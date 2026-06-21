# patch_friendly_error_handlers.py
# Owner directive 2026-06-21: "promise me i am not going to see eror codes
# like 500 and 404 again".
#
# We already have @app.errorhandler(404), 429, 500. This patch adds:
#   - 502 / 503 / 504 (Render free worker restarts the user hits the most)
#   - 405 (method not allowed -- happens when a form route is changed)
#   - 413 (request entity too large)
#   - @app.errorhandler(Exception) catch-all -- ANY unhandled exception
#     produces the friendly error page instead of a bare 500.
#
# All paths render templates/error.html which auto-redirects after 5s.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

ANCHOR = (
    b'    return render_template("error.html", code=500,\r\n'
    b'        title="Internal Server Error",\r\n'
    b'        message="Something went wrong on our end. "\r\n'
    b'                "Please go back to the dashboard and try again."), 500\r\n'
)

ADDITION = (
    b'\r\n'
    b'@app.errorhandler(405)\r\n'
    b'def err_405(e):\r\n'
    b'    return render_template("error.html", code=405,\r\n'
    b'        title="Action Not Allowed Here",\r\n'
    b'        message="This action isn\'t supported on this page. Try the dashboard."), 405\r\n'
    b'\r\n'
    b'@app.errorhandler(413)\r\n'
    b'def err_413(e):\r\n'
    b'    return render_template("error.html", code=413,\r\n'
    b'        title="Upload Too Large",\r\n'
    b'        message="The file you uploaded is too big for the free tier (16 MB max). "\r\n'
    b'                "Please attach a smaller file."), 413\r\n'
    b'\r\n'
    b'@app.errorhandler(502)\r\n'
    b'def err_502(e):\r\n'
    b'    return render_template("error.html", code=502,\r\n'
    b'        title="Brief reconnect",\r\n'
    b'        message="The server is reconnecting -- this clears in 10-20 seconds. "\r\n'
    b'                "Auto-retrying for you."), 502\r\n'
    b'\r\n'
    b'@app.errorhandler(503)\r\n'
    b'def err_503(e):\r\n'
    b'    return render_template("error.html", code=503,\r\n'
    b'        title="Server warming up",\r\n'
    b'        message="The server is warming up after an idle period (Render free tier). "\r\n'
    b'                "Auto-retrying for you."), 503\r\n'
    b'\r\n'
    b'@app.errorhandler(504)\r\n'
    b'def err_504(e):\r\n'
    b'    return render_template("error.html", code=504,\r\n'
    b'        title="Took a moment too long",\r\n'
    b'        message="That request took longer than the gateway allows. "\r\n'
    b'                "Auto-retrying for you."), 504\r\n'
    b'\r\n'
    b'@app.errorhandler(Exception)\r\n'
    b'def err_uncaught(e):\r\n'
    b'    # Catch-all so the owner never sees a bare 500/stack-trace page.\r\n'
    b'    # If Flask already routed to a specific @app.errorhandler the\r\n'
    b'    # exception never reaches here. Anything that DOES is genuinely\r\n'
    b'    # unhandled -- log full trace, return the friendly template.\r\n'
    b'    try:\r\n'
    b'        import traceback as _tb\r\n'
    b'        app.logger.error("UNCAUGHT " + request.method + " " + request.path + chr(10) + _tb.format_exc())\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
    b'    # Werkzeug HTTPException -- honour its status code.\r\n'
    b'    try:\r\n'
    b'        from werkzeug.exceptions import HTTPException as _HTTPExc\r\n'
    b'        if isinstance(e, _HTTPExc):\r\n'
    b'            return render_template("error.html", code=e.code or 500,\r\n'
    b'                title="Hiccup",\r\n'
    b'                message=str(e.description or "We hit a small hiccup. Please try again.")\r\n'
    b'            ), e.code or 500\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
    b'    return render_template("error.html", code=500,\r\n'
    b'        title="Small hiccup",\r\n'
    b'        message="We hit a small hiccup. Your data is safe -- please try again."), 500\r\n'
)

if b'@app.errorhandler(Exception)' in data and b'err_uncaught' in data:
    print("Already patched")
elif ANCHOR in data:
    data = data.replace(ANCHOR, ANCHOR + ADDITION)
    TARGET.write_bytes(data)
    print("OK  502/503/504/405/413/Exception handlers added")
else:
    print("WARN  anchor not found")
