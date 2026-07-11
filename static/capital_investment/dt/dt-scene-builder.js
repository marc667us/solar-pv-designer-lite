/* dt-scene-builder.js -- build the Three.js scene from scene.objects (Phase 1).
 *
 * Consumes the normalized dt_scene_v2 `objects` array and produces:
 *   - one THREE.Group per layer code (for fast visibility toggles),
 *   - a single InstancedMesh for all PV rows (proxy picking via instanceId --
 *     this is what keeps a 100MW / 181k-module farm renderable),
 *   - individual meshes for buildings / inverters / masts / terrain / fence,
 *   - a populated DT.objectIndex (id -> {object, mesh, instanceId}).
 *
 * rebuild() disposes the previous scene content so a live parameter change
 * (Phase 3) can swap geometry without leaking GPU memory or reloading the page.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var _sceneryMats = null;   // trunk/canopy materials, created once + reused

  function group(layer) {
    var t = DT.three;
    if (t.layerGroups[layer]) return t.layerGroups[layer];
    var THREE = window.THREE;
    var g = new THREE.Group();
    g.userData.layerCode = layer;
    g.visible = !DT.state.hiddenLayers[layer];
    t.scene.add(g);
    t.layerGroups[layer] = g;
    return g;
  }

  function euler(rotDeg) {
    var THREE = window.THREE, d = Math.PI / 180;
    var r = rotDeg || [0, 0, 0];
    return new THREE.Euler((r[0] || 0) * d, (r[1] || 0) * d, (r[2] || 0) * d, 'XYZ');
  }

  function tierShadows() { return (DT.state.graphicsTier || 'medium') !== 'low'; }

  // ---- procedural textures (self-contained; CSP blocks external images) ----
  var _texCache = {};

  // Tiled grass: base green with per-pixel noise speckle + faint mottling so the
  // ground reads as vegetation instead of a flat plane. Cached + repeat-wrapped.
  function grassTexture() {
    if (_texCache.grass) return _texCache.grass;
    var THREE = window.THREE, S = 256;
    var c = document.createElement('canvas'); c.width = c.height = S;
    var ctx = c.getContext('2d');
    ctx.fillStyle = '#3f6f28'; ctx.fillRect(0, 0, S, S);   // richer field green
    var img = ctx.getImageData(0, 0, S, S), d = img.data;
    for (var i = 0; i < d.length; i += 4) {
      var n = (Math.random() - 0.5) * 46;          // fine grain
      var m = (Math.random() < 0.04) ? -28 : 0;    // sparse darker tufts
      d[i] = Math.max(0, Math.min(255, d[i] + n * 0.7 + m));
      d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + n + m));
      d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + n * 0.5 + m));
    }
    ctx.putImageData(img, 0, 0);
    var tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    _texCache.grass = tex;
    return tex;
  }

  // Ground micro-relief bump map: smoothed mid-frequency grayscale noise so the
  // hard sun rakes across soil/grass unevenness instead of a perfectly flat
  // sheet (the classic "toy terrain" tell). Height-only bump (not displacement),
  // so the ground geometry stays flat and panels/legs never float. Tiles with
  // the grass albedo. Cached + repeat-wrapped.
  function groundBumpTexture() {
    if (_texCache.groundBump) return _texCache.groundBump;
    var THREE = window.THREE, S = 128;
    var c = document.createElement('canvas'); c.width = c.height = S;
    var ctx = c.getContext('2d');
    // start mid-gray, drop a few dozen soft light/dark blobs, then a light grain.
    ctx.fillStyle = '#808080'; ctx.fillRect(0, 0, S, S);
    for (var b = 0; b < 42; b++) {
      var x = Math.random() * S, y = Math.random() * S, rr = 6 + Math.random() * 20;
      var lum = Math.random() < 0.5 ? 255 : 0;
      var rg = ctx.createRadialGradient(x, y, 0, x, y, rr);
      rg.addColorStop(0, 'rgba(' + lum + ',' + lum + ',' + lum + ',0.16)');
      rg.addColorStop(1, 'rgba(' + lum + ',' + lum + ',' + lum + ',0)');
      ctx.fillStyle = rg; ctx.beginPath(); ctx.arc(x, y, rr, 0, 6.2832); ctx.fill();
    }
    var tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    _texCache.groundBump = tex;
    return tex;
  }

  // PV module face: dark-blue cell grid with thin silver mullions + a bright
  // specular streak, so a panel reads as glass-over-cells rather than a blue box.
  function panelTexture() {
    if (_texCache.panel) return _texCache.panel;
    var THREE = window.THREE, W = 256, H = 128;
    var c = document.createElement('canvas'); c.width = W; c.height = H;
    var ctx = c.getContext('2d');
    ctx.fillStyle = '#0e2350'; ctx.fillRect(0, 0, W, H);
    var cols = 12, rows = 6, gx = W / cols, gy = H / rows;
    for (var r = 0; r < rows; r++) for (var k = 0; k < cols; k++) {
      ctx.fillStyle = (r + k) % 2 ? '#12305f' : '#0d1f47';
      ctx.fillRect(k * gx + 1.5, r * gy + 1.5, gx - 3, gy - 3);
    }
    ctx.strokeStyle = 'rgba(190,205,225,0.55)'; ctx.lineWidth = 1.2;
    for (var x = 0; x <= W; x += gx) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
    for (var y = 0; y <= H; y += gy) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
    var tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;   // tile along the row length
    if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    _texCache.panel = tex;
    return tex;
  }

  // Asphalt road: dark bitumen with fine aggregate speckle + a dashed centre
  // line, so access roads read as sealed roadway instead of a flat grey slab.
  function roadTexture() {
    if (_texCache.road) return _texCache.road;
    var THREE = window.THREE, W = 128, H = 256;
    var c = document.createElement('canvas'); c.width = W; c.height = H;
    var ctx = c.getContext('2d');
    ctx.fillStyle = '#37383c'; ctx.fillRect(0, 0, W, H);
    var img = ctx.getImageData(0, 0, W, H), d = img.data;
    for (var i = 0; i < d.length; i += 4) {
      var n = (Math.random() - 0.5) * 30;            // aggregate speckle
      d[i] = Math.max(0, Math.min(255, d[i] + n));
      d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + n));
      d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + n));
    }
    ctx.putImageData(img, 0, 0);
    // dashed centre line running the length (V axis)
    ctx.fillStyle = 'rgba(220,200,90,0.85)';
    for (var y = 8; y < H; y += 40) ctx.fillRect(W / 2 - 3, y, 6, 22);
    var tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    _texCache.road = tex;
    return tex;
  }

  // ---- individual object meshes ----
  function buildBox(o) {
    var THREE = window.THREE;
    var dm = o.dimensions || {};
    var geom = new THREE.BoxGeometry(dm.w || 1, dm.h || 1, dm.l || 1);
    var mesh = new THREE.Mesh(geom, DT.materials.get((o.render || {}).material));
    var p = (o.transform || {}).position || [0, 0, 0];
    mesh.position.set(p[0], p[1], p[2]);
    mesh.setRotationFromEuler(euler((o.transform || {}).rotation_deg));
    mesh.castShadow = tierShadows() && (o.render || {}).cast_shadow !== false;
    mesh.receiveShadow = tierShadows();
    mesh.userData = { objectId: o.id, layer: o.layer, object: o };
    return mesh;
  }

  function buildMast(o) {
    var THREE = window.THREE, dm = o.dimensions || {};
    var r = (dm.w || 0.4) * 0.5;
    var geom = new THREE.CylinderGeometry(r, r, dm.h || 6, 8);
    var mesh = new THREE.Mesh(geom, DT.materials.get((o.render || {}).material));
    var p = (o.transform || {}).position || [0, 0, 0];
    mesh.position.set(p[0], p[1], p[2]);
    mesh.castShadow = tierShadows();
    mesh.userData = { objectId: o.id, layer: o.layer, object: o };
    return mesh;
  }

  function buildTerrain(o) {
    var THREE = window.THREE, dm = o.dimensions || {};
    // Rectangular terrain: w = E-W (X), l = N-S (Z). PlaneGeometry(w, l) lays w
    // along X and l along Y; the -90deg X rotation below sends Y -> Z, so the
    // plane covers w (E-W) x l (N-S). Legacy square sites have w === l.
    var w = dm.w || 300, l = dm.l || dm.w || 300;
    var geom = new THREE.PlaneGeometry(w, l, 1, 1);
    // Own material (not the shared 'soil') so we can hang the tiled grass map on
    // it without affecting other soil-coloured objects. One tile ~= 10 m.
    var base = DT.materials.get('soil');
    var mat = base.clone();
    if (DT.state.graphicsTier !== 'low') {
      var g = grassTexture();
      var reps = Math.max(4, Math.round(Math.max(w, l) / 10));
      g.repeat.set(reps, reps);
      mat.map = g;
      mat.color.set('#ffffff');   // let the texture supply the colour
      // Bump map so the directional sun shades surface unevenness -- kills the
      // flat-sheet look without moving geometry. Conservative scale; tiles with
      // the grass albedo. Shares one cached texture, so set repeat on a clone-safe
      // per-material basis via the map's own repeat (bump reuses the same UVs).
      var bump = groundBumpTexture();
      bump.repeat.set(reps, reps);
      mat.bumpMap = bump;
      mat.bumpScale = 0.35;
      mat.needsUpdate = true;
    }
    var mesh = new THREE.Mesh(geom, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.y = -0.02;
    mesh.receiveShadow = tierShadows();
    mesh.userData = { objectId: o.id, layer: o.layer, object: o };
    return mesh;
  }

  // Cached asphalt road material, one per tier. Built ONCE and reused across
  // every road AND every rebuild -- a stable shared singleton like DT.materials,
  // so (a) we never clone-per-build (no leak; disposeGroup deliberately leaves
  // shared materials alone) and (b) we never mutate a shared texture's repeat
  // per road (no stomp between roads). Repeat is a fixed world-ish tiling set
  // once here; the dashed centre line runs the road length via V-wrap.
  var _roadMatCache = {};
  function roadMaterial() {
    var tier = DT.state.graphicsTier || 'medium';
    if (_roadMatCache[tier]) return _roadMatCache[tier];
    var mat = DT.materials.get('asphalt');
    if (tier !== 'low') {
      mat = mat.clone();
      var tex = roadTexture();
      tex.repeat.set(1, 6);   // fixed tiling, set once -> no per-road stomp
      mat.map = tex; mat.color.set('#ffffff'); mat.needsUpdate = true;
    }
    _roadMatCache[tier] = mat;
    return mat;
  }

  // Access road: a thin box carrying the shared asphalt material (centre-line
  // dashes run the length via the texture's V-wrap).
  function buildRoad(o) {
    var THREE = window.THREE, dm = o.dimensions || {};
    var w = dm.w || 6, h = Math.max(dm.h || 0.1, 0.06), l = dm.l || 40;
    var geom = new THREE.BoxGeometry(w, h, l);
    var mat = roadMaterial();
    var mesh = new THREE.Mesh(geom, mat);
    var p = (o.transform || {}).position || [0, 0, 0];
    mesh.position.set(p[0], Math.max(p[1], h / 2), p[2]);
    mesh.setRotationFromEuler(euler((o.transform || {}).rotation_deg));
    mesh.receiveShadow = tierShadows();
    mesh.userData = { objectId: o.id, layer: o.layer, object: o };
    return mesh;
  }

  function buildFence(o) {
    var THREE = window.THREE, g = group('fence');
    var pts = ((o.meta || {}).points || []).slice();
    if (pts.length < 3) return;
    pts.push(pts[0]);
    var h = (o.dimensions || {}).h || 2.4;
    var mat = DT.materials.get('fence_metal');
    for (var i = 0; i < pts.length - 1; i++) {
      var a = pts[i], b = pts[i + 1];
      var dx = b[0] - a[0], dz = b[1] - a[1];
      var len = Math.sqrt(dx * dx + dz * dz);
      var geom = new THREE.BoxGeometry(len, h, 0.15);
      var m = new THREE.Mesh(geom, mat);
      m.position.set((a[0] + b[0]) / 2, h / 2, (a[1] + b[1]) / 2);
      m.rotation.y = -Math.atan2(dz, dx);
      m.userData = { objectId: o.id, layer: 'fence', object: o, segment: i };
      g.add(m);
      DT.three.pickables.push(m);
    }
    var e = DT.objectIndex.get(o.id); if (e) e.mesh = g;
  }

  // Aluminium frame ring for a PV table: a HOLLOW rectangular rim in the panel
  // plane so the dark glass shows through the opening (a solid oversized box
  // would occlude the glass from above). One ExtrudeGeometry (core THREE, no
  // BufferGeometryUtils needed), built once and instanced with the SAME per-row
  // matrix as the panel so it inherits tilt / azimuth / per-row scale.
  function pvFrameGeometry(THREE, w, l, rim, thick) {
    var hw = w / 2, hl = l / 2;
    var iw = Math.max(hw - rim, hw * 0.2), il = Math.max(hl - rim, hl * 0.2);
    var s = new THREE.Shape();
    s.moveTo(-hw, -hl); s.lineTo(hw, -hl); s.lineTo(hw, hl); s.lineTo(-hw, hl); s.lineTo(-hw, -hl);
    var hole = new THREE.Path();
    hole.moveTo(-iw, -il); hole.lineTo(iw, -il); hole.lineTo(iw, il); hole.lineTo(-iw, il); hole.lineTo(-iw, -il);
    s.holes.push(hole);
    var g = new THREE.ExtrudeGeometry(s, { depth: thick, bevelEnabled: false });
    g.rotateX(-Math.PI / 2);        // shape XY plane -> panel XZ plane; extrude -> +Y
    g.translate(0, -thick / 2, 0);  // centre the rim thickness on the row origin
    return g;
  }

  // ---- instanced PV rows ----
  function buildPvRows(rows) {
    if (!rows.length) return;
    var THREE = window.THREE;
    var first = rows[0].dimensions || {};
    // Thin panel slab, but tall enough (0.12 m) to read as a table edge. Tilt
    // comes from the server rotation_deg (about the row's long axis).
    var rowW = first.w || 2, rowL = first.l || 100;
    var geom = new THREE.BoxGeometry(rowW, Math.max(first.h || 0.06, 0.12), rowL);
    var mat = DT.materials.get('pv_glass');
    // Give the shared panel material a cell-grid map + repeat it along the row
    // so each row reads as a TABLE OF MODULES (many cells) instead of one box.
    if (DT.state.graphicsTier !== 'low' && !mat.map) {
      mat = mat.clone();
      var ptex = panelTexture();
      var mods = ((rows[0].meta || {}).modules) || Math.max(8, Math.round(Math.max(rowW, rowL) / 2));
      // baked grid = 12 cells across U(x), 6 across V(z). Tile along whichever
      // horizontal axis is the LONG one so module count runs down the row.
      if (rowW >= rowL) ptex.repeat.set(Math.max(1, Math.round(mods / 12)), 1);
      else ptex.repeat.set(1, Math.max(1, Math.round(mods / 6)));
      mat.map = ptex;
      mat.needsUpdate = true;
    }
    var inst = new THREE.InstancedMesh(geom, mat, rows.length);
    inst.castShadow = tierShadows();
    inst.receiveShadow = false;

    // Aluminium frame: one instance per row sharing the panel matrix, so every
    // table reads as a framed module (dark glass inside a metal rim) rather than
    // a bare slab -- the biggest realism win up close. Decorative: NOT pickable,
    // NOT indexed, and it does NOT cast shadow (the panel already casts the
    // row's shadow), so a large farm pays no extra shadow cost. Low tier skips.
    var frameInst = null;
    if (DT.state.graphicsTier !== 'low') {
      var panelH = Math.max(first.h || 0.06, 0.12);
      // Build the rim slightly LARGER than the panel (outward overhang `ov`) and
      // reaching `rimIn` inward over the glass, so NO frame face is coplanar with
      // a panel face -> no grazing-angle shimmer (Codex). The rim is also a touch
      // taller than the panel (panelH + 0.06) so its top/bottom rings clear the
      // glass faces rather than sitting flush with them.
      var ov = 0.04, rimIn = Math.min(rowW, rowL) * 0.04 + 0.05;
      var fgeom = pvFrameGeometry(THREE, rowW + 2 * ov, rowL + 2 * ov,
                                  ov + rimIn, panelH + 0.06);
      frameInst = new THREE.InstancedMesh(fgeom, DT.materials.get('aluminum_frame'), rows.length);
      frameInst.castShadow = false;
      frameInst.receiveShadow = false;
    }

    var dummy = new THREE.Object3D();
    var map = [];   // instanceId -> objectId
    rows.forEach(function (o, i) {
      var p = (o.transform || {}).position || [0, 0, 0];
      dummy.position.set(p[0], p[1], p[2]);
      dummy.setRotationFromEuler(euler((o.transform || {}).rotation_deg));
      // Scale to this row's own length if it differs from the shared geometry.
      var dm = o.dimensions || {};
      dummy.scale.set((dm.w || 2) / (first.w || 2), 1, (dm.l || 100) / (first.l || 100));
      dummy.updateMatrix();
      inst.setMatrixAt(i, dummy.matrix);
      if (frameInst) frameInst.setMatrixAt(i, dummy.matrix);   // frame shares panel placement
      map[i] = o.id;
      var e = DT.objectIndex.get(o.id); if (e) { e.mesh = inst; e.instanceId = i; }
    });
    inst.instanceMatrix.needsUpdate = true;
    inst.userData = { layer: 'pv_row', instancedRows: map };
    group('pv_row').add(inst);
    DT.three.pickables.push(inst);          // panel stays the ONLY pickable row mesh
    DT.three.instanced.pv_row = inst;
    if (frameInst) {
      frameInst.instanceMatrix.needsUpdate = true;
      frameInst.userData = { layer: 'pv_row', decorative: true };
      group('pv_row').add(frameInst);       // toggles + disposes with the panels
    }
  }

  // ---- PV mounting structure (torque tube + support legs) ----
  // Real utility arrays are TABLES on posts, not floating slabs -- the single
  // biggest realism gap. Built as two instanced meshes (one tube per row, two
  // legs per row) added to the 'pv_row' group so they toggle + shadow with the
  // panels. Decorative only: not pickable, not indexed. Tier/size gated so a
  // 100 MW (low-tier) farm skips it and never pays the instance cost.
  function buildPvSupports(rows) {
    if (DT.state.graphicsTier === 'low') return;
    if (!rows.length) return;
    // No row cap at all: tube + legs are single InstancedMeshes (draw-call cost
    // is flat regardless of row count), and the panel loop in buildPvRows is
    // already uncapped, so supports match it. Only shadow-casting degrades on
    // huge farms (see supShadow below) -- geometry is NEVER dropped. This fixes
    // the old `rows.length > 4000` cutoff that stripped ALL mounting structure
    // off a 100 MW farm (Codex finding #3).
    var THREE = window.THREE;
    var first = rows[0].dimensions || {};
    var rowW = first.w || 2, rowL = first.l || 100;
    var rowH = Math.max(first.h || 0.06, 0.12);
    var longZ = rowL >= rowW;                          // long axis is Z when l>=w
    var steel = DT.materials.get('steel');
    // Support shadows are the one place a huge farm could bite a weak GPU, so
    // gate them on the high tier AND a moderate row count. Geometry still shows
    // on a 100 MW farm; only its shadow-casting degrades (Codex finding #3).
    var supShadow = tierShadows() && (DT.state.graphicsTier === 'high') && rows.length <= 3000;
    var ZERO = new THREE.Matrix4().makeScale(0, 0, 0);   // hide mismatched rows

    // Torque tube: a slim beam the length of the row, sunk just below the
    // modules. It shares each panel's full matrix (so it inherits the tilt);
    // the downward offset is baked into the geometry.
    var tubeLen = (longZ ? rowL : rowW) * 0.98;
    var tubeGeom = longZ ? new THREE.BoxGeometry(0.14, 0.14, tubeLen)
                         : new THREE.BoxGeometry(tubeLen, 0.14, 0.14);
    tubeGeom.translate(0, -(rowH / 2 + 0.16), 0);
    var tubes = new THREE.InstancedMesh(tubeGeom, steel, rows.length);
    tubes.castShadow = supShadow; tubes.receiveShadow = false;

    // Two vertical legs per row, standing on the ground under the long-axis
    // ends. Their x/z footprint is read from the panel matrix (points on the
    // long-axis centre-line are invariant to tilt-about-long-axis, so this is
    // correct whichever rotation convention the server used).
    var legs = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(0.07, 0.09, 1, 6), steel, rows.length * 2);
    legs.castShadow = supShadow; legs.receiveShadow = false;

    var dP = new THREE.Object3D(), dL = new THREE.Object3D();
    var end = new THREE.Vector3(), m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
    var li = 0;
    rows.forEach(function (o, i) {
      var p = (o.transform || {}).position || [0, 0, 0];
      var rot = euler((o.transform || {}).rotation_deg);
      var dm = o.dimensions || {};
      // The shared tube geometry is oriented for the row[0] long axis. If a row
      // ever flips orientation (heterogeneous scene), hide its supports rather
      // than lay them along the wrong axis.
      if (((dm.l || rowL) >= (dm.w || rowW)) !== longZ) {
        tubes.setMatrixAt(i, ZERO); legs.setMatrixAt(li++, ZERO); legs.setMatrixAt(li++, ZERO);
        return;
      }
      // tube shares panel placement + length-scale along the long axis
      dP.position.set(p[0], p[1], p[2]);
      dP.setRotationFromEuler(rot);
      dP.scale.set(longZ ? 1 : (dm.w || rowW) / rowW, 1, longZ ? (dm.l || rowL) / rowL : 1);
      dP.updateMatrix();
      tubes.setMatrixAt(i, dP.matrix);
      // legs: world footprint of the two long-axis ends
      q.setFromEuler(rot);
      m4.compose(dP.position, q, new THREE.Vector3(1, 1, 1));
      var panelY = Math.max(p[1], 0.4);
      [-1, 1].forEach(function (s) {
        var half = (longZ ? (dm.l || rowL) : (dm.w || rowW)) * 0.45 * s;
        end.set(longZ ? 0 : half, 0, longZ ? half : 0).applyMatrix4(m4);
        dL.position.set(end.x, panelY / 2, end.z);
        dL.rotation.set(0, 0, 0);
        dL.scale.set(1, panelY, 1);
        dL.updateMatrix();
        legs.setMatrixAt(li++, dL.matrix);
      });
    });
    tubes.instanceMatrix.needsUpdate = true;
    legs.instanceMatrix.needsUpdate = true;
    var g = group('pv_row');
    g.add(tubes); g.add(legs);
  }

  // ---- decorative scenery (trees ring + distant hills) ----
  // Adds life + depth around the farm to match the reference aerial. Purely
  // decorative: not pickable, not indexed, lives in its own 'scenery' layer.
  function buildScenery() {
    if (DT.state.graphicsTier === 'low') return;
    var THREE = window.THREE;
    var site = (DT.scene && DT.scene.site) || {};
    var half = (site.land_side_m || 600) / 2;
    var g = group('scenery');

    // Trees: two instanced meshes (trunk + canopy) scattered in a ring just
    // outside the fence line.
    var N = 96, d = new THREE.Object3D();
    // Scenery materials are created ONCE and reused across rebuilds. disposeGroup
    // disposes geometries but deliberately leaves shared materials alone, so
    // creating these per-build (as before) leaked a material + WebGL program on
    // every parameter/object rebuild (Codex fix). Rounded smooth-shaded canopies
    // (no flatShading) read as trees, not the faceted crystals the low-poly
    // icosahedron produced.
    if (!_sceneryMats) _sceneryMats = {
      trunk: new THREE.MeshStandardMaterial({ color: '#6b4a2b', roughness: 1 }),
      canopy: new THREE.MeshStandardMaterial({ color: '#3f6b2e', roughness: 0.95 })
    };
    var trunkMat = _sceneryMats.trunk, canopyMat = _sceneryMats.canopy;
    var trunks = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.5, 0.75, 4, 6), trunkMat, N);
    var canopies = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(3.4, 2), canopyMat, N);
    trunks.castShadow = canopies.castShadow = tierShadows();
    for (var i = 0; i < N; i++) {
      var ang = (i / N) * Math.PI * 2 + Math.random() * 0.5;
      var rad = half * (1.14 + Math.random() * 0.9);
      var x = Math.cos(ang) * rad, z = Math.sin(ang) * rad, s = 0.7 + Math.random() * 1.3;
      d.rotation.set(0, Math.random() * 6.28, 0);
      d.scale.set(s, s, s);
      d.position.set(x, 2 * s, z); d.updateMatrix(); trunks.setMatrixAt(i, d.matrix);
      d.position.set(x, 6.4 * s, z); d.updateMatrix(); canopies.setMatrixAt(i, d.matrix);
    }
    trunks.instanceMatrix.needsUpdate = canopies.instanceMatrix.needsUpdate = true;
    g.add(trunks); g.add(canopies);

    // The old "distant hills" were 6-sided flat-shaded cones -- they read as a
    // toy train-set backdrop and actively pulled the scene toward the cartoon
    // look the owner rejected. Dropped: the atmospheric fog + graded horizon
    // haze already close the scene off believably, and an empty far field looks
    // more like a real flat solar site than faceted paper mountains.
  }

  // ---- public build / rebuild ----
  function build() {
    var t = DT.three;
    var objs = (DT.scene && DT.scene.objects) || [];
    DT.reindex();
    var rows = [];
    objs.forEach(function (o) {
      if (o.layer === 'pv_row' || o.layer === 'pv_array') { rows.push(o); return; }
      if (o.kind === 'line_loop') { buildFence(o); return; }
      var mesh;
      if (o.kind === 'ground' || o.layer === 'terrain') mesh = buildTerrain(o);
      else if (o.layer === 'internal_roads') mesh = buildRoad(o);
      else if (o.kind === 'mast') mesh = buildMast(o);
      else mesh = buildBox(o);
      group(o.layer).add(mesh);
      t.pickables.push(mesh);
      var e = DT.objectIndex.get(o.id); if (e) e.mesh = mesh;
    });
    buildPvRows(rows);
    buildPvSupports(rows);
    buildScenery();
    DT.bus.emit('scene:built', DT.scene);
  }

  function disposeGroup(g) {
    for (var i = g.children.length - 1; i >= 0; i--) {
      var c = g.children[i];
      if (c.geometry) c.geometry.dispose();
      g.remove(c);
    }
    if (g.parent) g.parent.remove(g);
  }

  // Swap the whole scene graph and rebuild geometry in place (Phase 3).
  function rebuild(newSceneData) {
    var t = DT.three;
    Object.keys(t.layerGroups).forEach(function (k) { disposeGroup(t.layerGroups[k]); });
    t.layerGroups = {};
    t.pickables = [];
    t.instanced = {};
    if (newSceneData) { DT.scene = newSceneData; DT.state.sceneData = newSceneData; }
    build();
    // Labels reference object positions -- rebuild them so none go stale.
    if (DT.labels && DT.labels.rebuild) DT.labels.rebuild();
  }

  DT.builder = { build: build, rebuild: rebuild, group: group };
})();
