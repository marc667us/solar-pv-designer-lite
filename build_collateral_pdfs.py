"""
Render the three external/internal collateral PDFs:
  - Sales pitch (inbound call script)
  - User guide (end-user workflow)
  - Technical guide (engineering basis + integration)

What it does
------------
Reads each markdown file from docs/src/, builds a multi-section PDF with
the same CSS family used by the beta-invitee PDFs (so all collateral
looks like a coherent set), and mirrors the output to the Desktop.

Inputs
------
- docs/src/sales_pitch.md
- docs/src/user_guide.md
- docs/src/technical_guide.md

Outputs
-------
- docs/SolarPro_Sales_Pitch.pdf  (+ Desktop copy)
- docs/SolarPro_User_Guide.pdf   (+ Desktop copy)
- docs/SolarPro_Technical_Guide.pdf (+ Desktop copy)

Syntax notes
------------
- We split each markdown on top-level `#` headings so each Part starts on a
  new page (mirrors `_build_tutorial_pdf.py` on Desktop).
- `toc_level=3` includes h1+h2+h3 in the rendered TOC.
"""
import re
import shutil
from pathlib import Path
from markdown_pdf import MarkdownPdf, Section

PROJECT = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite")
DESKTOP = Path(r"C:\Users\USER\Desktop")
SRC_DIR = PROJECT / "docs" / "src"
DOCS = PROJECT / "docs"

CSS = """
@page { margin: 18mm 16mm; }
body { font-family: 'Segoe UI', Calibri, sans-serif; font-size: 11.5pt; line-height: 1.65; color: #1f2937; }
h1 { font-size: 28pt; color: #0d1f3c; margin: 0 0 4px; letter-spacing: -0.5px; font-weight: 800; }
h1::after { content: ""; display: block; width: 60px; height: 4px; background: linear-gradient(90deg,#ce1126,#fcd116,#006b3f); margin-top: 10px; border-radius: 2px; }
h2 { font-size: 16pt; color: #0d1f3c; margin: 32px 0 10px; padding: 6px 0 6px 14px; border-left: 5px solid #ce1126; background: linear-gradient(90deg, #fdf2f4 0%, transparent 60%); font-weight: 700; }
h3 { font-size: 13.5pt; color: #1f2937; margin: 24px 0 6px; font-weight: 700; }
h4 { font-size: 11.5pt; color: #475569; margin: 14px 0 4px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; }
p { margin: 8px 0 12px; }
table { border-collapse: collapse; width: 100%; margin: 14px 0 18px; font-size: 10.5pt; box-shadow: 0 1px 0 #e2e8f0; }
th { background: #0d1f3c; color: #fff; text-align: left; padding: 8px 12px; font-size: 10pt; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; }
td { border-bottom: 1px solid #e5e7eb; padding: 9px 12px; vertical-align: top; }
tr:nth-child(even) td { background: #f8fafc; }
code { background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10.5pt; font-weight: 600; }
pre { background: #0d1f3c; color: #e2e8f0; border-radius: 8px; padding: 14px 18px; font-size: 10pt; line-height: 1.55; margin: 14px 0; overflow-x: auto; }
pre code { background: none; padding: 0; color: inherit; }
blockquote { border-left: 5px solid #fcd116; background: linear-gradient(90deg,#fffbeb,#fffefa); margin: 16px 0; padding: 14px 22px; color: #78350f; font-style: normal; border-radius: 0 6px 6px 0; }
blockquote p { margin: 0; }
strong { color: #0d1f3c; font-weight: 700; }
a { color: #ce1126; text-decoration: none; border-bottom: 1px dotted #ce1126; }
hr { border: none; border-top: 2px solid #e2e8f0; margin: 28px 0; }
ul, ol { margin: 10px 0 14px; padding-left: 28px; }
li { margin: 4px 0; }
"""

# Three docs to render: (src_filename, out_filename, title, subject)
DOCS_TO_BUILD = [
    ("sales_pitch.md",      "SolarPro_Sales_Pitch.pdf",      "Inbound Sales Call Pitch",  "Sales enablement"),
    ("user_guide.md",       "SolarPro_User_Guide.pdf",       "User Guide",                "End-user workflow"),
    ("technical_guide.md",  "SolarPro_Technical_Guide.pdf",  "Technical Guide",           "Engineering basis"),
]


def render(src: Path, out: Path, title: str, subject: str):
    """Read markdown, split on top-level h1, render to PDF.

    Inputs:  src = Path to markdown file
             out = Path to write the PDF
             title = pdf meta title
             subject = pdf meta subject
    Output:  writes out, returns the Path
    Syntax:  `(?m)^(?=# )` = multiline lookahead — splits BEFORE every line
             that starts with `# ` (an h1), keeping the heading with its section.
    """
    text = src.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^(?=# )", text)
    parts = [p for p in parts if p.strip()]

    pdf = MarkdownPdf(toc_level=3, optimize=True)
    for i, part in enumerate(parts):
        # First section drives the cover; mark all sections toc=True so the
        # TOC always starts at level 1 (PyMuPDF requirement) and every h1
        # becomes a TOC root.
        pdf.add_section(Section(part, toc=True), user_css=CSS)

    pdf.meta["title"] = f"SolarPro Global — {title}"
    pdf.meta["author"] = "SolarPro Global"
    pdf.meta["subject"] = subject
    pdf.save(str(out))
    return out


def main():
    for src_name, out_name, title, subject in DOCS_TO_BUILD:
        src = SRC_DIR / src_name
        out = DOCS / out_name
        render(src, out, title, subject)
        # Mirror to Desktop
        shutil.copy2(out, DESKTOP / out_name)
        print(f"  wrote: {out}")
        print(f"  wrote: {DESKTOP / out_name}")


if __name__ == "__main__":
    main()
