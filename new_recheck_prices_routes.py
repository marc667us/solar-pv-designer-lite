# new_recheck_prices_routes.py
# 2026-06-24 -- "Recheck Prices" feature.
#
# A button on Basic Price Schedule + Cost Estimate POSTs to
# /boms/<bom_id>/recheck-prices which asks the existing zero-cost LLM
# chain (OpenRouter free :free models -> Ollama -> GitHub Models) for
# current retail prices in the BOM's country/currency for every item.
# The proposals land in session, the owner reviews them at
# /boms/<bom_id>/recheck-prices/review, ticks the rows to accept, and
# POSTs to /boms/<bom_id>/recheck-prices/apply.
#
# Per-line basic_price column on marketplace_bom_items is updated for
# the BOM. (The catalogue equipment_catalog row is NOT touched -- this
# is a per-project recheck, not a master-catalogue rewrite. A separate
# admin flow can promote accepted prices to the master catalogue later.)
#
# Country resolution: BOM stores a `currency` ISO code (GHS / NGN / KES
# / ZAR / USD / EUR / GBP). Currency -> country map below. A BOM in USD
# defaults to the platform locale (Ghana) so the lookup still gets a
# real market context.
#
# Provider chain explicitly excludes paid Anthropic per the zero-cost
# rule in CLAUDE.md.


import json as _json
import os as _os
import urllib.request as _ur
import urllib.error as _ue
from datetime import date as _date


_CURRENCY_TO_COUNTRY = {
    "GHS": ("Ghana",         "GHS"),
    "NGN": ("Nigeria",       "NGN"),
    "KES": ("Kenya",         "KES"),
    "ZAR": ("South Africa",  "ZAR"),
    "USD": ("Ghana",         "USD"),  # platform locale fallback
    "EUR": ("Germany",       "EUR"),
    "GBP": ("United Kingdom","GBP"),
}


def _recheck_country_for(currency_code: str):
    """ISO currency -> (country_name, currency_for_prompt)."""
    return _CURRENCY_TO_COUNTRY.get(
        (currency_code or "GHS").upper().strip(),
        ("Ghana", currency_code or "GHS"),
    )


def _recheck_build_prompt(items_for_prompt, country, currency):
    """Build a single batched prompt.

    items_for_prompt is a list of dicts:
        {"id": int, "name": str, "spec": str, "brand": str, "unit": str,
         "current_price": float}

    The model must return ONLY a JSON object of the form
        {"prices": [{"id": int, "price": float, "source": str,
                     "confidence": "low"|"med"|"high"}, ...]}
    """
    today = _date.today().isoformat()
    rows = []
    for it in items_for_prompt:
        rows.append(
            "  - id={id}, name={name!r}, spec={spec!r}, brand={brand!r}, "
            "unit={unit!r}, current_price_{cur}={cp:.2f}".format(
                id=it["id"], name=it["name"][:160], spec=it["spec"][:160],
                brand=it["brand"][:80], unit=it["unit"][:20],
                cur=currency, cp=float(it["current_price"] or 0),
            )
        )
    body = "\n".join(rows)
    return (
        "You are a procurement analyst. For each item below, return THREE "
        "current retail unit prices from THREE DIFFERENT NAMED SUPPLIERS in "
        "{country} as of {today}, quoted in {currency}, from local "
        "electrical / solar / construction suppliers "
        "(e.g. for Ghana: Tridem, Beta Stores, A-Life Magnetic, ABB Ghana, "
        "Schneider Electric Ghana; for Nigeria: Coscharis, Power Limited; "
        "for Kenya: Davis & Shirtliff, Power Technics). If you cannot find "
        "three real suppliers, return what you have and set "
        "confidence='low' on missing rows.\n\n"
        "Items:\n{body}\n\n"
        "Return ONLY a valid JSON object, no markdown, no commentary. "
        "The 'price' field is the AVERAGE of the three supplier quotes "
        "(use this as the proposed new basic price). The 'quotes' array "
        "must contain THREE supplier-named entries (omit at most one if "
        "truly unavailable):\n"
        "{{\n"
        "  \"prices\": [\n"
        "    {{\n"
        "      \"id\": <int>,\n"
        "      \"price\": <average of the three quotes in {currency}>,\n"
        "      \"source\": \"<short note: 'avg of 3 quotes' or vendor name>\",\n"
        "      \"confidence\": \"low\"|\"med\"|\"high\",\n"
        "      \"quotes\": [\n"
        "        {{\"supplier\": \"<vendor 1 name>\", \"price\": <num>, \"note\": \"<optional source url or note>\"}},\n"
        "        {{\"supplier\": \"<vendor 2 name>\", \"price\": <num>, \"note\": \"\"}},\n"
        "        {{\"supplier\": \"<vendor 3 name>\", \"price\": <num>, \"note\": \"\"}}\n"
        "      ]\n"
        "    }}\n"
        "  ]\n"
        "}}".format(
            country=country, today=today, currency=currency, body=body,
        )
    )


