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

  // Build a vertical sky-gradient texture (zenith at top -> horizon haze at the
  // bottom) for scene.background. A 2px-wide tall canvas is enough -- the GPU
  // stretches it across the viewport, giving a smooth atmospheric sky rather
  // than a flat colour. Colours are passed as 0xRRGGBB ints.
  function _skyGradientTexture(THREE, zenithHex, horizonHex) {
    var c = document.createElement('canvas'); c.width = 2; c.height = 512;
    var ctx = c.getContext('2d');
    function hex(n) { return '#' + ('000000' + n.toString(16)).slice(-6); }
    var g = ctx.createLinearGradient(0, 0, 0, 512);
    g.addColorStop(0.0, hex(zenithHex));
    g.addColorStop(0.55, hex(zenithHex));
    g.addColorStop(1.0, hex(horizonHex));
    ctx.fillStyle = g; ctx.fillRect(0, 0, 2, 512);
    var tex = new THREE.CanvasTexture(c);
    if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
    tex.needsUpdate = true;
    return tex;
  }

  // ---------- three.js bootstrap ----------
  function init() {
    var THREE = window.THREE;
    var vp = document.getElementById('dt-viewport');
    if (!vp || !THREE) return false;
    var w = vp.clientWidth || 800, h = vp.clientHeight || 500;
    var t = DT.three;
    t.scene = new THREE.Scene();
    // Atmospheric sky: a vertical gradient (deep blue zenith -> pale haze at the
    // horizon) instead of a flat fill, which read as a bad wall of colour behind
    // the farm. The fog colour matches the horizon so distant ground melts into
    // the haze the same way it does in the reference aerial.
    var HORIZON = 0xc4d8e6, ZENITH = 0x4a86c8;
    t.scene.background = _skyGradientTexture(THREE, ZENITH, HORIZON);
    t.skyTexture = t.scene.background;   // kept so the sun update can restore it
    t.horizonHex = HORIZON;
    t.scene.fog = new THREE.Fog(HORIZON, 600, 7000);

    t.camera = new THREE.PerspectiveCamera(45, w / h, 0.5, 12000);
    t.camera.position.set(200, 160, 200);

    t.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    t.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    t.renderer.setSize(w, h);
    // Physically-based colour pipeline: filmic tone-mapping + sRGB output turns
    // the flat, video-gamey look into a photographic one. Guarded for r147
    // (outputColorSpace) vs older (outputEncoding) builds.
    t.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    t.renderer.toneMappingExposure = 1.05;
    if ('outputColorSpace' in t.renderer && THREE.SRGBColorSpace) {
      t.renderer.outputColorSpace = THREE.SRGBColorSpace;
    } else if ('outputEncoding' in t.renderer && THREE.sRGBEncoding) {
      t.renderer.outputEncoding = THREE.sRGBEncoding;
    }
    if (t.renderer.shadowMap) {
      t.renderer.shadowMap.enabled = (DT.state.graphicsTier !== 'low');
      if (THREE.PCFSoftShadowMap) t.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
    vp.appendChild(t.renderer.domElement);

    // Image-based lighting: turn the sky gradient into a pre-filtered
    // environment map so panel glass, aluminium frames and steel pick up real
    // sky reflections. scene.environment auto-applies to every StandardMaterial
    // -- the single biggest realism win, and cheap (2px equirect source).
    try {
      if (THREE.PMREMGenerator) {
        var eq = _skyGradientTexture(THREE, ZENITH, HORIZON);
        eq.mapping = THREE.EquirectangularReflectionMapping;
        var pmrem = new THREE.PMREMGenerator(t.renderer);
        pmrem.compileEquirectangularShader();
        t.scene.environment = pmrem.fromEquirectangular(eq).texture;
        eq.dispose(); pmrem.dispose();
      }
    } catch (e) { /* env map optional -- scene still renders without it */ }

    t.controls = new THREE.OrbitControls(t.camera, t.renderer.domElement);
    t.controls.enableDamping = true;
    t.controls.dampingFactor = 0.06;
    t.controls.maxPolarAngle = Math.PI * 0.495;
    t.controls.target.set(0, 0, 0);
    t.controls.update();

    // Env map already provides soft sky fill, so keep ambient low to preserve
    // contrast (a high ambient is what makes primitive scenes look flat).
    t.ambientLight = new THREE.AmbientLight(0xffffff, 0.18);
    t.scene.add(t.ambientLight);
    t.hemiLight = new THREE.HemisphereLight(0xbcd4ec, 0x4e6b32, 0.35);
    t.scene.add(t.hemiLight);
    t.sunLight = new THREE.DirectionalLight(0xfff1d0, 2.2);
    t.sunLight.position.set(600, 700, 400);
    if (t.sunLight.shadow && DT.state.graphicsTier !== 'low') {
      t.sunLight.castShadow = true;
      t.sunLight.shadow.mapSize.set(2048, 2048);
      var sc = t.sunLight.shadow.camera;
      sc.near = 10; sc.far = 3500;
      sc.left = -900; sc.right = 900; sc.top = 900; sc.bottom = -900;
      sc.updateProjectionMatrix();
      t.sunLight.shadow.bias = -0.0004;
      t.sunLight.shadow.normalBias = 0.6;
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
    // Render the label canvas at high resolution (4x the old 256x64) so the
    // sprite text stays crisp when the camera is close -- the previous 256x64
    // texture was magnified onto the sprite and looked blurred. Font scales
    // with the canvas; rounded pill background reads cleaner than a hard rect.
    var W = 1024, H = 256, pad = 28, r = 40;
    var c = document.createElement('canvas'); c.width = W; c.height = H;
    var ctx = c.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(10,16,21,0.82)';
    // rounded-rect pill
    ctx.beginPath();
    ctx.moveTo(r, 0); ctx.arcTo(W, 0, W, H, r); ctx.arcTo(W, H, 0, H, r);
    ctx.arcTo(0, H, 0, 0, r); ctx.arcTo(0, 0, W, 0, r); ctx.closePath(); ctx.fill();
    ctx.fillStyle = '#ffd54a';
    ctx.font = 'bold 88px "Segoe UI", Arial, sans-serif';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(text).slice(0, 22), pad, H / 2 + 4);
    var tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;   // no mipmaps -> no shimmer, stays sharp
    tex.magFilter = THREE.LinearFilter;
    if (THREE.SRGBColorSpace) tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    var spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
    spr.position.set(pos[0], pos[1] + 6, pos[2]);
    spr.scale.set(28, 7, 1);   // world size; texture aspect 4:1 matches 28:7
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
    // Distance-cull labels -- scaled to the site so a big farm's equipment
    // labels don't vanish (a flat 600 m cut hid every building on a 775 m site).
    if (DT.state.labelsVisible && t.labelSprites.length) {
      var cp = t.camera.position;
      var cull = Math.max(700, (((DT.scene || {}).terrain || {}).side_m || 400) * 2.5);
      t.labelSprites.forEach(function (s) {
        s.visible = s.position.distanceTo(cp) < cull;
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
