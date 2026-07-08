/* dt-main.js -- Digital Twin bootstrap + dashboard + label system.
 *
 * Ties the dt-*.js modules together: builds the renderer/camera/controls,
 * loads the server scene graph (embedded or via DT_SCENE_URL), builds the
 * scene, wires every control (layers, timeline, cameras, modes, VR cards,
 * graphics tiers, parameters, actions, exports) and runs the render loop.
 * Every DOM lookup is guarded so a missing widget never breaks the viewport.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var lastFrame = (window.performance || Date).now ? performance.now() : 0;
  var fpsAcc = 0, frames = 0;

  // ---------- three.js bootstrap ----------
  function init() {
    var THREE = window.THREE;
    var vp = document.getElementById('dt-viewport');
    if (!vp || !THREE) return false;
    var w = vp.clientWidth || 800, h = vp.clientHeight || 500;
    var t = DT.three;
    t.scene = new THREE.Scene();
    t.scene.background = new THREE.Color(0x9ec6e6);
    t.scene.fog = new THREE.Fog(0x9ec6e6, 400, 6000);

    t.camera = new THREE.PerspectiveCamera(45, w / h, 0.5, 12000);
    t.camera.position.set(200, 160, 200);

    t.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    t.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    t.renderer.setSize(w, h);
    if (t.renderer.shadowMap) t.renderer.shadowMap.enabled = (DT.state.graphicsTier !== 'low');
    vp.appendChild(t.renderer.domElement);

    t.controls = new THREE.OrbitControls(t.camera, t.renderer.domElement);
    t.controls.enableDamping = true;
    t.controls.dampingFactor = 0.06;
    t.controls.maxPolarAngle = Math.PI * 0.495;
    t.controls.target.set(0, 0, 0);
    t.controls.update();

    t.ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    t.scene.add(t.ambientLight);
    t.hemiLight = new THREE.HemisphereLight(0x9ec6e6, 0x334422, 0.4);
    t.scene.add(t.hemiLight);
    t.sunLight = new THREE.DirectionalLight(0xfff2d6, 1.0);
    t.sunLight.position.set(100, 300, 100);
    if (t.sunLight.shadow && DT.state.graphicsTier !== 'low') {
      t.sunLight.castShadow = true;
      t.sunLight.shadow.mapSize.set(1024, 1024);
    }
    t.scene.add(t.sunLight);

    t.raycaster = new THREE.Raycaster();
    t.mouse = new THREE.Vector2();
    window.addEventListener('resize', onResize);
    return true;
  }

  function onResize() {
    var t = DT.three, vp = document.getElementById('dt-viewport');
    if (!t.renderer || !vp) return;
    var w = vp.clientWidth, h = vp.clientHeight;
    t.camera.aspect = w / h; t.camera.updateProjectionMatrix();
    t.renderer.setSize(w, h);
  }

  // ---------- scene load ----------
  function loadScene() {
    var el = document.getElementById('dt-scene-json');
    if (el && el.textContent.trim()) {
      try { return Promise.resolve(JSON.parse(el.textContent)); } catch (e) { }
    }
    if (window.DT_SCENE_URL) return DT.util.getJSON(window.DT_SCENE_URL);
    return Promise.reject('no scene');
  }

  // ---------- labels (Phase 7, distance-culled) ----------
  function makeLabel(text, pos) {
    var THREE = window.THREE;
    var c = document.createElement('canvas'); c.width = 256; c.height = 64;
    var ctx = c.getContext('2d');
    ctx.fillStyle = 'rgba(10,16,21,0.75)'; ctx.fillRect(0, 0, 256, 64);
    ctx.fillStyle = '#ffd54a'; ctx.font = 'bold 22px sans-serif';
    ctx.fillText(String(text).slice(0, 22), 10, 40);
    var tex = new THREE.CanvasTexture(c);
    var spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
    spr.position.set(pos[0], pos[1] + 6, pos[2]);
    spr.scale.set(24, 6, 1);
    spr.visible = false;
    return spr;
  }
  // Labels have a proper lifecycle: builder.rebuild() calls DT.labels.rebuild()
  // so a parameter change or object action never leaves stale sprites behind.
  DT.labels = {
    clear: function () {
      var t = DT.three;
      (t.labelSprites || []).forEach(function (s) {
        if (s.material) {
          if (s.material.map) s.material.map.dispose();
          s.material.dispose();
        }
        if (t.scene) t.scene.remove(s);
      });
      t.labelSprites = [];
    },
    rebuild: function () {
      var t = DT.three;
      DT.labels.clear();
      (DT.scene.objects || []).forEach(function (o) {
        if (['terrain', 'internal_roads', 'fence', 'pv_row', 'pv_array',
             'earthing_pit'].indexOf(o.layer) >= 0) return;
        var p = (o.transform || {}).position || [0, 0, 0];
        var spr = makeLabel(o.label, p);
        spr.visible = !!DT.state.labelsVisible;
        t.scene.add(spr); t.labelSprites.push(spr);
      });
    }
  };

  // ---------- dashboard cards ----------
  DT.dashboard = {
    update: function (summary) {
      var site = (DT.scene || {}).site || {};
      var pv = ((DT.scene || {}).pv || {}).meta || {};
      var set = function (id, v) { var e = document.getElementById(id); if (e) e.textContent = v; };
      var kwp = (summary && summary.kwp) || pv.kwp || 0;
      set('dt-sum-dc', DT.util.fmt(kwp / 1000, 1) + ' MWp');
      set('dt-sum-ac', DT.util.fmt(kwp / 1000 / 1.2, 1) + ' MWac');
      set('dt-sum-modules', DT.util.fmt((summary && summary.modules) || pv.n_modules_planned));
      set('dt-sum-rows', DT.util.fmt((summary && summary.rows) || pv.n_rows));
      set('dt-sum-inv', DT.util.fmt(((DT.scene || {}).inverters || []).length));
      set('dt-sum-land', DT.util.fmt((summary && summary.land_area_ha) || site.land_area_ha, 1) + ' ha');
    }
  };

  // ---------- UI wiring ----------
  function wire() {
    // Layer toggles.
    document.querySelectorAll('.dt-layer-cb').forEach(function (cb) {
      cb.addEventListener('change', function () {
        DT.modes.setLayerVisible(cb.dataset.layer, cb.checked);
      });
    });
    // Timeline.
    var mEl = document.getElementById('tl-month'), hEl = document.getElementById('tl-hour');
    var mv = document.getElementById('tl-month-val'), hv = document.getElementById('tl-hour-val');
    function tl() {
      if (mv) mv.textContent = mEl.value;
      if (hv) hv.textContent = parseFloat(hEl.value).toFixed(2);
      DT.sun.update(parseInt(mEl.value, 10), parseFloat(hEl.value)).then(function () {
        if (DT.state.simulationMode === 'shadow') DT.shadow.refresh();
      });
    }
    if (mEl) mEl.addEventListener('input', tl);
    if (hEl) hEl.addEventListener('input', tl);
    var playBtn = document.getElementById('tl-play'), playing = false, timer = null;
    if (playBtn) playBtn.addEventListener('click', function () {
      playing = !playing;
      playBtn.innerHTML = playing ? '<i class="bi bi-pause-fill"></i>' : '<i class="bi bi-play-fill"></i>';
      if (playing) timer = setInterval(function () {
        var hnew = parseFloat(hEl.value) + 0.25; if (hnew > 19) hnew = 5;
        hEl.value = hnew; tl();
      }, 220); else if (timer) clearInterval(timer);
    });
    // Camera presets + sim modes + VR cards (event delegation).
    document.querySelectorAll('.dt-cam-btn').forEach(function (b) {
      b.addEventListener('click', function () { DT.cameras.goPreset(b.dataset.cam); });
    });
    document.querySelectorAll('.dt-mode-btn').forEach(function (b) {
      b.addEventListener('click', function () { DT.modes.setMode(b.dataset.mode); });
    });
    document.querySelectorAll('.dt-vr-card').forEach(function (b) {
      b.addEventListener('click', function () { DT.cameras.goVr(b.dataset.vr); });
    });
    // Analysis tabs.
    document.querySelectorAll('.dt-analysis-tab').forEach(function (b) {
      b.addEventListener('click', function () { DT.modes.setAnalysisTab(b.dataset.tab); });
    });
    // Graphics tier.
    var tier = document.getElementById('dt-tier');
    if (tier) tier.addEventListener('change', function () {
      DT.state.graphicsTier = tier.value;
      DT.materials.reset();
      if (DT.three.renderer.shadowMap) DT.three.renderer.shadowMap.enabled = (tier.value !== 'low');
      DT.builder.rebuild(DT.scene);
    });
    // Parameters + exports.
    bind('dt-run-sim', function () { DT.params.apply(); });
    bind('exp-png', function () { DT.exports.png(); });
    bind('exp-json', function () { DT.exports.sceneJson(); });
    bind('exp-schedule', function () { DT.exports.objectSchedule(); });
    bind('exp-shadow', function () { DT.exports.shadowReport(); });
    // Delegated action buttons rendered inside the details panel.
    document.addEventListener('click', function (ev) {
      var a = ev.target.closest('.dt-action-btn');
      if (a) { DT.actions.apply(a.dataset.action, JSON.parse(a.dataset.params || '{}')); return; }
      var d = ev.target.closest('.dt-drag-btn');
      if (d) { DT.actions.beginDrag(d.dataset.oid); }
    });
  }
  function bind(id, fn) { var e = document.getElementById(id); if (e) e.addEventListener('click', fn); }

  // ---------- render loop ----------
  function loop() {
    var t = DT.three;
    var now = performance.now(), dt = now - lastFrame; lastFrame = now;
    fpsAcc += dt; frames++;
    if (frames % 30 === 0) {
      var fps = Math.round(1000 * 30 / fpsAcc); fpsAcc = 0;
      var el = document.getElementById('hud-fps'); if (el) el.textContent = fps + ' fps';
    }
    // Distance-cull labels.
    if (DT.state.labelsVisible && t.labelSprites.length) {
      var cp = t.camera.position;
      t.labelSprites.forEach(function (s) {
        var d = s.position.distanceTo(cp);
        s.visible = d < 600;
      });
    }
    if (t.controls) t.controls.update();
    if (t.renderer) t.renderer.render(t.scene, t.camera);
    requestAnimationFrame(loop);
  }

  // ---------- start ----------
  function start() {
    loadScene().then(function (scene) {
      DT.scene = scene; DT.state.sceneData = scene;
      DT.state.projectId = window.DT_PROJECT_PID || (scene.site || {}).pid || null;
      DT.state.graphicsTier = (scene.performance || {}).recommended_tier || 'medium';
      var tierSel = document.getElementById('dt-tier');
      if (tierSel) tierSel.value = DT.state.graphicsTier;
      if (!init()) return;
      DT.three.sunDistance = (((scene.terrain || {}).side_m) || 300) * 1.5;
      // Initial camera from server-provided view.
      var cam = (scene.camera || {}).position;
      if (cam) DT.three.camera.position.set(cam[0], cam[1], cam[2]);
      DT.builder.build();
      DT.labels.rebuild();
      DT.selection.init();
      DT.params && DT.params.render();
      DT.dashboard.update(null);
      DT.sun.update(DT.state.sun.month, DT.state.sun.hour).then(function () {
        DT.sun.buildArc(DT.state.sun.month);
      });
      wire();
      DT.modes.setMode('three_d');
      DT.actions && DT.actions.recommendations();
      var l = document.getElementById('dt-hud-loading'); if (l) l.style.display = 'none';
      requestAnimationFrame(loop);
    }).catch(function (e) {
      var l = document.getElementById('dt-hud-loading');
      if (l) l.innerHTML = '<span class="text-danger">3D scene failed to load. ' +
        'Please refresh.</span>';
      if (window.console) console.error('DT start failed', e);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
  DT.main = { start: start };
})();
