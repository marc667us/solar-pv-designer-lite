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
body { font-family: 'Segoe UI', Calibri, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1a1a1a; }
h1 { font-size: 22pt; color: #1f5fb8; border-bottom: 3px solid #1f5fb8; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 15pt; color: #2a6fcc; margin-top: 22px; border-bottom: 1px solid #d8e3f0; padding-bottom: 3px; }
h3 { font-size: 12.5pt; color: #333; margin-top: 14px; }
h4 { font-size: 11pt; color: #555; margin-bottom: 4px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }
th { background: #1f5fb8; color: #fff; text-align: left; padding: 5px 8px; }
td { border: 1px solid #d8e3f0; padding: 5px 8px; vertical-align: top; }
tr:nth-child(even) td { background: #f4f8fd; }
code { background: #f4f2ef; padding: 1px 4px; border-radius: 3px; font-family: Consolas, monospace; font-size: 9.5pt; }
pre { background: #f7f5f2; border: 1px solid #e0dcd5; border-left: 3px solid #1f5fb8; padding: 10px 12px; border-radius: 4px; font-size: 9pt; line-height: 1.4; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #ffcb6b; background: #fffbf2; margin: 10px 0; padding: 6px 14px; color: #444; font-style: italic; }
strong { color: #1a1a1a; }
a { color: #1f5fb8; }
hr { border: none; border-top: 1px solid #ddd; margin: 18px 0; }
ul, ol { margin: 8px 0; }
li { margin: 3px 0; }
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
