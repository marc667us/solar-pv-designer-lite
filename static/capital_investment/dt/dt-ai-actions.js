/* dt-ai-actions.js -- object actions, drag, AI recommendations (Phase 6).
 *
 * - objectActionsHtml(o): action buttons injected into the details panel.
 * - apply(action, params): POST /dt/object-action; the server persists to the
 *   existing config blobs and returns a fresh scene, which we rebuild in place.
 * - recommendations(): derives engineering advice from the last shadow analysis
 *   plus simple layout heuristics; each rec has an Apply button that calls a
 *   real server action (rows move, shadows/BOQ recompute).
 * - beginDrag(id): drag a movable object across the ground; persist on confirm.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var esc = DT.util.esc;

  function objectActionsHtml(o) {
    var eng = o.engineering || {};
    var parts = [];
    if (o.layer === 'pv_row' || o.layer === 'pv_array') {
      parts.push(btn('increase_row_spacing', 'Increase spacing', 'bi-arrows-expand', { delta_m: 0.5 }));
      parts.push(btn('decrease_row_spacing', 'Decrease spacing', 'bi-arrows-collapse', { delta_m: 0.5 }));
    }
    if (eng.movable && o.layer.indexOf('transformer') === 0) {
      parts.push('<button class="btn btn-sm btn-outline-info text-start dt-drag-btn" ' +
        'data-oid="' + esc(o.id) + '"><i class="bi bi-arrows-move me-1"></i>Move (drag on ground)</button>');
    }
    if (!parts.length) return '';
    return '<hr style="border-color:#1e1e3a"><div class="text-secondary mb-1" ' +
      'style="font-size:10px;letter-spacing:.5px">ACTIONS</div><div class="d-grid gap-1">' +
      parts.join('') + '</div>';
  }
  function btn(action, label, icon, params) {
    return '<button class="btn btn-sm btn-outline-info text-start dt-action-btn" ' +
      'data-action="' + esc(action) + '" data-params=\'' + esc(JSON.stringify(params || {})) +
      '\'><i class="bi ' + icon + ' me-1"></i>' + esc(label) + '</button>';
  }

  function apply(action, params) {
    if (!window.DT_ACTION_URL) return Promise.resolve();
    var keepSel = DT.state.selectedObjectId;
    return DT.util.postJSON(window.DT_ACTION_URL, { action: action, params: params || {} })
      .then(function (resp) {
        if (!resp || !resp.ok || !resp.scene) { toast(resp && resp.message || 'Action failed.'); return; }
        DT.builder.rebuild(resp.scene);
        DT.params && DT.params.render();
        if (keepSel && DT.objectIndex.has(keepSel)) DT.selection.select(keepSel);
        if (DT.state.simulationMode === 'shadow' && DT.shadow) DT.shadow.refresh();
        recommendations();
        toast(resp.message || 'Applied.');
      });
  }

  function toast(msg) {
    var el = document.getElementById('dt-flash');
    if (!el) { return; }
    el.className = 'alert alert-info py-1 px-2 small'; el.textContent = msg; el.style.display = '';
    setTimeout(function () { el.style.display = 'none'; }, 4000);
  }

  // ---- AI recommendation panel ----
  function recommendations() {
    var host = document.getElementById('dt-ai-body');
    if (!host) return;
    var recs = [];
    var sh = DT.shadow && DT.shadow.last();
    if (sh && sh.affected_objects) {
      sh.affected_objects.filter(function (a) { return a.severity === 'heavy' || a.severity === 'moderate'; })
        .slice(0, 4).forEach(function (a) {
          recs.push({
            severity: a.severity === 'heavy' ? 'high' : 'medium',
            object_id: a.object_id,
            message: 'Shading on ' + a.object_id + ' is ' + a.shadow_loss_pct + '% at this time.',
            action: 'increase_row_spacing', params: { delta_m: 0.5 },
            action_label: 'Increase row spacing +0.5m'
          });
        });
    }
    // Heuristic: transformer far from the PV field centroid inflates cabling.
    var xf = null; DT.objectIndex.forEach(function (v) {
      if (!xf && v.object && v.object.layer.indexOf('transformer') === 0) xf = v.object;
    });
    if (xf) {
      var p = (xf.transform || {}).position || [0, 0, 0];
      var dist = Math.sqrt(p[0] * p[0] + p[2] * p[2]);
      var side = ((DT.scene.terrain || {}).side_m) || 300;
      if (dist > side * 0.45) {
        recs.push({
          severity: 'low', object_id: xf.id,
          message: 'Transformer is near the site edge; central placement can cut MV cable cost.',
          action: null, action_label: null
        });
      }
    }
    if (!recs.length) {
      host.innerHTML = '<div class="text-secondary small">No engineering flags at the current ' +
        'design / sun position. Run Shadow Analysis to surface shading advice.</div>';
      return;
    }
    host.innerHTML = recs.map(function (r, i) {
      var col = r.severity === 'high' ? 'danger' : r.severity === 'medium' ? 'warning' : 'secondary';
      return '<div class="border rounded p-2 mb-2" style="border-color:#1e1e3a!important">' +
        '<div><span class="badge bg-' + col + '">' + r.severity + '</span> ' +
        '<a href="#" class="small dt-rec-focus" data-oid="' + esc(r.object_id) + '">' +
        esc(r.object_id) + '</a></div>' +
        '<div class="small my-1">' + esc(r.message) + '</div>' +
        (r.action ? '<button class="btn btn-sm btn-warning dt-rec-apply" data-i="' + i +
          '"><i class="bi bi-magic me-1"></i>' + esc(r.action_label) + '</button>' : '') +
        '</div>';
    }).join('');
    host.querySelectorAll('.dt-rec-focus').forEach(function (a) {
      a.addEventListener('click', function (e) { e.preventDefault(); DT.selection.select(a.getAttribute('data-oid')); });
    });
    host.querySelectorAll('.dt-rec-apply').forEach(function (b) {
      b.addEventListener('click', function () {
        var r = recs[+b.getAttribute('data-i')];
        apply(r.action, r.params);
      });
    });
  }

  // ---- drag a movable object on the ground plane ----
  var drag = null;
  function beginDrag(objId) {
    var o = DT.util.findObject(objId); if (!o) return;
    var t = DT.three, THREE = window.THREE;
    if (t.controls) t.controls.enabled = false;
    drag = { id: objId, plane: new THREE.Plane(new THREE.Vector3(0, 1, 0), 0) };
    toast('Drag to reposition, release to place, then confirm.');
    var el = t.renderer.domElement;
    function move(ev) {
      var rect = el.getBoundingClientRect();
      t.mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      t.mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      t.raycaster.setFromCamera(t.mouse, t.camera);
      var pt = new THREE.Vector3();
      if (t.raycaster.ray.intersectPlane(drag.plane, pt)) {
        drag.x = pt.x; drag.z = pt.z;
        DT.selection.placeHighlightAt && DT.selection.placeHighlightAt(pt.x, pt.z);
        var rec = DT.objectIndex.get(objId);
        if (rec && rec.mesh && rec.mesh.position) { rec.mesh.position.x = pt.x; rec.mesh.position.z = pt.z; }
      }
    }
    function up() {
      el.removeEventListener('mousemove', move);
      el.removeEventListener('mouseup', up);
      if (t.controls) t.controls.enabled = true;
      if (drag && drag.x != null && window.confirm('Move transformer here? Cable quantities will need recompute.')) {
        apply('move_transformer', { x: Math.round(drag.x), z: Math.round(drag.z) });
      } else {
        DT.builder.rebuild(DT.scene);  // snap back
      }
      drag = null;
    }
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseup', up);
  }

  DT.actions = { objectActionsHtml: objectActionsHtml, apply: apply,
                 recommendations: recommendations, beginDrag: beginDrag };
})();
