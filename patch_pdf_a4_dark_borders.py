# patch_pdf_a4_dark_borders.py
# Owner directive 2026-06-21: "all boqs must be a4, and formated with border
# line solide dark and betwen each columns, do for all reports pdf, print
# excel".
#
# This patch updates ONE central CSS block in web_app.py's _render_pdf().
# Every PDF rendered through markdown-pdf inherits it.
#
# Changes:
#   - @page size A4 portrait, 12 mm margin
#   - table border-collapse + solid 1px #000 outer border
#   - th/td border 1px solid #000 (was light grey 1px #e5e7eb)
#   - th: dark navy background, white text, padding tightened
#   - alt-row striping retained but lightened so it doesn't fight the borders
#   - print-friendly font sizes (10pt body, 9pt table)
#
# We replace the WHOLE CSS string between `CSS = """` and the closing
# `"""` so it stays one atomic edit.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

OLD = (
    b'    CSS = """\r\n'
    b"    body{font-family:'Segoe UI',Arial,sans-serif;color:#111827;font-size:11pt;line-height:1.55;margin:0;padding:0}\r\n"
    b"    h1{color:#b45309;font-size:17pt;border-bottom:3px solid #f59e0b;padding-bottom:8px;margin-bottom:14px}\r\n"
    b"    h2{color:#1e3a8a;font-size:13pt;border-bottom:1px solid #bfdbfe;padding-bottom:4px;margin-top:20px}\r\n"
    b"    h3{color:#374151;font-size:11pt;margin-top:14px}\r\n"
    b"    table{width:100%;border-collapse:collapse;margin:10px 0;font-size:10pt}\r\n"
    b"    th{background:#1e3a5f;color:#fff;padding:7px 10px;text-align:left}\r\n"
    b"    td{border:1px solid #e5e7eb;padding:5px 10px}\r\n"
    b"    tr:nth-child(even){background:#f8fafc}\r\n"
    b"    blockquote{background:#f0fdf4;border-left:4px solid #22c55e;padding:10px 16px;margin:8px 0;border-radius:4px}\r\n"
    b"    .warn{background:#fffbeb;border-left:4px solid #f59e0b;padding:10px 16px;margin:8px 0;border-radius:4px}\r\n"
    b"    .danger{background:#fef2f2;border-left:4px solid #ef4444;padding:10px 16px;margin:8px 0;border-radius:4px}\r\n"
    b"    p{margin:5px 0}\r\n"
    b"    hr{border:none;border-top:1px solid #e5e7eb;margin:14px 0}\r\n"
    b"    code{background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:10pt}\r\n"
    b'    """\r\n'
)

NEW = (
    b'    CSS = """\r\n'
    b"    @page { size: A4 portrait; margin: 12mm 10mm 14mm 10mm; }\r\n"
    b"    body{font-family:'Segoe UI',Arial,sans-serif;color:#111827;font-size:10pt;line-height:1.45;margin:0;padding:0}\r\n"
    b"    h1{color:#b45309;font-size:16pt;border-bottom:3px solid #f59e0b;padding-bottom:6px;margin-bottom:10px}\r\n"
    b"    h2{color:#1e3a8a;font-size:12pt;border-bottom:1px solid #bfdbfe;padding-bottom:3px;margin-top:14px}\r\n"
    b"    h3{color:#374151;font-size:10.5pt;margin-top:10px}\r\n"
    b"    table{width:100%;border-collapse:collapse;margin:8px 0;font-size:9pt;border:1.2pt solid #000}\r\n"
    b"    th{background:#1e3a5f;color:#fff;padding:5px 7px;text-align:left;border:1px solid #000}\r\n"
    b"    td{border:1px solid #000;padding:4px 7px;vertical-align:top}\r\n"
    b"    tr:nth-child(even) td{background:#f5f7fb}\r\n"
    b"    blockquote{background:#f0fdf4;border-left:4px solid #22c55e;padding:8px 12px;margin:6px 0;border-radius:3px}\r\n"
    b"    .warn{background:#fffbeb;border-left:4px solid #f59e0b;padding:8px 12px;margin:6px 0;border-radius:3px}\r\n"
    b"    .danger{background:#fef2f2;border-left:4px solid #ef4444;padding:8px 12px;margin:6px 0;border-radius:3px}\r\n"
    b"    p{margin:4px 0}\r\n"
    b"    hr{border:none;border-top:1px solid #444;margin:10px 0}\r\n"
    b"    code{background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:9pt}\r\n"
    b'    """\r\n'
)

if OLD in data:
    data = data.replace(OLD, NEW)
    TARGET.write_bytes(data)
    print("OK — _render_pdf CSS upgraded: A4 + solid dark borders")
elif b"@page { size: A4 portrait;" in data:
    print("Already patched — A4 marker present")
else:
    print("WARN — CSS anchor not found verbatim. No change.")
