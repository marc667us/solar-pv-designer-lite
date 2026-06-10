#!/usr/bin/env bash
# Shared review-runner used by every codex-*-review.sh and supervise-codex.sh.
# Despite the filename, this can run against either Ollama (default, zero-cost) or
# Codex CLI (if REVIEWER_BACKEND=codex is set). Keeping the filename for stability
# across the existing scripts; treat it as "the reviewer runner".
#
# Backend selection:
#   REVIEWER_BACKEND=ollama  (default) — uses local Ollama API at http://localhost:11434
#   REVIEWER_BACKEND=codex            — uses codex CLI (needs OPENAI_API_KEY or codex login)
#
# Model selection (Ollama only):
#   REVIEWER_MODEL=mistral   (default) — better instruction-following, 4.4 GB
#   REVIEWER_MODEL=llama3.2            — smaller/faster, 2.0 GB
#
# Output:
#   ../reviews/<name>.md — review-formatted markdown (clean text, no terminal control chars)

set -e

REVIEWER_BACKEND="${REVIEWER_BACKEND:-codex}"  # Codex CLI on ChatGPT Plus (default) — switch to ollama for zero-cost fallback if Plus auth lapses
REVIEWER_MODEL="${REVIEWER_MODEL:-llama3.2}"   # only used by the ollama backend; faster small model; switch to mistral for higher quality at the cost of speed
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

# Normalize OLLAMA_HOST: the Ollama daemon often exports 0.0.0.0:11434 (a bind address,
# not a connect URL). Translate to localhost and prepend scheme if missing.
OLLAMA_HOST="${OLLAMA_HOST//0.0.0.0/localhost}"
case "$OLLAMA_HOST" in
  http://*|https://*) ;;
  *) OLLAMA_HOST="http://$OLLAMA_HOST" ;;
esac

gather_context() {
  # Emits a *compact* markdown block with the diff stat + first 100 lines of diff
  # + git status. We deliberately keep this small because Ollama's local models
  # are slow on CPU and large prompts cause multi-minute calls. Tune with
  # CONTEXT_DIFF_LINES (default 100) or CONTEXT_NAMESTAT_ONLY=1 (just file names).
  local repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  local diff_lines="${CONTEXT_DIFF_LINES:-100}"
  (
    cd "$repo_root"
    echo "## Repository context"
    echo ""
    if git rev-parse --git-dir >/dev/null 2>&1; then
      local diff_target=""
      if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
        diff_target="HEAD~1..HEAD"
      fi
      echo "### Changed files${diff_target:+ ($diff_target)}"
      echo '```'
      if [ -n "$diff_target" ]; then
        git diff --stat "$diff_target" 2>/dev/null | head -20
      else
        git diff --stat 2>/dev/null | head -20
        git status --short 2>/dev/null | head -20
      fi
      echo '```'
      if [ "${CONTEXT_NAMESTAT_ONLY:-0}" != "1" ]; then
        echo ""
        echo "### Diff snippet (first ${diff_lines} lines)"
        echo '```diff'
        if [ -n "$diff_target" ]; then
          git diff "$diff_target" 2>/dev/null | head -"$diff_lines"
        else
          git diff 2>/dev/null | head -"$diff_lines"
        fi
        echo '```'
      fi
    else
      echo "_(not a git repository — context unavailable; reviewer will rely on prompt only)_"
    fi
  )
}

