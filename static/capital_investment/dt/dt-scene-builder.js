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
    var side = dm.w || 300;
    var geom = new THREE.PlaneGeometry(side, side, 1, 1);
    // Own material (not the shared 'soil') so we can hang the tiled grass map on
    // it without affecting other soil-coloured objects. One tile ~= 10 m.
    var base = DT.materials.get('soil');
    var mat = base.clone();
    if (DT.state.graphicsTier !== 'low') {
      var g = grassTexture();
      var reps = Math.max(4, Math.round(side / 10));
      g.repeat.set(reps, reps);
      mat.map = g;
      mat.color.set('#ffffff');   // let the texture supply the colour
      mat.needsUpdate = true;
    }
    var mesh = new THREE.Mesh(geom, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.y = -0.02;
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
      map[i] = o.id;
      var e = DT.objectIndex.get(o.id); if (e) { e.mesh = inst; e.instanceId = i; }
    });
    inst.instanceMatrix.needsUpdate = true;
    inst.userData = { layer: 'pv_row', instancedRows: map };
    group('pv_row').add(inst);
    DT.three.pickables.push(inst);
    DT.three.instanced.pv_row = inst;
  }

  // ---- PV mounting structure (torque tube + support legs) ----
  // Real utility arrays are TABLES on posts, not floating slabs -- the single
  // biggest realism gap. Built as two instanced meshes (one tube per row, two
  // legs per row) added to the 'pv_row' group so they toggle + shadow with the
  // panels. Decorative only: not pickable, not indexed. Tier/size gated so a
  // 100 MW (low-tier) farm skips it and never pays the instance cost.
  function buildPvSupports(rows) {
    if (DT.state.graphicsTier === 'low') return;
    if (!rows.length || rows.length > 4000) return;    // hard perf cap
    var THREE = window.THREE;
    var first = rows[0].dimensions || {};
    var rowW = first.w || 2, rowL = first.l || 100;
    var rowH = Math.max(first.h || 0.06, 0.12);
    var longZ = rowL >= rowW;                          // long axis is Z when l>=w
    var steel = DT.materials.get('steel');
    // Support structure casts shadows only on the high tier -- the extra shadow
    // passes are the one place this could bite a weak GPU at the row cap.
    var supShadow = tierShadows() && (DT.state.graphicsTier === 'high');
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
    var trunkMat = new THREE.MeshStandardMaterial({ color: '#6b4a2b', roughness: 1 });
    var canopyMat = new THREE.MeshStandardMaterial({ color: '#3f6b2e', roughness: 1, flatShading: true });
    var trunks = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.5, 0.75, 4, 6), trunkMat, N);
    var canopies = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(3.4, 0), canopyMat, N);
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

    // Distant hills fading into the horizon haze (fog does the blending).
    var hillMat = new THREE.MeshStandardMaterial({ color: '#819670', roughness: 1, flatShading: true });
    var hills = new THREE.InstancedMesh(new THREE.ConeGeometry(1, 1, 6), hillMat, 16);
    var hd = new THREE.Object3D();
    for (var j = 0; j < 16; j++) {
      var ha = (j / 16) * Math.PI * 2 + Math.random();
      var hr = half * (4 + Math.random() * 2.5);
      var hw = 500 + Math.random() * 700, hh = 160 + Math.random() * 260;
      hd.rotation.set(0, Math.random() * 6.28, 0);
      hd.scale.set(hw, hh, hw);
      hd.position.set(Math.cos(ha) * hr, 0.5 * hh - 40, Math.sin(ha) * hr);
      hd.updateMatrix(); hills.setMatrixAt(j, hd.matrix);
    }
    hills.instanceMatrix.needsUpdate = true;
    g.add(hills);
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