def _recheck_call_llm(prompt: str):
    """Run the prompt through the zero-cost provider chain. Returns
    (raw_text, source_label) or (None, error_msg)."""
    errors = []

    # 1. OpenRouter free models
    or_key = _os.environ.get("OPENROUTER_API_KEY", "")
    if or_key:
        for model in (
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemma-2-9b-it:free",
            "mistralai/mistral-7b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ):
            try:
                req = _ur.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    data=_json.dumps({
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2400,
                        "temperature": 0.2,
                    }).encode(),
                    headers={
                        "Authorization": f"Bearer {or_key}",
                        "Content-Type":  "application/json",
                        "HTTP-Referer":  "https://solarpro.aiappinvent.com",
                        "X-Title":       "SolarPro Price Recheck",
                    },
                )
                with _ur.urlopen(req, timeout=90) as resp:
                    payload = _json.loads(resp.read())
                return (payload["choices"][0]["message"]["content"].strip(),
                        f"openrouter:{model.split('/')[1]}")
            except _ue.HTTPError as e:
                errors.append(
                    f"OR {model} HTTP{e.code}: "
                    f"{e.read().decode('utf-8','ignore')[:120]}"
                )
            except Exception as e:
                errors.append(f"OR {model}: {e}")

    # 2. Ollama (local)
    ollama_url = _os.environ.get("OLLAMA_URL", "")
    if ollama_url:
        try:
            model = _os.environ.get("OLLAMA_MODEL", "mistral")
            req = _ur.Request(
                ollama_url.rstrip("/") + "/api/chat",
                data=_json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
            with _ur.urlopen(req, timeout=120) as resp:
                payload = _json.loads(resp.read())
            text = (payload.get("message") or {}).get("content") or ""
            if text:
                return text.strip(), f"ollama:{model}"
        except Exception as e:
            errors.append(f"Ollama: {e}")

    # 3. GitHub Models
    gh_token = _os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        try:
            req = _ur.Request(
                "https://models.inference.ai.azure.com/chat/completions",
                data=_json.dumps({
                    "model": "gpt-4.1-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2400,
                    "temperature": 0.2,
                }).encode(),
                headers={
                    "Authorization": f"Bearer {gh_token}",
                    "Content-Type":  "application/json",
                },
            )
            with _ur.urlopen(req, timeout=90) as resp:
                payload = _json.loads(resp.read())
            return (payload["choices"][0]["message"]["content"].strip(),
                    "github:gpt-4.1-mini")
        except Exception as e:
            errors.append(f"GH: {e}")

    return None, "all providers failed: " + " | ".join(errors[:3])


def _recheck_parse(raw: str):
    """Parse the LLM response into a dict {id: {price, source, confidence}}.
    Tolerates the model wrapping JSON in markdown ```json``` fences."""
    if not raw:
        return {}
    t = raw.strip()
    if t.startswith("```"):
        # strip opening fence (optionally with language tag)
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1 :]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    # Try to slice from first { to last }
    if not t.startswith("{"):
        i = t.find("{")
        if i >= 0:
            t = t[i:]
    if not t.endswith("}"):
        j = t.rfind("}")
        if j >= 0:
            t = t[: j + 1]
    try:
        obj = _json.loads(t)
    except Exception:
        return {}
    out = {}
    for row in (obj.get("prices") or []):
        try:
            iid = int(row.get("id"))
            price = float(row.get("price") or 0)
            source = (row.get("source") or "")[:120]
            conf = (row.get("confidence") or "low")[:10].lower()
            if conf not in ("low", "med", "high"):
                conf = "low"
            quotes = []
            for q in (row.get("quotes") or [])[:5]:
                try:
                    quotes.append({
                        "supplier": (q.get("supplier") or "")[:200],
                        "price":    float(q.get("price") or 0),
                        "note":     (q.get("note") or "")[:300],
                    })
                except (TypeError, ValueError):
                    continue
            # If model gave quotes but no avg, compute it.
            if quotes and price <= 0:
                ps = [q["price"] for q in quotes if q["price"] > 0]
                if ps:
                    price = sum(ps) / len(ps)
            out[iid] = {
                "price": price, "source": source, "confidence": conf,
                "quotes": quotes,
            }
        except (TypeError, ValueError):
            continue
    return out


