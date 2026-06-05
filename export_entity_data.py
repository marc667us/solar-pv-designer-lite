"""
Export the Ghana beta-invitee master list to every format the team might need.

What it does
------------
Reads `data/ghana_beta_invitees.json` (the single source of truth) and produces:
  - ghana_beta_invitees.csv    — Excel / Sheets / CRM imports
  - ghana_beta_invitees.vcf    — Phone contacts (iOS, Android, Outlook all read vCard 3.0)
  - ghana_beta_invitees.md     — Markdown table for Slack / Notion / email
  - ghana_beta_invitees.tsv    — Tab-separated, safe for fields containing commas
  - ghana_beta_invitees.flat.json — Same data but flattened (no nested lists) for CRMs
                                    that won't accept arrays in a cell

Inputs
------
- data/ghana_beta_invitees.json

Outputs
-------
- Files above, written to:
    1) data/exports/                                  (canonical, in repo)
    2) C:/Users/USER/Desktop/SolarPro_Ghana_Internal_App/data/  (next to the internal app)

Syntax notes
------------
- vCard 3.0 line endings MUST be CRLF (\r\n) per RFC 2426, otherwise some
  phones silently drop fields. We open with `newline=''` and write explicit \r\n.
- CSV uses csv.QUOTE_ALL so a comma in services/notes never breaks a row.
- Phones are split into TEL;TYPE=CELL entries one-per-line in VCF; in CSV
  we join with " | " (pipe with spaces) to remain Excel-safe.
"""
import csv
import json
import shutil
from pathlib import Path

PROJECT = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite")
DESKTOP_APP = Path(r"C:\Users\USER\Desktop\SolarPro_Ghana_Internal_App")
SRC = PROJECT / "data" / "ghana_beta_invitees.json"

OUT_REPO = PROJECT / "data" / "exports"
OUT_DESK = DESKTOP_APP / "data"
OUT_REPO.mkdir(exist_ok=True, parents=True)
OUT_DESK.mkdir(exist_ok=True, parents=True)


def roles_str(roles):
    """Join the roles list as a single human-readable string ('supplier+installer')."""
    return "+".join(roles) if roles else ""


def phones_str(phones, sep=" | "):
    """Flatten phones list to a single cell. Default sep = pipe (CSV/Excel safe)."""
    return sep.join(phones) if phones else ""


def write_csv(entities, path: Path):
    """Write QUOTE_ALL CSV — safe to open in Excel and import into any CRM."""
    cols = ["name", "roles", "services", "address", "city", "email",
            "phones", "contact_person", "website", "notes"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        # utf-8-sig writes a BOM so Excel detects UTF-8 (Ghanaian street names use diacritics)
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(cols)
        for e in entities:
            w.writerow([
                e.get("name", ""),
                roles_str(e.get("roles", [])),
                e.get("services", ""),
                e.get("address", ""),
                e.get("city", ""),
                e.get("email", "") or "",
                phones_str(e.get("phones", [])),
                e.get("contact_person", "") or "",
                e.get("website", ""),
                e.get("notes", ""),
            ])


def write_tsv(entities, path: Path):
    """Tab-separated version — preferable when notes/services contain commas."""
    cols = ["name", "roles", "services", "address", "city", "email",
            "phones", "contact_person", "website", "notes"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        w.writerow(cols)
        for e in entities:
            w.writerow([
                e.get("name", ""),
                roles_str(e.get("roles", [])),
                e.get("services", ""),
                e.get("address", ""),
                e.get("city", ""),
                e.get("email", "") or "",
                phones_str(e.get("phones", [])),
                e.get("contact_person", "") or "",
                e.get("website", ""),
                e.get("notes", ""),
            ])


def write_vcf(entities, path: Path):
    """Write a multi-entry vCard 3.0 file — drops straight into iOS Contacts,
    Google Contacts, Outlook. Each entity becomes one CARD.

    vCard requires CRLF line breaks. ORG is set to the company; FN/N are also
    the company (no individuals listed since most contact_person fields are null).
    """
    # vCard requires CRLF; open in binary-text mode to control line endings precisely
    lines = []
    for e in entities:
        name = (e.get("name") or "").replace(",", "\\,")
        company = name
        # Build per-card lines
        lines += [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"N:{name};;;;",                       # vCard N field — last;first;middle;prefix;suffix
            f"FN:{name}",                          # Formatted (display) name
            f"ORG:{company}",
            f"TITLE:{roles_str(e.get('roles', []))}",
        ]
        if e.get("contact_person"):
            cp = e["contact_person"].replace(",", "\\,")
            lines.append(f"NOTE:Contact person: {cp}")
        # One TEL line per phone, typed CELL (Ghana numbers are mobile-first)
        for ph in (e.get("phones") or []):
            ph_clean = ph.replace(" ", "")
            lines.append(f"TEL;TYPE=CELL,VOICE:{ph_clean}")
        if e.get("email"):
            # Some emails contain ' / ' as a separator in our source; split if so
            first_email = e["email"].split("/")[0].strip()
            lines.append(f"EMAIL;TYPE=WORK:{first_email}")
        if e.get("website"):
            lines.append(f"URL:{e['website'].split(' ')[0]}")
        if e.get("address"):
            # ADR-formatted line. We dump everything into the 'street' field since
            # Ghanaian addresses don't always parse into PO box / city / region cleanly.
            addr = e["address"].replace(";", ",")
            lines.append(f"ADR;TYPE=WORK:;;{addr};{e.get('city', '')};;;Ghana")
        if e.get("notes"):
            note = e["notes"].replace("\n", "\\n")
            lines.append(f"NOTE:{note}")
        # Categories help iOS/Android group by tag
        cats = ["SolarPro-Beta"] + e.get("roles", [])
        lines.append("CATEGORIES:" + ",".join(cats))
        lines.append("END:VCARD")
    # Write with explicit CRLF
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))


