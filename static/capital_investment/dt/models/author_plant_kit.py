"""Author a self-hosted, engineering-detailed GLB equipment kit for the
Generation-Station twin (Slice 2). Named root nodes: pv_table, inverter,
transformer, substation. Y-up, metres, base near y=0, centred in X/Z.

Fidelity approach: each equipment root is ONE concatenated mesh carrying BAKED
PER-VERTEX COLOURS (ColorVisuals). Vertex colours survive the GLB round-trip
(verified) and render on a MeshStandardMaterial via GLTFLoader, so a single
node can show many materials WITHOUT changing dt-glb-models.js (which loads one
node per equipment). Detail comes from real component geometry (radiators,
bushings, conservator, louvers, doors, windows, gantry) instead of ~4 boxes.

Regenerate:  python static/capital_investment/dt/models/author_plant_kit.py
Output:      static/capital_investment/dt/models/plant-kit.glb  (git-tracked)
"""
import os
import numpy as np
import trimesh
from trimesh.transformations import rotation_matrix, concatenate_matrices

# --- vertex-colour primitive helpers -------------------------------------
def _colorize(mesh, rgb):
    c = np.tile(np.array([rgb[0], rgb[1], rgb[2], 255], dtype=np.uint8),
                (len(mesh.vertices), 1))
    mesh.visual = trimesh.visual.ColorVisuals(mesh, vertex_colors=c)
    return mesh

def box(ext, x=0.0, y=0.0, z=0.0, rgb=(128, 128, 128), xf=None):
    m = trimesh.creation.box(extents=ext)
    if xf is not None:
        m.apply_transform(xf)
    m.apply_translation([x, y, z])
    return _colorize(m, rgb)

def cyl(r, h, x=0.0, y=0.0, z=0.0, rgb=(128, 128, 128), axis="y"):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=16)
    if axis == "x":
        m.apply_transform(rotation_matrix(np.radians(90), [0, 1, 0]))
    elif axis == "z":
        m.apply_transform(rotation_matrix(np.radians(90), [1, 0, 0]))
    m.apply_translation([x, y, z])
    return _colorize(m, rgb)

def combine(parts):
    return trimesh.util.concatenate(parts)

# palette (0-255)
GREEN   = (58, 105, 74);   GREEN_D = (46, 86, 60)
STEEL   = (150, 158, 150); STEEL_D = (120, 126, 122)
PORC    = (222, 214, 158)
CREAM   = (200, 195, 170)
GREY_L  = (205, 208, 212); GREY_M = (150, 153, 158); GREY_D = (95, 99, 106)
CONC    = (122, 118, 108)
WALL    = (196, 190, 175); ROOF = (140, 143, 148)
DARK    = (55, 60, 68)
GLASS   = (60, 92, 122)
PANEL   = (18, 30, 72);    ALU = (156, 165, 176)
YELLOW  = (232, 200, 44)
DOORBR  = (92, 80, 66)

# --- TRANSFORMER: tank + radiators + bushings + conservator + plinth ------
def build_transformer():
    p = []
    p.append(box([3.0, 0.22, 2.6], 0, 0.11, 0, CONC))                 # gravel plinth
    # oil-bund kerb (thin low frame around plinth)
    for (dx, dz, w, l) in [(0, 1.32, 3.0, 0.12), (0, -1.32, 3.0, 0.12),
                           (1.5, 0, 0.12, 2.6), (-1.5, 0, 0.12, 2.6)]:
        p.append(box([w, 0.35, l], dx, 0.28, dz, GREY_D))
    p.append(box([2.0, 2.0, 1.6], 0, 1.35, 0, GREEN))                 # tank
    p.append(box([2.12, 0.16, 1.72], 0, 2.4, 0, GREEN_D))             # tank lid
    # corrugated radiator fins on both long sides
    for side in (1.06, -1.06):
        for i in range(7):
            z = -1.05 + i * 0.35
            p.append(box([0.10, 1.5, 0.28], side, 1.35, z, STEEL))
    # conservator drum across the top
    p.append(cyl(0.34, 1.6, 0, 2.95, 0.55, CREAM, axis="x"))
    # 3 HV porcelain bushings on top
    for dx in (-0.6, 0.0, 0.6):
        p.append(cyl(0.09, 0.8, dx, 2.75, -0.2, PORC))
    # 3 LV bushings (smaller) toward the front
    for dx in (-0.5, 0.0, 0.5):
        p.append(cyl(0.06, 0.45, dx, 2.45, 0.85, PORC))
    p.append(box([0.5, 0.7, 0.35], 1.05, 1.6, 0.9, GREY_M))           # LV terminal box
    p.append(box([0.32, 0.32, 0.03], 0, 1.4, 0.81, YELLOW))           # danger sign
    return combine(p)

