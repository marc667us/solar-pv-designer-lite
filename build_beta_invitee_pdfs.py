"""
Build the two beta-invitee PDFs (suppliers + installers) from the master JSON.

What it does
------------
1. Reads `data/ghana_beta_invitees.json` (the master list).
2. Filters entities by role: "supplier" -> suppliers PDF, "installer" -> installers PDF.
   Entities with both roles appear in both PDFs (they are real candidates either way).
3. Renders each PDF via the `markdown-pdf` package (per project memory; pandoc/wkhtmltopdf
   are NOT installed on this machine — only `markdown-pdf` works).
4. Writes the two PDFs to `docs/` AND copies them to the user's Desktop for quick access.

Inputs
------
- ./data/ghana_beta_invitees.json   (UTF-8 JSON, schema described in that file)

Outputs
-------
- ./docs/Ghana_Solar_Suppliers_Beta_Invitees.pdf
- ./docs/Ghana_Solar_Installers_Beta_Invitees.pdf
- C:/Users/USER/Desktop/Ghana_Solar_Suppliers_Beta_Invitees.pdf
- C:/Users/USER/Desktop/Ghana_Solar_Installers_Beta_Invitees.pdf

Syntax notes
------------
- `MarkdownPdf(toc_level=2, optimize=True)` builds a multi-section doc with a TOC at h1+h2.
- `Section(text, toc=True)` = add a TOC entry for this section.
- `user_css=` applies the CSS to that section only (we want the same styling everywhere).
- `shutil.copy2` preserves the file mtime when we copy to Desktop.
- We render markdown tables, not raw HTML — `markdown-pdf` handles the conversion.
"""
import json
import shutil
from pathlib import Path
from markdown_pdf import MarkdownPdf, Section

PROJECT = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite")
DESKTOP = Path(r"C:\Users\USER\Desktop")
SRC = PROJECT / "data" / "ghana_beta_invitees.json"
DOCS = PROJECT / "docs"
DOCS.mkdir(exist_ok=True)

# CSS matched to the tutorial-PDF template on Desktop so look-and-feel is consistent
CSS = """
body { font-family: 'Segoe UI', Calibri, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 22pt; color: #1f5fb8; border-bottom: 3px solid #1f5fb8; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 15pt; color: #2a6fcc; margin-top: 22px; border-bottom: 1px solid #d8e3f0; padding-bottom: 3px; }
h3 { font-size: 12pt; color: #333; margin-top: 14px; }
h4 { font-size: 10.5pt; color: #555; margin-bottom: 4px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }
th { background: #1f5fb8; color: #fff; text-align: left; padding: 5px 8px; }
td { border: 1px solid #d8e3f0; padding: 5px 8px; vertical-align: top; }
tr:nth-child(even) td { background: #f4f8fd; }
strong { color: #1a1a1a; }
a { color: #1f5fb8; }
hr { border: none; border-top: 1px solid #ddd; margin: 18px 0; }
.badge-supplier { background: #e8f0fc; color: #1f5fb8; padding: 2px 7px; border-radius: 3px; font-size: 8.5pt; }
.badge-installer { background: #e9f7e8; color: #2e7d32; padding: 2px 7px; border-radius: 3px; font-size: 8.5pt; }
.note { font-size: 9pt; color: #555; font-style: italic; }
"""


def render_entity(e: dict) -> str:
    """Return one markdown block for a single entity.

    Inputs:  e = dict with keys name, roles, services, address, city, email,
             phones[list], contact_person, website, notes
    Output:  multi-line markdown string with an h3 heading + key/value table.
    """
    # Format the phones list — joins with " / " or shows em-dash if empty
    phones = " / ".join(e["phones"]) if e["phones"] else "—"
    # Inline e-mail mailto: links so the PDF is clickable
    email = f"[{e['email']}](mailto:{e['email'].split('/')[0].strip()})" if e["email"] else "—"
    # Website link
    website = f"[{e['website']}]({e['website'].split(' ')[0]})" if e["website"] else "—"
    contact_person = e["contact_person"] or "—"

    # Each entity is rendered as an h3 + a 2-column key/value table — easy to scan.
    md = f"""
### {e['name']}

| Field | Value |
|---|---|
| **Services** | {e['services']} |
| **Address** | {e['address']} |
| **City** | {e['city']} |
| **Email** | {email} |
| **Phones** | {phones} |
| **Contact person** | {contact_person} |
| **Website** | {website} |
| **Notes** | {e['notes']} |
"""
    return md


