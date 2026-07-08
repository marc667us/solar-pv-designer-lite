"""Author a self-hosted PBR GLB equipment kit for the Generation-Station twin.
Named root nodes: pv_table, inverter, transformer, substation. Y-up, metres."""
import numpy as np, trimesh
from trimesh.visual.material import PBRMaterial

def mat(rgb, metal=0.2, rough=0.7):
    return PBRMaterial(baseColorFactor=[rgb[0],rgb[1],rgb[2],1.0],
                       metallicFactor=metal, roughnessFactor=rough)

def box(ext, xf=None, color=(0.5,0.5,0.5), metal=0.2, rough=0.7):
    m = trimesh.creation.box(extents=ext)
    if xf is not None: m.apply_transform(xf)
    m.visual = trimesh.visual.TextureVisuals(material=mat(color, metal, rough))
    return m

def cyl(r, h, xf=None, color=(0.5,0.5,0.5), metal=0.6, rough=0.4):
    m = trimesh.creation.cylinder(radius=r, height=h, sections=16)
    if xf is not None: m.apply_transform(xf)
    m.visual = trimesh.visual.TextureVisuals(material=mat(color, metal, rough))
    return m

def T(x,y,z):
    m=np.eye(4); m[:3,3]=[x,y,z]; return m

def combine(parts):
    return trimesh.util.concatenate(parts)

# --- PV TABLE: 2P tilted panel on torque tube + 2 legs (approx 4m x 2m) ---
tilt=np.radians(12)
panel = trimesh.creation.box(extents=[4.0,0.05,2.0])
Rt=trimesh.transformations.rotation_matrix(tilt,[1,0,0]); Rt[:3,3]=[0,1.4,0]
panel.apply_transform(Rt); panel.visual=trimesh.visual.TextureVisuals(material=mat((0.09,0.13,0.30),0.5,0.25))
tube = cyl(0.05,4.0, trimesh.transformations.concatenate_matrices(T(0,1.25,0),trimesh.transformations.rotation_matrix(np.radians(90),[0,0,1])), (0.7,0.72,0.75),0.8,0.4)
leg1 = box([0.08,1.25,0.08], T(-1.3,0.62,0),(0.6,0.62,0.66),0.7,0.5)
leg2 = box([0.08,1.25,0.08], T( 1.3,0.62,0),(0.6,0.62,0.66),0.7,0.5)
pv_table = combine([panel,tube,leg1,leg2])

# --- INVERTER SKID: container + louver stripe + plinth (approx 6 x 2.6 x 2.6) ---
body = box([6.0,2.4,2.6], T(0,1.3,0),(0.82,0.84,0.86),0.35,0.55)
louv = box([2.2,1.2,0.06], T(1.4,1.3,1.33),(0.28,0.30,0.34),0.5,0.6)
plinth = box([6.4,0.3,2.9], T(0,0.15,0),(0.35,0.36,0.38),0.1,0.9)
roof = box([6.1,0.12,2.7], T(0,2.56,0),(0.6,0.62,0.66),0.4,0.5)
inverter = combine([plinth,body,roof,louv])

# --- TRANSFORMER: tank + 3 HV bushings + radiator fins (approx 2.2 x 2.4 x 2) ---
tank = box([2.2,2.0,1.8], T(0,1.2,0),(0.30,0.42,0.34),0.6,0.4)  # utility green
tanklid = box([2.3,0.15,1.9], T(0,2.25,0),(0.28,0.38,0.32),0.6,0.4)
bush=[]
for i,dx in enumerate([-0.6,0.0,0.6]):
    bush.append(cyl(0.09,0.7, T(dx,2.6,0),(0.85,0.82,0.6),0.2,0.3))  # porcelain
fins=[]
for dx in [-1.18,1.18]:
    fins.append(box([0.12,1.6,1.5], T(dx,1.2,0),(0.5,0.55,0.5),0.6,0.5))
transformer = combine([tank,tanklid]+bush+fins)

# --- SUBSTATION: control building + gantry (approx 8 x 4 x 5) ---
bldg = box([8.0,4.0,5.0], T(0,2.0,0),(0.80,0.80,0.82),0.15,0.7)
roof2 = box([8.4,0.3,5.4], T(0,4.15,0),(0.5,0.52,0.55),0.3,0.6)
door = box([1.4,2.4,0.1], T(0,1.2,2.55),(0.3,0.32,0.36),0.4,0.6)
posts=[]
for dx in [-5.5,5.5]:
    posts.append(box([0.25,6.0,0.25], T(dx,3.0,-1.0),(0.55,0.57,0.6),0.7,0.5))
beam = box([11.5,0.3,0.3], T(0,6.0,-1.0),(0.55,0.57,0.6),0.7,0.5)
substation = combine([bldg,roof2,door,beam]+posts)

scene = trimesh.Scene()
scene.add_geometry(pv_table, node_name='pv_table', geom_name='pv_table')
scene.add_geometry(inverter, node_name='inverter', geom_name='inverter')
scene.add_geometry(transformer, node_name='transformer', geom_name='transformer')
scene.add_geometry(substation, node_name='substation', geom_name='substation')

out='static/capital_investment/dt/models/plant-kit.glb'
scene.export(out)
import os
print('exported', out, os.path.getsize(out)//1024, 'KB')
print('nodes:', list(scene.graph.nodes_geometry))