# --- INVERTER SKID: plinth + body + louvers + door + roof canopy ----------
def build_inverter():
    p = []
    p.append(box([6.4, 0.3, 2.9], 0, 0.15, 0, CONC))                  # plinth
    p.append(box([6.0, 2.4, 2.6], 0, 1.5, 0, GREY_L))                 # container body
    p.append(box([6.3, 0.16, 2.86], 0, 2.78, 0, GREY_M))             # roof canopy overhang
    # louver banks on the front face (recessed dark strips)
    for i in range(5):
        x = -2.2 + i * 1.1
        p.append(box([0.85, 1.1, 0.06], x, 1.55, 1.31, DARK))
    p.append(box([1.0, 2.0, 0.06], -2.55, 1.05, 1.31, GREY_D))        # access door
    p.append(box([0.14, 1.0, 0.04], -2.15, 1.05, 1.34, STEEL))       # door handle rail
    p.append(box([0.9, 0.6, 0.45], 2.9, 0.7, 0.9, GREY_D))           # cable-entry box
    p.append(box([0.9, 0.32, 0.03], 1.6, 2.15, 1.32, YELLOW))         # signage
    return combine(p)

# --- SUBSTATION / CONTROL BUILDING: walls + roof + windows + gantry -------
def build_substation():
    p = []
    p.append(box([8.0, 4.0, 5.0], 0, 2.0, 0, WALL))                   # walls
    p.append(box([8.5, 0.4, 5.5], 0, 4.15, 0, ROOF))                 # parapet roof
    for dx in (-2.2, 2.2):                                            # roof AC units
        p.append(box([1.1, 0.6, 1.1], dx, 4.55, -0.5, GREY_M))
    p.append(box([1.5, 2.5, 0.12], 0, 1.25, 2.55, DOORBR))           # door
    p.append(box([2.0, 0.3, 0.7], 0, 0.15, 2.95, CONC))             # entrance step
    for dx in (-2.6, -0.9, 0.9, 2.6):                                 # front windows
        p.append(box([1.2, 1.1, 0.08], dx, 2.5, 2.53, GLASS))
    # gantry kept WITHIN the 8 m building width so placeModel's bbox-width scaling
    # (dt-glb-models) does not shrink the whole building to fit an over-wide beam.
    for dx in (-3.5, 3.5):                                            # gantry posts
        p.append(box([0.26, 5.4, 0.26], dx, 2.7, -1.2, STEEL_D))
    p.append(box([7.6, 0.3, 0.3], 0, 5.4, -1.2, STEEL_D))            # gantry beam
    return combine(p)

# --- PV TABLE: framed tilted panel on torque tube + 2 posts ---------------
def build_pv_table():
    tilt = np.radians(15)
    Rt = rotation_matrix(tilt, [1, 0, 0])
    p = []
    # aluminium frame ring (4 bars) + dark laminate, all tilted together
    Xf = concatenate_matrices(rotation_matrix(0, [0, 0, 1]))  # identity base
    # dark panel
    panel = box([4.0, 0.05, 2.0], 0, 1.4, 0, PANEL, xf=Rt)
    p.append(panel)
    # frame bars (slightly proud of the laminate)
    for (w, l, dx, dz) in [(4.12, 0.10, 0, 1.02), (4.12, 0.10, 0, -1.02),
                           (0.10, 2.04, 2.02, 0), (0.10, 2.04, -2.02, 0)]:
        bar = trimesh.creation.box(extents=[w, 0.09, l])
        bar.apply_transform(Rt)
        # place around the tilted panel centre
        off = np.array([dx, 1.4, dz, 1.0])
        rot_off = Rt @ off
        bar.apply_translation([rot_off[0], rot_off[1], rot_off[2]])
        p.append(_colorize(bar, ALU))
    p.append(cyl(0.05, 4.0, 0, 1.2, 0, STEEL, axis="x"))              # torque tube
    p.append(box([0.09, 1.2, 0.09], -1.3, 0.6, 0, STEEL_D))           # post 1
    p.append(box([0.09, 1.2, 0.09], 1.3, 0.6, 0, STEEL_D))            # post 2
    return combine(p)

# --- assemble scene -------------------------------------------------------
scene = trimesh.Scene()
scene.add_geometry(build_pv_table(),   node_name="pv_table",   geom_name="pv_table")
scene.add_geometry(build_inverter(),   node_name="inverter",   geom_name="inverter")
scene.add_geometry(build_transformer(),node_name="transformer",geom_name="transformer")
scene.add_geometry(build_substation(), node_name="substation", geom_name="substation")

out = "static/capital_investment/dt/models/plant-kit.glb"
scene.export(out)
print("exported", out, os.path.getsize(out) // 1024, "KB")
print("nodes:", list(scene.graph.nodes_geometry))
for name, g in scene.geometry.items():
    print("  ", name, "verts", len(g.vertices), "faces", len(g.faces))