def build_pdf(entities: list[dict], role: str, out_path: Path):
    """Render the entities list to a PDF for the given role.

    Inputs:  entities = list of dicts that match the role
             role = "supplier" | "installer" (used in title)
             out_path = where to write the PDF (Path)
    Output:  writes the PDF file; returns the path.
    """
    title = "Ghana Solar Suppliers — Beta-Testing Invitees" if role == "supplier" \
        else "Ghana Solar Installers — Beta-Testing Invitees"

    # Cover-page-ish intro section (no TOC entry — toc=False)
    intro_md = f"""# {title}

**Compiled:** 2026-06-05
**Purpose:** SolarPro Global beta-testing invitation list.
**Source:** Public web (company websites, ENF Solar directory, Ghana Yellow Pages).
**Count:** {len(entities)} entities.

> All emails, phone numbers and addresses below were collected from public web sources
> on 2026-06-05. Verify before sending production-scale outreach — Ghana mobile numbers
> change networks; e-commerce sites may not publish street addresses.

---

## How to use this list

1. Sort by **roles** in `data/ghana_beta_invitees.json` (companies that are both
   suppliers and installers get the strongest invite — they have BOQ + design needs).
2. Invite Tesano-/Tema-based companies first (Nocheski, Ozo, Translight) — they are
   easiest to visit in person if a phone call lands in voicemail.
3. **Phones** are listed with the most recent first — call before emailing; Ghanaian
   SMB owners answer phones more reliably than e-mail.
4. **Contact person** is blank where no individual name was published — start with
   `info@` / `sales@` aliases, then ask for a named lead on the first call.

---
"""

    # toc_level=3 = include h1+h2+h3 in TOC.
    # The intro must be toc=True so the h1 title is the TOC root —
    # PyMuPDF requires the first TOC item to be level 1.
    pdf = MarkdownPdf(toc_level=3, optimize=True)
    pdf.add_section(Section(intro_md, toc=True), user_css=CSS)

    # One section per entity, all under an h2 grouping header so the TOC reads cleanly.
    body = "## Entity directory\n\n"
    for e in entities:
        body += render_entity(e) + "\n---\n"
    pdf.add_section(Section(body, toc=True), user_css=CSS)

    pdf.meta["title"] = title
    pdf.meta["author"] = "SolarPro Global"
    pdf.meta["subject"] = "Beta testing invitee list — Ghana"
    pdf.save(str(out_path))
    return out_path


def main():
    """Load JSON, split by role, render two PDFs, mirror to Desktop."""
    data = json.loads(SRC.read_text(encoding="utf-8"))
    entities = data["entities"]

    suppliers = [e for e in entities if "supplier" in e["roles"]]
    installers = [e for e in entities if "installer" in e["roles"]]

    sup_path = DOCS / "Ghana_Solar_Suppliers_Beta_Invitees.pdf"
    inst_path = DOCS / "Ghana_Solar_Installers_Beta_Invitees.pdf"

    build_pdf(suppliers, "supplier", sup_path)
    build_pdf(installers, "installer", inst_path)

    # Mirror to Desktop for the user's quick access
    for src in (sup_path, inst_path):
        dest = DESKTOP / src.name
        shutil.copy2(src, dest)
        print(f"  wrote: {src}")
        print(f"  wrote: {dest}")

    # Also copy the master JSON to Desktop (lightweight, useful for editing later)
    shutil.copy2(SRC, DESKTOP / SRC.name)
    print(f"  wrote: {DESKTOP / SRC.name}")

    print(f"\nSuppliers: {len(suppliers)}")
    print(f"Installers: {len(installers)}")


if __name__ == "__main__":
    main()
