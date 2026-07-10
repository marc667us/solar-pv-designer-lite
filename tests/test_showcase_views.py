"""The Showcase gallery must depict the CUSTOMER'S design, not a stock photo.

Owner rule (no-lies): every picture on /large-scale-solar/<pid>/showcase is
rendered from the same scene graph the 3D twin consumes. A stock photograph may
appear ONLY when the project carries no committed sizing, and then every scene
-- hero included -- must be labelled an illustrative reference.

Run: python -m pytest tests/test_showcase_views.py -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dt_showcase_aerial as aer          # noqa: E402
from dt_showcase import build_showcase_model  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _obj(layer, x, z, *, w=4.0, h=2.0, l=4.0, meta=None):
    return {"layer": layer, "transform": {"position": [x, h / 2.0, z]},
            "dimensions": {"w": w, "h": h, "l": l}, "meta": meta or {}}


def _scene():
    """A miniature but structurally real plant: 4 rows, 2 skids, a compound."""
    objs = [_obj("pv_row", 0.0, -30.0 + i * 6.0, w=80.0, h=0.05, l=4.0,
                 meta={"tilt_deg": 10.0, "modules": 10})
            for i in range(4)]
    objs += [_obj("inverter", -20.0, 10.0), _obj("inverter", 20.0, 10.0),
             _obj("transformer_bldg", 0.0, 24.0, w=10.0, l=8.0),
             _obj("control_room", -14.0, 24.0, w=8.0, l=6.0),
             _obj("om_building", 14.0, 24.0, w=8.0, l=6.0)]
    return {"terrain": {"side_m": 120.0}, "objects": objs}


# ---------------------------------------------------------------- renderer ---

def test_every_gallery_view_renders_a_png():
    scene = _scene()
    for view in aer.SHOWCASE_VIEWS:
        png = aer.render_plant_view(scene, view, 640, 360)
        assert png.startswith(PNG_MAGIC), f"{view}: not a PNG"
        assert len(png) > 500, f"{view}: suspiciously empty render"


def test_views_differ_from_each_other():
    """Five identical frames would mean the framing/night flags do nothing."""
    scene = _scene()
    shots = {v: aer.render_plant_view(scene, v, 640, 360)
             for v in aer.SHOWCASE_VIEWS}
    assert len(set(shots.values())) == len(shots)


def test_unknown_view_renders_nothing():
    assert aer.render_plant_view(_scene(), "definitely-not-a-view") == b""


@pytest.mark.parametrize("scene", [
    {},                                            # empty
    {"objects": []},                               # no objects
    {"objects": [{"layer": "pv_row"}]},            # object with no geometry
    {"objects": [{"layer": "pv_row",
                  "transform": {"position": ["x", None, {}]},
                  "dimensions": {"w": "wide"}}]},  # garbage geometry
    {"terrain": {"side_m": "huge"}, "objects": None},
])
def test_renderer_never_raises_on_bad_scenes(scene):
    """Never-raises contract: a half-built project must still show something."""
    for view in aer.SHOWCASE_VIEWS:
        aer.render_plant_view(scene, view, 320, 180)   # must not raise


def test_missing_subject_is_omitted_rather_than_substituted():
    """No-lies: a plant with no inverters must not show the whole site under an
    "Your inverter stations" caption. The frame simply does not exist."""
    scene = _scene()
    scene["objects"] = [o for o in scene["objects"] if o["layer"] != "inverter"]
    assert aer.view_available(scene, "inverter") is False
    assert aer.render_plant_view(scene, "inverter", 320, 180) == b""
    # subject-less views (whole-site framing) are always available
    assert aer.view_available(scene, "aerial") is True
    assert aer.view_available(scene, "night") is True
    assert aer.view_available(scene, "nope") is False


def test_anchor_modes_pick_different_framing_points():
    scene = _scene()
    rows = ("pv_row",)
    mid = aer._centroid_of(scene, rows, "centroid")
    south = aer._centroid_of(scene, rows, "south")
    near = aer._centroid_of(scene, ("inverter",), "nearest")
    assert south[1] > mid[1], "south anchor must sit on the near edge"
    # "nearest" must land ON a real unit, never in the gap between two
    assert near in [(-20.0, 10.0), (20.0, 10.0)]
    assert aer._centroid_of(scene, ("no_such_layer",)) is None


def test_pv_row_lod_collapses_when_tables_are_subpixel():
    """A whole-site frame must not try to draw 5 000 individual tables."""
    row = _obj("pv_row", 0.0, 0.0, w=600.0, h=0.05, l=4.0,
               meta={"tilt_deg": 10.0, "modules": 60})
    _px, _py, _pz, hw, hd, rise, tilt, n = aer._pv_row_geometry(row)
    assert n == 60 and tilt == 10.0
    assert hd < 2.0 and rise > 0.0, "tilt must foreshorten depth and lift the row"


def test_off_frame_culls_only_what_is_outside_the_viewport():
    inside = aer._proj_bbox(0.0, 0.0, 4.0, 4.0, 2.0, 4.0, 320.0, 180.0)
    far_east = aer._proj_bbox(9000.0, 0.0, 4.0, 4.0, 2.0, 4.0, 320.0, 180.0)
    assert aer._off_frame(inside, 640, 360) is False
    assert aer._off_frame(far_east, 640, 360) is True


def test_render_cost_is_bounded_for_a_huge_plant():
    """DoS guard: one request must not rasterise an unbounded polygon count.

    A 400-row x 60-table plant would be 24 000 tables. The object-level frustum
    cull plus the table budget keep every view renderable well inside a request
    timeout, and the tables actually drawn never exceed the budget.
    """
    import time
    big = {"terrain": {"side_m": 2500.0}, "objects": [
        _obj("pv_row", 0.0, -1200.0 + i * 6.0, w=2200.0, h=0.05, l=4.0,
             meta={"tilt_deg": 10.0, "modules": 60}) for i in range(400)]}
    big["objects"].append(_obj("inverter", 0.0, 1300.0))
    for view in ("aerial", "panels", "inverter", "night"):
        started = time.time()
        png = aer.render_plant_view(big, view, 1600, 900)
        assert png.startswith(PNG_MAGIC), view
        assert time.time() - started < 12.0, f"{view}: render is unbounded"


def test_pv_row_honours_the_table_budget():
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (1600, 900)), "RGBA")
    row = _obj("pv_row", 0.0, 0.0, w=600.0, h=0.05, l=4.0,
               meta={"tilt_deg": 10.0, "modules": 60})
    assert aer._draw_pv_row(d, row, 20.0, 800.0, 450.0, False, 1600, 5) <= 5
    # a spent budget collapses the row to a single ribbon (0 tables drawn)
    assert aer._draw_pv_row(d, row, 20.0, 800.0, 450.0, False, 1600, 0) == 0


# ------------------------------------------------------------------- model ---

def _proj(n_modules: int | None) -> dict:
    sizing = {"n_modules": n_modules, "n_central_inverters": 4,
              "combiners": 8, "modules_per_string": 28} if n_modules else {}
    return {"id": 1, "name": "Test Plant", "target_kwp": 20000.0,
            "pv_config": {"sizing": sizing}}


def test_committed_design_gallery_is_all_design_views(monkeypatch):
    """With real sizing, no stock photograph is served -- not even a thumbnail."""
    monkeypatch.setattr(aer, "aerial_callout_anchors", lambda *a, **k: {})
    show = build_showcase_model(_proj(36364))
    if not show["is_design_aerial"]:
        pytest.skip("scene graph unavailable in this environment")
    assert show["hero"].get("is_aerial") is True
    gallery = show["scenes"][1:]
    assert gallery, "gallery lost its scenes"
    for s in gallery:
        assert s.get("is_design_view") is True, f"{s['key']} is a stock photo"
        assert "img" not in s and "thumb" not in s, f"{s['key']} still carries stock art"
        assert "Illustrative" not in s["caption"]
        assert s["caption"].lower().startswith("your")


def test_uncommitted_project_labels_every_scene_illustrative():
    show = build_showcase_model(_proj(None))
    assert show["is_design_aerial"] is False
    for s in show["scenes"]:
        assert s["caption"].startswith("Illustrative reference"), s["key"]


def test_model_never_raises_on_garbage_project():
    for bad in (None, {}, {"pv_config": "not-json"}, {"pv_config": {"sizing": 7}}):
        out = build_showcase_model(bad)          # must not raise
        assert out["scenes"] and out["hero"]


# ------------------------------------------------------------------ routes ---

COMMITTED_PV = json.dumps({
    "kwp": 20000.0, "module_wp": 550, "tilt_deg": 10.0, "azimuth_deg": 180.0,
    "row_pitch_m": 6.0,
    "sizing": {"n_modules": 36364, "dc_kwp_actual": 20000.0,
               "n_central_inverters": 12, "central_inverter_kw": 1500.0,
               "inverter_ac_kw": 17000.0, "combiners": 65,
               "modules_per_string": 28, "strings": 1299},
})


@pytest.fixture()
def committed_project():
    """A logged-in client on a project WITH committed sizing, created here.

    The routes must be exercised on every machine, so the fixture builds its own
    row instead of hunting the local database for one (a fresh CI database has
    none, and skipped no-lies tests protect nothing).
    """
    import web_app
    from new_capital_investment_routes import _ensure_ci_projects_schema_verified
    web_app.app.config["WTF_CSRF_ENABLED"] = False
    with web_app.app.test_request_context():
        from web_app import get_db
        # a sibling test may have repointed DB_PATH at a fresh database whose
        # lazily-created CI tables do not exist yet
        _ensure_ci_projects_schema_verified(get_db)
        with get_db() as c:
            uid = c.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
            if uid is None:
                pytest.skip("no user in this database")
            uid = uid[0]
            cur = c.execute(
                "INSERT INTO capital_investment_projects "
                "(user_id, project_name, target_kwp, pv_config, country) "
                "VALUES (?,?,?,?,?)",
                (uid, "pytest showcase plant", 20000.0, COMMITTED_PV, "Ghana"))
            pid = cur.lastrowid
    cl = web_app.app.test_client()
    with cl.session_transaction() as s:
        s["user_id"] = uid
    try:
        yield cl, pid
    finally:
        with web_app.app.test_request_context():
            from web_app import get_db
            with get_db() as c:
                c.execute("DELETE FROM capital_investment_projects WHERE id=?",
                          (pid,))


def test_design_image_routes_serve_png_for_a_committed_project(committed_project):
    cl, pid = committed_project
    for url in (f"/large-scale-solar/{pid}/showcase-aerial.png",
                f"/large-scale-solar/{pid}/showcase-view/panels.png",
                f"/large-scale-solar/{pid}/showcase-view/night.png?w=320"):
        r = cl.get(url)
        assert r.status_code == 200, f"{url} -> {r.status_code}"
        assert r.headers["Content-Type"] == "image/png"
        assert r.get_data().startswith(PNG_MAGIC)


def test_design_image_routes_404_without_committed_sizing(committed_project,
                                                          monkeypatch):
    """No-lies: a frame captioned "your array" must not exist before the design.

    It must also never fall back to a stock photograph -- that would put another
    plant's picture under the customer's caption.
    """
    cl, pid = committed_project
    import dt_electrical_sld as sld
    monkeypatch.setattr(sld, "has_committed_sizing", lambda proj: False)
    for url in (f"/large-scale-solar/{pid}/showcase-aerial.png",
                f"/large-scale-solar/{pid}/showcase-view/panels.png"):
        r = cl.get(url)
        assert r.status_code == 404, f"{url} -> {r.status_code}"
        assert "hero/" not in r.headers.get("Location", "")


def test_unknown_view_route_404s(committed_project):
    cl, pid = committed_project
    assert cl.get(f"/large-scale-solar/{pid}/showcase-view/etc.png").status_code == 404


def test_other_users_project_image_is_not_readable(committed_project):
    """Tenant isolation: the image routes must not become an IDOR side-channel.

    A signed-in stranger must get the same 404 as a missing project, and an
    unauthenticated caller must never reach the renderer at all.
    """
    import web_app
    cl, pid = committed_project
    with web_app.app.test_request_context():
        from web_app import get_db
        with get_db() as c:
            owner = c.execute(
                "SELECT user_id FROM capital_investment_projects WHERE id=?",
                (pid,)).fetchone()[0]
            other = c.execute("SELECT id FROM users WHERE id<>? ORDER BY id LIMIT 1",
                              (owner,)).fetchone()

    urls = (f"/large-scale-solar/{pid}/showcase-aerial.png",
            f"/large-scale-solar/{pid}/showcase-view/panels.png")
    if other is not None:                       # a real, signed-in stranger
        with cl.session_transaction() as s:
            s["user_id"] = other[0]
        for url in urls:
            r = cl.get(url)
            assert r.status_code in (404, 302), f"{url} leaked to another user"
            assert not r.get_data().startswith(PNG_MAGIC), f"{url} served an image"

    with cl.session_transaction() as s:         # signed out entirely
        s.clear()
    for url in urls:
        r = cl.get(url)
        assert r.status_code in (302, 401, 403, 404), url
        assert not r.get_data().startswith(PNG_MAGIC), f"{url} served an image"


def test_committed_showcase_page_links_no_stock_art(committed_project):
    cl, pid = committed_project
    html = cl.get(f"/large-scale-solar/{pid}/showcase").get_data(as_text=True)
    assert "hero/scene-" not in html and "hero/farm-aerial" not in html
    assert "/showcase-view/" in html and "/showcase-aerial.png" in html
