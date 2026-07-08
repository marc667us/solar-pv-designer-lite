/* dt-simulation-modes.js -- data-driven simulation modes (Phase 4).
 *
 * Reads DT.scene.simulation_modes (9 modes described server-side) and applies
 * each as a real change of camera preset + visible layers + labels + lighting
 * profile + active analysis tab -- never just a label swap. Also owns the
 * layer-visibility API used by the left-nav checkboxes and the context menu.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};

  function setLayerVisible(layer, vis) {
    DT.state.hiddenLayers[layer] = !vis;
    var g = DT.three.layerGroups[layer];
    if (g) g.visible = vis;
    var cb = document.querySelector('.dt-layer-cb[data-layer="' + layer + '"]');
    if (cb) cb.checked = vis;
  }

  function showAllLayers() {
    Object.keys(DT.three.layerGroups).forEach(function (l) { setLayerVisible(l, true); });
  }

  function isolateLayer(layer) {
    Object.keys(DT.three.layerGroups).forEach(function (l) { setLayerVisible(l, l === layer); });
  }

  function applyLayers(spec) {
    if (spec === 'all' || !spec) { showAllLayers(); return; }
    var keep = {}; (spec || []).forEach(function (l) { keep[l] = true; });
    Object.keys(DT.three.layerGroups).forEach(function (l) { setLayerVisible(l, !!keep[l]); });
  }

  function setLightingProfile(profile) {
    var t = DT.three, THREE = window.THREE;
    if (!t.sunLight) return;
    if (profile === 'night') {
      t.sunLight.intensity = 0.05;
      if (t.ambientLight) t.ambientLight.intensity = 0.15;
      if (t.scene) t.scene.background = new THREE.Color(0x05060f);
    } else if (profile === 'flat') {
      t.sunLight.intensity = 0.2;
      if (t.ambientLight) t.ambientLight.intensity = 0.95;
      if (t.scene) t.scene.background = new THREE.Color(0x11151c);
    } else { // day -- restore from the current sun
      DT.sun && DT.sun.update(DT.state.sun.month, DT.state.sun.hour);
    }
  }

  function setLabelsVisible(vis) {
    DT.state.labelsVisible = vis;
    DT.three.labelSprites.forEach(function (s) { s.visible = vis; });
  }

  function setAnalysisTab(tab) {
    var tabs = document.querySelectorAll('.dt-analysis-tab');
    var panes = document.querySelectorAll('.dt-analysis-pane');
    tabs.forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === tab); });
    panes.forEach(function (p) { p.style.display = p.getAttribute('data-pane') === tab ? '' : 'none'; });
    if (tab === 'shadow' && DT.shadow) DT.shadow.refresh();
  }

  function setMode(modeKey) {
    var modes = (DT.scene && DT.scene.simulation_modes) || {};
    var m = modes[modeKey];
    if (!m) return;
    DT.state.simulationMode = modeKey;
    if (m.camera && DT.cameras) DT.cameras.goPreset(m.camera);
    applyLayers(m.layers);
    setLightingProfile(m.lighting || 'day');
    setLabelsVisible(!!m.labels);
    if (m.analysis) setAnalysisTab(m.analysis);
    // Shadow mode colours the PV rows; other modes clear the tint.
    if (DT.shadow) { if (modeKey === 'shadow') DT.shadow.refresh(); else DT.shadow.clearTint(); }
    document.querySelectorAll('.dt-mode-btn').forEach(function (b) {
      b.classList.toggle('btn-warning', b.getAttribute('data-mode') === modeKey);
      b.classList.toggle('btn-outline-warning', b.getAttribute('data-mode') !== modeKey);
    });
    DT.bus.emit('mode:changed', modeKey);
  }

  DT.modes = {
    setMode: setMode, setLayerVisible: setLayerVisible, isolateLayer: isolateLayer,
    showAllLayers: showAllLayers, setLightingProfile: setLightingProfile,
    setLabelsVisible: setLabelsVisible, setAnalysisTab: setAnalysisTab
  };
})();
