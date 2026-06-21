# patch_email_pdf_a4_borders.py
# The TWO inline MarkdownPdf usages (boq email + price-sheet email) don't
# pass `user_css`, so the email PDF attachments come out un-styled (no A4,
# no dark borders) -- inconsistent with the downloaded PDFs.
#
# Fix: build the same A4 + dark-borders CSS and pass it via user_css.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

CSS_PY = (
    b'        _A4_DARK_CSS = (\r\n'
    b'            "@page { size: A4 portrait; margin: 12mm 10mm 14mm 10mm; }"\r\n'
    b'            "body{font-family:\'Segoe UI\',Arial,sans-serif;color:#111827;font-size:10pt;line-height:1.45;margin:0;padding:0}"\r\n'
    b'            "h1{color:#b45309;font-size:16pt;border-bottom:3px solid #f59e0b;padding-bottom:6px;margin-bottom:10px}"\r\n'
    b'            "h2{color:#1e3a8a;font-size:12pt;border-bottom:1px solid #bfdbfe;padding-bottom:3px;margin-top:14px}"\r\n'
    b'            "h3{color:#374151;font-size:10.5pt;margin-top:10px}"\r\n'
    b'            "table{width:100%;border-collapse:collapse;margin:8px 0;font-size:9pt;border:1.2pt solid #000}"\r\n'
    b'            "th{background:#1e3a5f;color:#fff;padding:5px 7px;text-align:left;border:1px solid #000}"\r\n'
    b'            "td{border:1px solid #000;padding:4px 7px;vertical-align:top}"\r\n'
    b'            "tr:nth-child(even) td{background:#f5f7fb}"\r\n'
    b'        )\r\n'
)

# ---- BOQ email PDF (~ L20596) ----
OLD_BOQ = (
    b'        from markdown_pdf import MarkdownPdf, Section\r\n'
    b'        pdf = MarkdownPdf(toc_level=2)\r\n'
    b'        pdf.add_section(Section(md, toc=False))\r\n'
    b'        import tempfile\r\n'
    b'        tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)\r\n'
    b'        pdf.save(tf.name); tf.close()\r\n'
    b'        with open(tf.name, "rb") as fh:\r\n'
    b'            attachment_bytes = fh.read()\r\n'
)
NEW_BOQ = (
    b'        from markdown_pdf import MarkdownPdf, Section\r\n'
    + CSS_PY +
    b'        pdf = MarkdownPdf(toc_level=2)\r\n'
    b'        pdf.add_section(Section(md, toc=False), user_css=_A4_DARK_CSS)\r\n'
    b'        import tempfile\r\n'
    b'        tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)\r\n'
    b'        pdf.save(tf.name); tf.close()\r\n'
    b'        with open(tf.name, "rb") as fh:\r\n'
    b'            attachment_bytes = fh.read()\r\n'
)

count = data.count(OLD_BOQ)
if count >= 1:
    data = data.replace(OLD_BOQ, NEW_BOQ)
    print(f"OK  {count} inline-MarkdownPdf block(s) wrapped with A4+borders CSS")
else:
    if b"_A4_DARK_CSS" in data:
        print("Already patched")
    else:
        print("WARN  anchor not found")

TARGET.write_bytes(data)
print("OK")