def write_md(entities, path: Path):
    """Markdown table — paste into Notion / Slack / email."""
    rows = ["| Name | Roles | City | Email | Phones | Website |",
            "|---|---|---|---|---|---|"]
    for e in entities:
        rows.append("| {n} | {r} | {c} | {em} | {p} | {w} |".format(
            n=e["name"],
            r=roles_str(e.get("roles", [])),
            c=e["city"],
            em=e.get("email") or "—",
            p=phones_str(e.get("phones", []), sep=" / ") or "—",
            w=f"[link]({e.get('website', '')})" if e.get("website") else "—",
        ))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_flat_json(entities, path: Path):
    """Flattened JSON — every nested list becomes a scalar.

    Use case: CRMs (Salesforce, HubSpot, Pipedrive) that import JSON but
    refuse arrays. roles becomes a string; phones becomes a string.
    """
    flat = []
    for e in entities:
        flat.append({
            "name": e.get("name", ""),
            "roles": roles_str(e.get("roles", [])),
            "services": e.get("services", ""),
            "address": e.get("address", ""),
            "city": e.get("city", ""),
            "email": e.get("email") or "",
            "phones": phones_str(e.get("phones", [])),
            "phone_primary": (e.get("phones") or [""])[0],
            "contact_person": e.get("contact_person") or "",
            "website": e.get("website", ""),
            "notes": e.get("notes", ""),
        })
    path.write_text(json.dumps(flat, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    entities = data["entities"]

    # 1) Write canonical copies in the repo (data/exports/)
    write_csv(entities,  OUT_REPO / "ghana_beta_invitees.csv")
    write_tsv(entities,  OUT_REPO / "ghana_beta_invitees.tsv")
    write_vcf(entities,  OUT_REPO / "ghana_beta_invitees.vcf")
    write_md(entities,   OUT_REPO / "ghana_beta_invitees.md")
    write_flat_json(entities, OUT_REPO / "ghana_beta_invitees.flat.json")
    # Also drop the original JSON next to its derived formats so the bundle is self-contained
    shutil.copy2(SRC, OUT_REPO / "ghana_beta_invitees.json")

    # 2) Mirror the whole exports/ folder into the Desktop internal-app bundle
    for name in ("ghana_beta_invitees.csv", "ghana_beta_invitees.tsv",
                 "ghana_beta_invitees.vcf", "ghana_beta_invitees.md",
                 "ghana_beta_invitees.flat.json", "ghana_beta_invitees.json"):
        shutil.copy2(OUT_REPO / name, OUT_DESK / name)
        print(f"  wrote: {OUT_REPO / name}")
        print(f"  wrote: {OUT_DESK / name}")

    print(f"\n{len(entities)} entities exported in 6 formats.")


if __name__ == "__main__":
    main()