codex_run() {
  local name="$1"
  local prompt="$2"
  local out_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/reviews"
  local out_file="$out_dir/$name.md"

  mkdir -p "$out_dir"

  {
    echo "# Review: $name"
    echo ""
    echo "_Generated: $(date -Iseconds) · backend: ${REVIEWER_BACKEND} · model: ${REVIEWER_MODEL}_"
    echo ""
    echo "## Prompt"
    echo ""
    echo "> $prompt"
    echo ""
    echo "## Findings"
    echo ""
  } > "$out_file"

  # Track per-call failure so we propagate it to the caller instead of
  # silently writing a "call failed" stub and pretending the review succeeded.
  local _rc=0
  case "$REVIEWER_BACKEND" in
    ollama)
      if ! _run_ollama "$prompt" >> "$out_file" 2>>"$out_file"; then
        echo -e "\n\n_Ollama call failed - check that the daemon is running (\`ollama serve\` / Ollama tray app) and the model is pulled (\`ollama pull ${REVIEWER_MODEL}\`)._" >> "$out_file"
        _rc=1
      fi
      ;;
    codex)
      if ! _run_codex "$prompt" >> "$out_file" 2>>"$out_file"; then
        echo -e "\n\n_Codex call failed - check auth (OPENAI_API_KEY or \`codex login\`)._" >> "$out_file"
        _rc=1
      fi
      ;;
    *)
      echo "ERROR: unknown REVIEWER_BACKEND='$REVIEWER_BACKEND' (expected: ollama | codex)" >&2
      return 1
      ;;
  esac

  echo "Wrote: $out_file"
  return $_rc
}

_run_ollama() {
  local prompt="$1"

  # Compose system + user into a single prompt the model receives.
  local sysmsg="You are an independent code reviewer in a Claude+Codex+Supervisor pair-coding workflow. Be skeptical, specific, brief. Output markdown with severity (critical/high/medium/low), file:line citation, what's wrong, recommended fix, why it matters. If you do not have file content in context, say so explicitly rather than inventing findings."
  local full_prompt="${sysmsg}

---

${prompt}"

  # POST to /api/generate via curl + python (no jq dependency).
  # Python both builds the JSON body (safe escaping) and parses the response.
  python - "$REVIEWER_MODEL" "$OLLAMA_HOST" "$full_prompt" <<'PY'
import json, sys, urllib.request, urllib.error

model, host, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
# Ask for a larger output ceiling; small defaults are why findings sometimes come back empty.
# num_predict = max output tokens; num_ctx = total context the model loads.
body = json.dumps({
    "model": model,
    "prompt": prompt,
    "stream": False,
    "options": {"num_predict": 800, "num_ctx": 4096, "temperature": 0.2},
}).encode("utf-8")
req = urllib.request.Request(f"{host}/api/generate", data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=900) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    answer = data.get("response", "").strip()
    if not answer:
        # Surface the failure rather than silently writing an empty Findings section.
        keys = sorted(data.keys())
        err = data.get("error") or ""
        done_reason = data.get("done_reason") or ""
        eval_count = data.get("eval_count")
        print(f"_Reviewer returned empty response. done_reason={done_reason!r} eval_count={eval_count!r} error={err!r} keys={keys}_")
        print("_Likely causes: prompt too large for the model's context window, model not pulled, or daemon issue._")
        print(f"_Try a larger model (REVIEWER_MODEL=mistral) or trim repo context in scripts/_codex-runner.sh's gather_context()._")
    else:
        print(answer)
except urllib.error.URLError as e:
    print(f"_Ollama HTTP error: {e}_", file=sys.stderr)
    sys.exit(2)
except Exception as e:
    print(f"_Reviewer error: {e}_", file=sys.stderr)
    sys.exit(3)
PY
}

_run_codex() {
  local prompt="$1"
  local codex_bin
  if command -v codex >/dev/null 2>&1; then
    codex_bin="codex"
  elif [ -x "/c/Users/USER/nodejs/codex.cmd" ]; then
    codex_bin="/c/Users/USER/nodejs/codex.cmd"
  else
    echo "ERROR: codex CLI not found. Install with: npm install -g @openai/codex" >&2
    return 1
  fi
  # -s workspace-write: let Codex run shell commands (rg, git, node -e, etc.) inside the project.
  #                     Reads + writes confined to the workspace root; nothing outside is touched.
  #                     Without this, Codex's default read-only sandbox blocks the discovery calls
  #                     it needs to investigate findings, and reviews fall back to web-search only.
  "$codex_bin" exec --skip-git-repo-check -s workspace-write "$prompt"
}
