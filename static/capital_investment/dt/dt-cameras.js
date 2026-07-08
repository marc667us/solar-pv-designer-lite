/* dt-cameras.js -- engineering camera presets + smooth tween (Phase 4).
 *
 * Reads DT.scene.camera_presets (14 named views computed server-side, scaled
 * to the site). Every preset and every VR-impression card is a real animated
 * camera move -- never a static screenshot. Tweens position + controls.target
 * together over ~700ms with easing that does not fight OrbitControls damping.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var anim = null;

  function ease(t) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; }

  function tween(toPos, toTarget, ms) {
    var t = DT.three, THREE = window.THREE;
    if (!t.camera || !t.controls) return;
    if (anim) cancelAnimationFrame(anim);
    var fromPos = t.camera.position.clone();
    var fromTgt = t.controls.target.clone();
    var toP = new THREE.Vector3(toPos[0], toPos[1], toPos[2]);
    var toT = new THREE.Vector3(toTarget[0], toTarget[1], toTarget[2]);
    var start = null, dur = ms || 700;
    function step(ts) {
      if (start == null) start = ts;
      var k = Math.min((ts - start) / dur, 1), e = ease(k);
      t.camera.position.lerpVectors(fromPos, toP, e);
      t.controls.target.lerpVectors(fromTgt, toT, e);
      t.controls.update();
      if (k < 1) anim = requestAnimationFrame(step); else anim = null;
    }
    anim = requestAnimationFrame(step);
  }

  function goPreset(name) {
    var presets = (DT.scene && DT.scene.camera_presets) || {};
    var p = presets[name];
    if (!p) return;
    tween(p.position, p.target || [0, 0, 0], 700);
    // Night preset also flips the visual mode for a coherent look.
    if (name === 'night' && DT.modes) DT.modes.setLightingProfile('night');
  }

  // VR-impression cards -> real camera moves (some target a live object).
  function goVr(card) {
    var t = DT.three;
    if (card === 'aerial') return goPreset('investor');
    if (card === 'ground') return goPreset('walkthrough');
    if (card === 'night') { goPreset('night'); return; }
    // inverter / substation: fly to the first matching object if present.
    var layer = card === 'inverter' ? 'inverter' :
                card === 'substation' ? 'transformer' : null;
    if (layer) {
      var rec = null;
      DT.objectIndex.forEach(function (v) {
        if (!rec && v.object && v.object.layer === layer) rec = v.object;
      });
      if (rec) {
        var p = (rec.transform || {}).position || [0, 0, 0];
        tween([p[0] + 25, 12, p[2] + 25], [p[0], 3, p[2]], 700);
        DT.selection && DT.selection.select(rec.id);
        return;
      }
    }
    goPreset('birdseye');
  }

  DT.cameras = { goPreset: goPreset, goVr: goVr, tween: tween };
})();
