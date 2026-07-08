/* dt-toolrail.js -- viewport tool rail + floating object tooltips.
 *
 * Layout-local wiring for the mockup's left tool rail (select / pan / orbit /
 * zoom / top / labels / fit / fullscreen) and the dark object tooltips that
 * float over the PV array, inverter station and substation. It only uses the
 * public DT.* API (DT.three, DT.cameras, DT.modes, DT.scene) and is fully
 * defensive: any missing widget or handle is a no-op, never a thrown error.
 * Loaded AFTER dt-main.js so the DT namespace + render handles exist.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  function el(id) { return document.getElementById(id); }

  // ---------------- tool rail ----------------
  function setActiveTool(id) {
    var rail = el('dt-toolrail'); if (!rail) return;
    rail.querySelectorAll('button').forEach(function (b) {
      b.classList.toggle('active', b.id === id);
    });
  }

  // Dolly the camera along its line-of-sight toward/away from the orbit target.
  function dolly(factor) {
    var t = DT.three; if (!t || !t.camera || !t.controls) return;
    t.camera.position.lerpVectors(t.controls.target, t.camera.position, factor);
    t.controls.update();
  }

  function wireTools() {
    var bind = function (id, fn, activates) {
      var b = el(id); if (!b) return;
      b.addEventListener('click', function () {
        if (activates) setActiveTool(id);
        try { fn(); } catch (e) { }
      });
    };
    bind('tool-select', function () {
      if (DT.selection && DT.selection.select) DT.selection.select(null);
    }, true);
    bind('tool-pan', function () { }, true);
    bind('tool-orbit', function () { }, true);
    bind('tool-zoom-in', function () { dolly(0.82); });
    bind('tool-zoom-out', function () { dolly(1.22); });
    bind('tool-top', function () { DT.cameras && DT.cameras.goPreset('top'); });
    bind('tool-labels', function () {
      var v = !DT.state.labelsVisible;
      DT.modes && DT.modes.setLabelsVisible(v);
      var b = el('tool-labels'); if (b) b.classList.toggle('active', v);
    });
    bind('tool-fit', function () { DT.cameras && DT.cameras.goPreset('birdseye'); });
    bind('tool-full', function () {
      // Fullscreen the whole viewport CARD (the .solar-card parent) so the tool
      // rail, HUD, timeline and tooltips come along -- not the bare canvas div.
      var vp = el('dt-viewport');
      var host = (vp && vp.parentElement) || vp;
      if (!document.fullscreenElement && host && host.requestFullscreen) host.requestFullscreen();
      else if (document.exitFullscreen) document.exitFullscreen();
    });
    // LAUNCH VR (right panel) -> investor immersive mode. Wired explicitly so it
    // keeps its green styling instead of being restyled by the generic
    // .dt-mode-btn active-class toggle.
    var vrBtn = el('dt-launch-vr');
    if (vrBtn) vrBtn.addEventListener('click', function () {
      if (DT.modes && DT.modes.setMode) DT.modes.setMode('investor');
    });
  }

  // ---------------- floating object tooltips ----------------
  // A short, curated set of headline objects (mockup shows PV ARRAY / INVERTER
  // STATION / SUBSTATION). Each maps to a scene layer; the first object in that
  // layer supplies the world anchor, and the tip body is filled from the scene
  // aggregates (pv.meta, inverter count, transformer count) not per-row noise.
  var tips = [];     // [{ layer, world:[x,y,z], node }]

  function firstOfLayer(layer) {
    var objs = (DT.scene && DT.scene.objects) || [];
    for (var i = 0; i < objs.length; i++) if (objs[i].layer === layer) return objs[i];
    return null;
  }
  function countLayer(layer) {
    var objs = (DT.scene && DT.scene.objects) || [], n = 0;
    for (var i = 0; i < objs.length; i++) if (objs[i].layer === layer) n++;
    return n;
  }

  function buildTips() {
    var host = el('dt-obj-tips'); if (!host) return;
    host.innerHTML = ''; tips = [];
    var pv = ((DT.scene || {}).pv || {}).meta || {};
    var invN = ((DT.scene || {}).inverters || []).length || countLayer('inverter');
    var xfmrN = countLayer('transformer') + countLayer('transformer_bldg');
    var specs = [
      { layer: 'pv_row', title: 'PV ARRAY', rows: [
        ['Rows', DT.util.fmt(pv.n_rows)], ['Modules', DT.util.fmt(pv.n_modules_planned)] ] },
      { layer: 'inverter', title: 'INVERTER STATION', rows: [
        ['Inverters', DT.util.fmt(invN || 0)] ] },
      { layer: 'transformer', title: 'SUBSTATION', alt: 'transformer_bldg', rows: [
        ['Transformers', xfmrN ? DT.util.fmt(xfmrN) : ''] ] }
    ];
    specs.forEach(function (sp) {
      var o = firstOfLayer(sp.layer) || (sp.alt && firstOfLayer(sp.alt));
      if (!o) return;
      var p = (o.transform || {}).position || [0, 0, 0];
      var node = document.createElement('div');
      node.className = 'dt-obj-tip';
      node.style.display = 'none';
      var html = '<div class="t">' + DT.util.esc(sp.title) + '</div>';
      sp.rows.forEach(function (r) {
        if (r[1] === '' || r[1] == null) return;
        html += '<div class="r">' + DT.util.esc(r[0]) + ': ' + DT.util.esc(r[1]) + '</div>';
      });
      node.innerHTML = html;
      host.appendChild(node);
      tips.push({ layer: o.layer, world: [p[0], (p[1] || 0) + 6, p[2]], node: node });
    });
  }

  // Project each tip's world anchor to screen space every frame (throttled) and
  // hide it when its layer is toggled off or it falls behind the camera.
  var raf = null, lastT = 0, _vec = null;
  function loop(ts) {
    raf = requestAnimationFrame(loop);
    if (ts - lastT < 90) return;         // ~11 Hz is plenty for tooltips
    lastT = ts;
    var t = DT.three, THREE = window.THREE, vp = el('dt-viewport');
    if (!t || !t.camera || !THREE || !vp || !tips.length) return;
    var w = vp.clientWidth, h = vp.clientHeight;
    var v = _vec || (_vec = new THREE.Vector3());   // hoisted, no per-frame alloc
    tips.forEach(function (tip) {
      var grp = t.layerGroups[tip.layer];
      var hidden = grp && grp.visible === false;
      v.set(tip.world[0], tip.world[1], tip.world[2]).project(t.camera);
      var behind = v.z > 1 || v.z < -1;
      if (hidden || behind) { tip.node.style.display = 'none'; return; }
      var x = (v.x * 0.5 + 0.5) * w, y = (-v.y * 0.5 + 0.5) * h;
      if (x < 0 || y < 0 || x > w || y > h) { tip.node.style.display = 'none'; return; }
      tip.node.style.display = '';
      tip.node.style.left = Math.round(x) + 'px';
      tip.node.style.top = Math.round(y) + 'px';
      tip.node.style.transform = 'translate(-50%,-120%)';
    });
  }

  function start() {
    wireTools();
    buildTips();
    if (!raf) raf = requestAnimationFrame(loop);
    // Rebuild anchors whenever the scene geometry is swapped (parameter change).
    DT.bus && DT.bus.on && DT.bus.on('scene:built', buildTips);
  }

  // dt-main builds the scene asynchronously; wait for the first build so the
  // camera + scene objects exist before we start projecting. Guarded so we
  // start exactly once, whether via the bus event or (if the bus already fired
  // before this file parsed) via a direct readiness check / poll fallback.
  var started = false;
  function startOnce() { if (started) return; started = true; start(); }
  if (DT.bus && DT.bus.on) {
    DT.bus.on('scene:built', function once() { DT.bus.off('scene:built', once); startOnce(); });
    if (DT.three && DT.three.camera && DT.scene) startOnce();   // bus may have already fired
  } else {
    var tries = 0, iv = setInterval(function () {
      if ((DT.three && DT.three.camera && DT.scene) || tries++ > 60) { clearInterval(iv); startOnce(); }
    }, 100);
  }
})();
