/* dt-shadow-analysis.js -- server shadow analysis + per-row tint (Phase 5).
 *
 * Fetches /dt/shadow-analysis.json for the current sun (month/hour), colours
 * the affected PV-row instances by severity (none/light/moderate/heavy) and
 * fills the right-panel Shadow card + object simulation metadata. Row-level,
 * conservative -- it is labelled an engineering estimate, not a bankable trace.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var shadowMat = null, lastResult = null;

  function shadowUrl() {
    return (window.DT_SHADOW_URL || '') + '?month=' + DT.state.sun.month +
      '&hour=' + DT.state.sun.hour;
  }

  function ensureShadowMat() {
    if (shadowMat) return shadowMat;
    shadowMat = new window.THREE.MeshLambertMaterial({ color: 0xffffff });
    return shadowMat;
  }

  // Apply severity colours to the PV-row InstancedMesh via instanceColor.
  function tint(result) {
    var inst = DT.three.instanced.pv_row, THREE = window.THREE;
    if (!inst) return;
    inst.material = ensureShadowMat();     // white base so instanceColor reads true
    var bySev = {};
    (result.affected_objects || []).forEach(function (a) { bySev[a.object_id] = a.severity; });
    var map = (inst.userData || {}).instancedRows || [];
    for (var i = 0; i < map.length; i++) {
      var sev = bySev[map[i]] || 'none';
      inst.setColorAt(i, new THREE.Color(DT.materials.severityColor(sev)));
    }
    if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
    // Write severity back onto the object graph so the details panel shows it.
    (result.affected_objects || []).forEach(function (a) {
      var o = DT.util.findObject(a.object_id);
      if (o) {
        o.simulation = o.simulation || {};
        o.simulation.shadow = { severity: a.severity, loss_pct: a.shadow_loss_pct,
                                caused_by: a.caused_by || [] };
        o.simulation.irradiance_wm2 = a.irradiance_wm2;
      }
    });
  }

  function clearTint() {
    var inst = DT.three.instanced.pv_row, THREE = window.THREE;
    if (!inst) return;
    inst.material = DT.materials.get('pv_glass');
    if (inst.instanceColor) {
      var map = (inst.userData || {}).instancedRows || [];
      for (var i = 0; i < map.length; i++) inst.setColorAt(i, new THREE.Color(0xffffff));
      inst.instanceColor.needsUpdate = true;
    }
  }

  function renderPanel(result) {
    var body = document.getElementById('dt-shadow-body');
    if (!body) return;
    if (result.is_night) {
      body.innerHTML = '<div class="text-secondary small">Sun is below the horizon ' +
        '-- no shading at this time.</div>';
      return;
    }
    var s = result.summary || {};
    var html = '<div class="d-flex gap-2 mb-2">' +
      pill('Affected rows', s.affected_rows || 0) +
      pill('Weighted loss', (s.weighted_loss_pct || 0) + '%') + '</div>';
    html += '<div class="d-flex flex-wrap gap-1 mb-2">' +
      legend('none') + legend('light') + legend('moderate') + legend('heavy') + '</div>';
    var rows = (result.affected_objects || []).slice().sort(function (a, b) {
      return (b.shadow_loss_pct || 0) - (a.shadow_loss_pct || 0);
    }).slice(0, 12);
    if (!rows.length) {
      html += '<div class="text-secondary small">No significant shading detected.</div>';
    } else {
      html += '<table class="table table-dark table-sm small mb-0"><tbody>';
      rows.forEach(function (a) {
        html += '<tr style="cursor:pointer" data-oid="' + DT.util.esc(a.object_id) + '">' +
          '<td><span style="display:inline-block;width:9px;height:9px;background:' +
          DT.materials.severityColor(a.severity) + ';margin-right:5px"></span>' +
          DT.util.esc(a.object_id) + '</td>' +
          '<td class="text-end">' + (a.shadow_loss_pct || 0) + '%</td>' +
          '<td class="text-end text-secondary">' + DT.util.fmt(a.energy_loss_kwh_day, 1) + ' kWh/d</td></tr>';
      });
      html += '</tbody></table>';
    }
    body.innerHTML = html;
    body.querySelectorAll('[data-oid]').forEach(function (tr) {
      tr.addEventListener('click', function () { DT.selection.select(tr.getAttribute('data-oid')); });
    });
  }
  function pill(k, v) {
    return '<div class="flex-fill text-center border rounded py-1" style="border-color:#1e1e3a!important">' +
      '<div class="text-secondary" style="font-size:10px">' + k + '</div>' +
      '<div class="text-warning fw-bold">' + v + '</div></div>';
  }
  function legend(sev) {
    return '<span class="small text-secondary"><span style="display:inline-block;width:9px;height:9px;' +
      'background:' + DT.materials.severityColor(sev) + ';margin-right:3px"></span>' + sev + '</span>';
  }

  function refresh() {
    return DT.util.getJSON(shadowUrl()).then(function (result) {
      lastResult = result;
      if (DT.state.simulationMode === 'shadow') tint(result);
      renderPanel(result);
      DT.bus.emit('shadow:updated', result);
      return result;
    }).catch(function () { });
  }

  DT.shadow = { refresh: refresh, clearTint: clearTint, tint: tint,
                last: function () { return lastResult; } };
})();
