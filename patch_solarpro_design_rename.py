# -*- coding: utf-8 -*-
"""
patch_solarpro_design_rename.py
================================
Bytes-level, CRLF-safe rename of user-visible brand strings:

    "SolarPro Global"        -> "SolarPro Design"
    "SolarPro Design Lite"   -> "SolarPro Design"
    "Solar PV Designer Lite" -> "SolarPro Design"

Targets ONLY user-visible surfaces:
    - templates/*.html (including growth/*.html)
    - web_app.py
    - scripts/*.py (email flyers, launch scripts)

Explicitly SKIPPED:
    - reviews/*.md          (internal review notes)
    - k8s/, monitoring/     (labels + configs)
    - migrations/*.md       (internal docs)
    - keycloak/render/*.json (realm export)
    - logging_config/       (internal log identifiers)
    - tests/, tmp/          (dev artifacts)
    - output/, dist/, build/ (generated)

.solarpro FILE FORMAT COMPAT: web_app.py's project_open() checks that
imported .solarpro payloads carry `"app": "SolarPro Global"`. After the
rename we accept BOTH the old and the new brand string on import so
existing exports continue to load.

Idempotent - safe to re-run.
"""

from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
RENAMES: list[tuple[bytes, bytes]] = [
    (b"SolarPro Design Lite",   b"SolarPro Design"),
    (b"Solar PV Designer Lite", b"SolarPro Design"),
    (b"SolarPro Global",        b"SolarPro Design"),
]


def _target_files() -> list[str]:
    out: list[str] = []
    # 1. All template files
    for root, dirs, files in os.walk(os.path.join(REPO, "templates")):
        for name in files:
            if name.endswith(".html"):
                out.append(os.path.join(root, name))
    # 2. web_app.py at repo root
    out.append(os.path.join(REPO, "web_app.py"))
    # 3. Scripts that touch user-visible email / flyer content
    scripts_dir = os.path.join(REPO, "scripts")
    if os.path.isdir(scripts_dir):
        for name in os.listdir(scripts_dir):
            if name.endswith(".py"):
                out.append(os.path.join(scripts_dir, name))
    return out


def _patch_bytes(data: bytes) -> tuple[bytes, dict[str, int]]:
    counts: dict[str, int] = {}
    for old, new in RENAMES:
        n = data.count(old)
        if n:
            data = data.replace(old, new)
            counts[old.decode()] = n
    return data, counts


def _patch_solarpro_import_check(data: bytes) -> tuple[bytes, bool]:
    """Widen web_app.py's `.solarpro` import to accept both old and new
    brand strings. Uses a SPLIT-LITERAL form ("SolarPro"+" "+"Global")
    so future bytes-level bulk renames cannot match the substring
    "SolarPro Global" and stomp the compat tuple."""
    OK_MARKER = b"rename-safe: split literal so future brand renames do NOT touch legacy accept string"
    if OK_MARKER in data:
        return data, False
    NEW = (b'if payload.get("app") not in ("SolarPro Design", '
           b'"SolarPro" + " " + "Global") or "project" not in payload:  # '
           + OK_MARKER)
    # Case 1: original code with only the new brand string in the check.
    ORIG = (b'if payload.get("app") != "SolarPro Design" '
            b'or "project" not in payload:')
    if ORIG in data:
        return data.replace(ORIG, NEW), True
    # Case 2: bulk rename stomped a previous tuple form. Heal any
    # ("SolarPro Design", "SolarPro Design") variant.
    STOMPED = (b'if payload.get("app") not in '
               b'("SolarPro Design", "SolarPro Design") '
               b'or "project" not in payload:')
    if STOMPED in data:
        return data.replace(STOMPED, NEW), True
    return data, False


def main() -> int:
    files = _target_files()
    print(f"[INFO] Scanning {len(files)} target files")
    total_hits = 0
    files_changed = 0
    for p in files:
        try:
            data = open(p, "rb").read()
        except OSError as e:
            print(f"[SKIP] {p} - {e}")
            continue
        new_data, counts = _patch_bytes(data)
        if not counts:
            continue
        open(p, "wb").write(new_data)
        rel = os.path.relpath(p, REPO)
        summary = ", ".join(f"{k}={v}" for k, v in counts.items())
        print(f"[OK] {rel}: {summary}")
        total_hits += sum(counts.values())
        files_changed += 1

    # Now widen the .solarpro import check
    wa = os.path.join(REPO, "web_app.py")
    data = open(wa, "rb").read()
    data, widened = _patch_solarpro_import_check(data)
    if widened:
        open(wa, "wb").write(data)
        print("[OK] widened .solarpro import check to accept old + new brand string")
    else:
        print("[SKIP] .solarpro import check already widened OR anchor not found")

    print(f"---")
    print(f"[DONE] {files_changed} files changed, {total_hits} occurrences renamed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
