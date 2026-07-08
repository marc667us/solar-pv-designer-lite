/* dt-parameter-panel.js -- live Design-Parameters round-trip (Phase 3).
 *
 * Renders inputs from DT.scene.parameters.editable (grouped by section), and
 * on Apply POSTs the changed values to /dt/parameters. The server updates the
 * EXISTING project JSON blobs, re-runs size_utility_pv and returns a fresh
 * scene + summary. We rebuild only the 3D groups (no page reload) and keep the
 * camera + current selection. This is the server-authoritative update path.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};

  function render() {
    var host = document.getElementById('dt-param-body');
    if (!host) return;
    var editable = ((DT.scene || {}).parameters || {}).editable || {};
    var groups = {};
    Object.keys(editable).forEach(function (path) {
      var p = editable[path];
      (groups[p.group] = groups[p.group] || []).push({ path: path, p: p });
    });
    var html = '';
    Object.keys(groups).forEach(function (grp) {
      html += '<div class="text-secondary mb-1" style="font-size:10px;letter-spacing:.5px;' +
        'text-transform:uppercase">' + DT.util.esc(grp) + '</div>';
      groups[grp].forEach(function (row) {
        var p = row.p;
        html += '<div class="d-flex align-items-center gap-2 mb-1">' +
          '<label class="small text-secondary flex-fill" style="min-width:90px">' +
          DT.util.esc(p.label) + '</label>' +
          '<input class="form-control form-control-sm dt-param" style="max-width:96px" ' +
          'type="number" data-path="' + DT.util.esc(row.path) + '" ' +
          'value="' + DT.util.esc(p.value) + '" min="' + p.min + '" max="' + p.max +
          '" step="' + p.step + '">' +
          '<span class="text-secondary small" style="min-width:30px">' + DT.util.esc(p.unit) + '</span>' +
          '</div>';
      });
    });
    host.innerHTML = html;
  }

  function collect() {
    var pv = {}, facility = {};
    document.querySelectorAll('.dt-param').forEach(function (inp) {
      var path = inp.getAttribute('data-path');
      var val = parseFloat(inp.value);
      if (isNaN(val)) return;
      if (path.indexOf('pv.') === 0) pv[path.slice(3)] = val;
      else if (path === 'facility.battery_kwh') facility.battery_kwh = val;
    });
    return { pv: pv, facility: facility };
  }

  function setBusy(busy) {
    var btn = document.getElementById('dt-run-sim');
    if (!btn) return;
    btn.disabled = busy;
    btn.innerHTML = busy ? '<span class="spinner-border spinner-border-sm me-1"></span>Updating...'
                         : '<i class="bi bi-play-fill me-1"></i>Run Simulation';
  }

  function apply() {
    if (!window.DT_PARAMS_URL) return;
    setBusy(true);
    var keepSel = DT.state.selectedObjectId;
    DT.util.postJSON(window.DT_PARAMS_URL, collect()).then(function (resp) {
      setBusy(false);
      if (!resp || !resp.ok || !resp.scene) {
        flash('Parameter update failed.', 'danger'); return;
      }
      DT.builder.rebuild(resp.scene);       // swap geometry in place
      render();                             // refresh inputs to clamped values
      DT.dashboard && DT.dashboard.update(resp.summary);
      if (keepSel && DT.objectIndex.has(keepSel)) DT.selection.select(keepSel);
      // Re-apply shadow tint if we are in shadow mode.
      if (DT.state.simulationMode === 'shadow' && DT.shadow) DT.shadow.refresh();
      flash('Design updated -- BOQ & finance marked for recompute.', 'success');
    }).catch(function () { setBusy(false); flash('Parameter update error.', 'danger'); });
  }

  function flash(msg, kind) {
    var el = document.getElementById('dt-flash');
    if (!el) return;
    el.className = 'alert alert-' + (kind || 'info') + ' py-1 px-2 small';
    el.textContent = msg;
    el.style.display = '';
    setTimeout(function () { el.style.display = 'none'; }, 4000);
  }

  DT.params = { render: render, apply: apply, collect: collect };
})();
