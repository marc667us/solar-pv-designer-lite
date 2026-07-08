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
    ctx.fillStyle = '#5f7f3d'; ctx.fillRect(0, 0, S, S);
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
    var geom = new THREE.BoxGeometry(first.w || 2, first.h || 0.06, first.l || 100);
    var mat = DT.materials.get('pv_glass');
    // Give the shared panel material a cell-grid map once so every instanced
    // module reads as glass-over-cells (mullions + specular) rather than a box.
    if (DT.state.graphicsTier !== 'low' && !mat.map) {
      mat = mat.clone();
      mat.map = panelTexture();
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
