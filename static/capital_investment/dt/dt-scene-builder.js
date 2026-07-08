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
    var mesh = new THREE.Mesh(geom, DT.materials.get('soil'));
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