# ─────────────────────────── Routes ───────────────────────────


def register_recheck_prices_routes(
    app, login_required, session, request, redirect, url_for, flash,
    render_template, current_user, get_db, _bom_owned_or_404,
    _bom_items_with_prices, _CURRENCY_RATES_FROM_USD, csrf_protect,
):
    """Wire the three routes onto the live Flask app. Closures keep this
    file free of `from web_app import ...` cycles."""

    @app.route("/boms/<int:bom_id>/recheck-prices", methods=["POST"])
    @login_required
    def boms_recheck_prices(bom_id):
        """Step 1: call the LLM for proposed prices, stash in session,
        redirect to the review page."""
        uid = session["user_id"]
        bom = _bom_owned_or_404(bom_id, uid)
        csrf_protect()
        items = _bom_items_with_prices(bom_id)
        if not items:
            flash("No items on this BOM to recheck.", "warning")
            return redirect(url_for("boms_basic_prices", bom_id=bom_id))

        currency = (bom["currency"] if "currency" in bom.keys() and bom["currency"]
                    else "GHS")
        country, _cur_for_prompt = _recheck_country_for(currency)
        fx_rate = float(_CURRENCY_RATES_FROM_USD.get(currency, 1.0) or 1.0)

        # Build prompt rows in the BOM's local currency.
        prompt_items = []
        for it in items:
            basic_usd = float(
                (it["unit_price_override"] if it["unit_price_override"] is not None
                 else (it["catalog_price"] or 0)) or 0
            )
            basic_local = basic_usd * fx_rate
            name = (
                it["custom_name"] if "custom_name" in it.keys() and it["custom_name"]
                else (it["catalog_name"] if "catalog_name" in it.keys() else "")
            ) or ""
            spec = (it["specification"] if "specification" in it.keys() else "") or ""
            brand = (it["brand"] if "brand" in it.keys() and it["brand"]
                     else (it["catalog_brand"] if "catalog_brand" in it.keys() else "")) or ""
            prompt_items.append({
                "id": int(it["id"]),
                "name": str(name),
                "spec": str(spec),
                "brand": str(brand),
                "unit": str(it["unit"] or "No."),
                "current_price": basic_local,
            })

        prompt = _recheck_build_prompt(prompt_items, country, currency)
        raw, source = _recheck_call_llm(prompt)
        if raw is None:
            flash(
                "Price recheck could not reach any AI provider. "
                f"({source}) Set OPENROUTER_API_KEY or OLLAMA_URL and try again.",
                "danger",
            )
            return redirect(url_for("boms_basic_prices", bom_id=bom_id))

        proposed = _recheck_parse(raw)
        if not proposed:
            flash(
                "Recheck returned no usable prices. "
                f"Provider was {source} -- try again later.",
                "warning",
            )
            return redirect(url_for("boms_basic_prices", bom_id=bom_id))

        # Stash proposals in session, keyed by bom_id. Includes per-supplier
        # quotes (B feature) + anomaly flag (>+/-25% from current price).
        key = f"recheck_proposals_{bom_id}"
        def _anomaly(current, prop):
            if not current or current <= 0 or not prop or prop <= 0:
                return False
            return abs(prop - current) / current > 0.25
        session[key] = {
            "currency": currency,
            "country":  country,
            "source":   source,
            "ts":       _date.today().isoformat(),
            "items": {
                str(it["id"]): {
                    "current":   it["current_price"],
                    "name":      it["name"],
                    "unit":      it["unit"],
                    "proposed":  proposed.get(it["id"], {}).get("price", 0),
                    "src_note":  proposed.get(it["id"], {}).get("source", ""),
                    "confidence":proposed.get(it["id"], {}).get("confidence", "low"),
                    "quotes":    proposed.get(it["id"], {}).get("quotes", []),
                    "anomaly":   _anomaly(it["current_price"],
                                          proposed.get(it["id"], {}).get("price", 0)),
                }
                for it in prompt_items
            },
        }
        flash(
            f"Recheck complete via {source}. Review proposed {currency} prices for "
            f"{country} below; tick the rows you want to apply.",
            "info",
        )
        return redirect(url_for("boms_recheck_prices_review", bom_id=bom_id))

    @app.route("/boms/<int:bom_id>/recheck-prices/review", methods=["GET"])
    @login_required
    def boms_recheck_prices_review(bom_id):
        uid = session["user_id"]
        bom = _bom_owned_or_404(bom_id, uid)
        key = f"recheck_proposals_{bom_id}"
        proposals = session.get(key) or {}
        if not proposals.get("items"):
            flash(
                "No proposed prices in session. Click Recheck Prices first.",
                "warning",
            )
            return redirect(url_for("boms_basic_prices", bom_id=bom_id))
        # Sort rows by current item id so the page is stable across reloads.
        rows = []
        for sid, info in proposals["items"].items():
            try:
                rows.append((int(sid), info))
            except ValueError:
                continue
        rows.sort(key=lambda r: r[0])
        return render_template(
            "bom_recheck_review.html",
            user=current_user(),
            bom=bom, rows=rows, meta=proposals,
        )

    @app.route("/boms/<int:bom_id>/recheck-prices/apply", methods=["POST"])
    @login_required
    def boms_recheck_prices_apply(bom_id):
        uid = session["user_id"]
        bom = _bom_owned_or_404(bom_id, uid)
        csrf_protect()
        key = f"recheck_proposals_{bom_id}"
        proposals = session.get(key) or {}
        if not proposals.get("items"):
            flash("Nothing to apply -- the proposals expired.", "warning")
            return redirect(url_for("boms_basic_prices", bom_id=bom_id))
        currency = proposals.get("currency", "GHS")
        fx_rate = float(_CURRENCY_RATES_FROM_USD.get(currency, 1.0) or 1.0)
        if fx_rate <= 0:
            fx_rate = 1.0
        applied = 0
        skipped = 0
        catalogue_pushes = 0
        ticked = set()
        push_to_catalog = set()
        for k in request.form.getlist("apply"):
            try:
                ticked.add(int(k))
            except (TypeError, ValueError):
                pass
        for k in request.form.getlist("push_catalog"):
            try:
                push_to_catalog.add(int(k))
            except (TypeError, ValueError):
                pass
        # Lazy import to avoid circular at module load.
        try:
            from new_catalogue_pricing_routes import (
                _record_catalog_quote, _record_price_history,
                _ensure_pricing_tables,
            )
            _ensure_pricing_tables(get_db,
                lambda: bool(__import__("os").environ.get("DATABASE_URL")))
        except Exception:
            _record_catalog_quote = None
            _record_price_history = None
        with get_db() as c:
            for sid, info in proposals["items"].items():
                try:
                    iid = int(sid)
                except ValueError:
                    continue
                if iid not in ticked:
                    skipped += 1
                    continue
                proposed_local = float(info.get("proposed") or 0)
                if proposed_local <= 0:
                    skipped += 1
                    continue
                proposed_usd = proposed_local / fx_rate
                try:
                    c.execute(
                        "UPDATE marketplace_bom_items "
                        "SET basic_price=?, unit_price_override=? "
                        "WHERE id=? AND bom_id=?",
                        (proposed_local, proposed_usd, iid, bom_id),
                    )
                except Exception:
                    c.execute(
                        "UPDATE marketplace_bom_items "
                        "SET unit_price_override=? "
                        "WHERE id=? AND bom_id=?",
                        (proposed_usd, iid, bom_id),
                    )
                applied += 1

                # B (3-quote): record every supplier quote that came back.
                quotes = info.get("quotes") or []
                anomaly = bool(info.get("anomaly"))
                if _record_catalog_quote and quotes:
                    # Resolve the catalogue product_id for this BOM line.
                    try:
                        prod_row = c.execute(
                            "SELECT product_id FROM marketplace_bom_items WHERE id=?",
                            (iid,),
                        ).fetchone()
                        cat_pid = int((prod_row["product_id"] if prod_row else 0) or 0)
                    except Exception:
                        cat_pid = 0
                    if cat_pid:
                        for q in quotes:
                            _record_catalog_quote(
                                get_db, cat_pid,
                                q.get("supplier") or "", 0,
                                float(q.get("price") or 0),
                                currency, q.get("note") or "",
                                anomaly, uid, status="proposed",
                            )

                # C (push-to-catalogue): if owner ticked the box AND the line
                # points at a real catalogue product, update the master price.
                if iid in push_to_catalog and _record_price_history:
                    try:
                        prod_row = c.execute(
                            "SELECT product_id FROM marketplace_bom_items WHERE id=?",
                            (iid,),
                        ).fetchone()
                        cat_pid = int((prod_row["product_id"] if prod_row else 0) or 0)
                    except Exception:
                        cat_pid = 0
                    if cat_pid:
                        old_row = c.execute(
                            "SELECT price_usd FROM equipment_catalog WHERE id=?",
                            (cat_pid,),
                        ).fetchone()
                        old_usd = float((old_row["price_usd"] if old_row else 0) or 0)
                        c.execute(
                            "UPDATE equipment_catalog SET price_usd=? WHERE id=?",
                            (proposed_usd, cat_pid),
                        )
                        _record_price_history(
                            get_db, cat_pid, old_usd, proposed_usd,
                            currency, proposed_local,
                            f"recheck-from-bom #{bom_id}",
                            f"AI source: {proposals.get('source','?')}",
                            uid, status="approved",
                        )
                        catalogue_pushes += 1
            c.execute(
                "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                (bom_id,),
            )
        # Best-effort audit row.
        try:
            from new_boq_hierarchy_schema import boq_audit
            boq_audit(
                get_db, uid, "bom_prices_rechecked", "marketplace_bom",
                bom_id,
                f"applied={applied} skipped={skipped} "
                f"src={proposals.get('source','?')}",
            )
        except Exception:
            pass
        session.pop(key, None)
        push_msg = (f" {catalogue_pushes} also pushed to the master catalogue."
                    if catalogue_pushes else "")
        flash(
            f"Applied {applied} new price(s). {skipped} skipped.{push_msg} "
            "Recompute the Cost Estimate to see the new totals.",
            "success",
        )
        return redirect(url_for("boms_basic_prices", bom_id=bom_id))
