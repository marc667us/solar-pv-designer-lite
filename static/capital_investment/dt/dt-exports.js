/* dt-exports.js -- engineering exports (Phase 8).
 *
 * Reuses existing surfaces where possible:
 *   - PNG        : client canvas snapshot (preserveDrawingBuffer renderer).
 *   - Scene JSON : the dt_scene_v2 graph (includes schema_version).
 *   - Object schedule : GET /dt/object-schedule.json (BOQ-linked).
 *   - Shadow report   : GET /dt/shadow-analysis.json for the current sun.
 *   - Technical report: links to the existing Step 13 report surface.
 * No new PDF/report engine is created here.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};

  function download(name, blob) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = name; a.click();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function png() {
    var r = DT.three.renderer;
    if (!r) return;
    r.render(DT.three.scene, DT.three.camera);
    var a = document.createElement('a');
    a.href = r.domElement.toDataURL('image/png');
    a.download = 'digital_twin_pid' + (DT.state.projectId || 'x') + '.png';
    a.click();
  }

  function sceneJson() {
    download('digital_twin_scene_pid' + (DT.state.projectId || 'x') + '.json',
      new Blob([JSON.stringify(DT.scene, null, 2)], { type: 'application/json' }));
  }

  function objectSchedule() {
    if (!window.DT_SCHEDULE_URL) return;
    DT.util.getJSON(window.DT_SCHEDULE_URL).then(function (data) {
      download('object_schedule_pid' + (DT.state.projectId || 'x') + '.json',
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    });
  }

  function shadowReport() {
    if (!window.DT_SHADOW_URL) return;
    var url = window.DT_SHADOW_URL + '?month=' + DT.state.sun.month + '&hour=' + DT.state.sun.hour;
    DT.util.getJSON(url).then(function (data) {
      download('shadow_report_pid' + (DT.state.projectId || 'x') + '.json',
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    });
  }

  DT.exports = { png: png, sceneJson: sceneJson, objectSchedule: objectSchedule,
                 shadowReport: shadowReport };
})();
