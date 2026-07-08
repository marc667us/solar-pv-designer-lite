/* dt-glb-models.js — OPTIONAL, GUARDED photoreal-equipment layer.
 *
 * After the scene is built, this module loads a self-hosted GLB equipment kit
 * (plant-kit.glb: pv_table / inverter / transformer / substation) and replaces
 * the crude box primitives for inverters, transformers and buildings with the
 * authored 3D models — scaled to each object's footprint, positioned on the
 * ground, rotated to match. The InstancedMesh PV panels are left untouched.
 *
 * SAFETY (this must never break the working twin):
 *   - Runs only if window.DT_GLB_ENABLED and THREE.GLTFLoader are present.
 *   - Skipped on the 'low' graphics tier (huge farms) for performance.
 *   - A primitive box is hidden ONLY AFTER its GLB replacement is successfully
 *     added, so a partial failure never leaves a hole.
 *   - Every step is wrapped in try/catch; any failure leaves the primitives as-is.
 *   - The original box meshes are kept (visible=false) so picking / selection /
 *     labels — which use the box meshes — continue to work unchanged.
 */
(function () {
  "use strict";
  var DT = window.DT = window.DT || {};

  var KIT_URL = "/static/capital_investment/dt/models/plant-kit.glb";
  // object layer / id  ->  kit node name
  function modelKeyFor(o) {
    if (!o) return null;
    if (o.layer === "inverter") return "inverter";
    if (o.layer === "transformer") return "transformer";
    if ((o.id && String(o.id).indexOf("bldg_") === 0) || o.layer === "building") return "substation";
    return null;
  }

  var _kit = null;        // { inverter: Object3D, ... } prototypes
  var _kitTried = false;
  var _glbGroup = null;
  var _hidden = [];       // box meshes this module has hidden (to restore later)

  function tierOK() {
    try { return (DT.state && DT.state.graphicsTier) !== "low"; }
    catch (e) { return true; }
  }

  // Dispose a group's cloned geometries/materials so repeated rebuilds don't leak.
  function disposeGroup(g) {
    if (!g) return;
    try {
      g.traverse(function (m) {
        if (m.isMesh) {
          if (m.geometry && m.geometry.dispose) m.geometry.dispose();
          var mat = m.material;
          if (Array.isArray(mat)) mat.forEach(function (x) { if (x && x.dispose) x.dispose(); });
          else if (mat && mat.dispose) mat.dispose();
        }
      });
    } catch (e) {}
    if (g.parent) g.parent.remove(g);
  }

  // Restore every box we previously hid (before re-placing), so a box is never
  // left hidden without a live GLB replacement.
  function restoreHidden() {
    for (var i = 0; i < _hidden.length; i++) {
      try { if (_hidden[i]) _hidden[i].visible = true; } catch (e) {}
    }
    _hidden = [];
  }

  function bbox(obj) {
    var THREE = window.THREE;
    return new THREE.Box3().setFromObject(obj);
  }

  // Load + cache the kit prototypes once.
  function loadKit(cb) {
    if (_kit) { cb(_kit); return; }
    if (_kitTried) { cb(null); return; }
    _kitTried = true;
    try {
      var THREE = window.THREE;
      if (!THREE || !THREE.GLTFLoader) { cb(null); return; }
      new THREE.GLTFLoader().load(KIT_URL, function (gltf) {
        try {
          var kit = {};
          ["pv_table", "inverter", "transformer", "substation"].forEach(function (n) {
            var node = gltf.scene.getObjectByName(n);
            if (node) kit[n] = node;
          });
          _kit = kit;
          cb(kit);
        } catch (e) { cb(null); }
      }, undefined, function () { cb(null); });
    } catch (e) { cb(null); }
  }

  // Place a GLB model to match a box mesh, then hide the box.
  function placeModel(boxMesh, proto) {
    var THREE = window.THREE;
    var o = boxMesh.userData && boxMesh.userData.object;
    if (!o || !proto) return false;
    var dm = o.dimensions || {};
    var inst = proto.clone(true);

    // uniform scale so the model footprint width matches the object width
    var b = bbox(inst);
    var size = new THREE.Vector3(); b.getSize(size);
    var mw = size.x || 1, mh = size.y || 1;
    var targetW = dm.w || dm.l || mw;
    var s = targetW / mw;
    // don't let a very tall authored model tower over a short object
    if (dm.h && mh * s > dm.h * 2.2) s = (dm.h * 2.2) / mh;
    inst.scale.setScalar(s);

    // position: object transform.position is the BOX CENTRE; drop the model so
    // its base sits on the ground (y = centre - h/2).
    var p = (o.transform && o.transform.position) || [0, 0, 0];
    var h = dm.h || (mh * s);
    inst.position.set(p[0], (p[1] || 0) - h / 2, p[2]);

    var rot = (o.transform && o.transform.rotation_deg) || [0, 0, 0];
    inst.rotation.y = (rot[1] || 0) * Math.PI / 180;

    var shad = tierOK();
    inst.traverse(function (m) {
      if (m.isMesh) { m.castShadow = shad; m.receiveShadow = shad;
        // let scene.environment reflect on the PBR materials
        if (m.material && "envMapIntensity" in m.material) m.material.envMapIntensity = 0.7;
      }
    });
    inst.userData = { glbFor: o.id };
    _glbGroup.add(inst);                  // if this throws, box stays visible
    boxMesh.visible = false;             // hide the primitive AFTER success
    _hidden.push(boxMesh);               // remember so we can restore on rebuild
    return true;
  }

  function apply() {
    if (!window.DT_GLB_ENABLED) return;
    if (!tierOK()) return;
    var THREE = window.THREE;
    var t = DT.three;
    if (!THREE || !t || !t.scene) return;
    loadKit(function (kit) {
      if (!kit) return;                  // load failed -> primitives stay
      try {
        // fresh group each build (rebuild disposes the layer groups, not ours).
        // Restore any boxes we hid last time + dispose the old clones first, so
        // no box is ever left hidden without a live replacement and nothing leaks.
        restoreHidden();
        disposeGroup(_glbGroup);
        _glbGroup = new THREE.Group();
        _glbGroup.name = "dt-glb-models";
        t.scene.add(_glbGroup);

        var meshes = t.pickables || [];
        var placed = 0;
        meshes.forEach(function (mesh) {
          try {
            if (!mesh || !mesh.userData) return;
            var o = mesh.userData.object;
            var key = modelKeyFor(o);
            if (!key || !kit[key]) return;
            if (placeModel(mesh, kit[key])) placed++;
          } catch (e) { /* leave this primitive as-is */ }
        });
        if (window.console && placed) console.log("[dt-glb] placed", placed, "equipment models");
      } catch (e) { /* any failure -> primitives remain visible */ }
    });
  }

  // Run after each build; also once now in case the scene is already built.
  try {
    if (DT.bus && DT.bus.on) DT.bus.on("scene:built", function () { apply(); });
  } catch (e) {}
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(apply, 300); });
  } else {
    setTimeout(apply, 300);
  }

  DT.glbModels = { apply: apply };
})();
