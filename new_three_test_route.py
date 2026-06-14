# Three.js sanity test endpoint. No auth needed — pure-static page that
# loads the self-hosted Three.js and tries to render one spinning cube.
# Lets us isolate "is Three.js working at all" from "is my shading
# scene broken".


@app.route("/three-test")
def three_test():
    """Minimal Three.js scene to confirm WebGL + Three.js + the
    self-hosted module path are all working on a given browser."""
    return render_template("three_test.html", user=current_user())
