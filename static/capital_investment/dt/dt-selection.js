/* dt-selection.js -- hover, selection, context menu, details panel (Phase 2).
 *
 * Handles both regular meshes (userData.objectId) and the PV-row InstancedMesh
 * (intersection.instanceId -> userData.instancedRows[id]). Renders the right
 * property panel with identity / dimensions / quantities / warnings and links
 * into the EXISTING BOQ (step9), finance (step8), reports (step13) and
 * marketplace surfaces -- no new engines.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var esc = DT.util.esc;
  var highlight = null;   // reusable wireframe box over the selection

  function resolveHit(hit) {
    if (!hit || !hit.object) return null;
    var ud = hit.object.userData || {};
    if (ud.instancedRows && hit.instanceId != null) return ud.instancedRows[hit.instanceId];
    return ud.objectId || null;
  }

  function ensureHighlight() {
    if (highlight) return highlight;
    var THREE = window.THREE;
    var geom = new THREE.BoxGeometry(1, 1, 1);
    var edges = new THREE.EdgesGeometry(geom);
    highlight = new THREE.LineSegments(edges,
      new THREE.LineBasicMaterial({ color: 0xf59e0b }));
    highlight.visible = false;
    DT.three.scene.add(highlight);
    return highlight;
  }

  function placeHighlight(objId) {
    var h = ensureHighlight();
    var rec = DT.objectIndex.get(objId);
    if (!rec || !rec.object) { h.visible = false; return; }
    var o = rec.object, dm = o.dimensions || {}, p = (o.transform || {}).position || [0, 0, 0];
    h.scale.set((dm.w || 1) * 1.06 + 0.4, (dm.h || 1) * 1.06 + 0.4, (dm.l || 1) * 1.06 + 0.4);
    h.position.set(p[0], p[1], p[2]);
    var r = (o.transform || {}).rotation_deg || [0, 0, 0], d = Math.PI / 180;
    h.rotation.set((r[0] || 0) * d, (r[1] || 0) * d, (r[2] || 0) * d);
    h.visible = true;
  }

  function panelHtml(o) {
    var eng = o.engineering || {}, links = o.links || {}, meta = o.meta || {};
    var sim = o.simulation || {};
    var html = '<div class="mb-2"><span class="badge bg-warning text-dark">' +
      esc(o.layer) + '</span>' +
      (eng.locked ? ' <span class="badge bg-secondary">locked</span>' : '') + '</div>' +
      '<div class="fw-bold mb-1">' + esc(o.label) + '</div>' +
      '<div class="small text-secondary mb-2">id: ' + esc(o.id) + ' &middot; ' + esc(o.type) + '</div>';

    var dm = o.dimensions || {};
    html += '<table class="table table-dark table-sm small mb-2"><tbody>';
    html += row('Dimensions (w/h/l)', [dm.w, dm.h, dm.l].map(function (n) {
      return n == null ? '--' : (+n).toFixed(1);
    }).join(' / ') + ' m');
    if (eng.quantity != null) html += row('Quantity', DT.util.fmt(eng.quantity));
    if (eng.capacity_kwp != null) html += row('Capacity', DT.util.fmt(eng.capacity_kwp) + ' kWp');
    // Whitelisted meta fields only (avoid dumping noisy internal config).
    ['modules', 'row_index', 'tilt_deg', 'azimuth_deg', 'footprint_m2',
     'building_code', 'kw', 'coverage_m', 'wattage_W', 'contents',
     'resistance_ohm_target'].forEach(function (k) {
      if (meta[k] != null && !Array.isArray(meta[k])) html += row(k.replace(/_/g, ' '), esc(meta[k]));
    });
    if (sim.shadow && sim.shadow.severity && sim.shadow.severity !== 'none') {
      html += row('Shading', esc(sim.shadow.severity) + ' (' + (sim.shadow.loss_pct || 0) + '%)');
    }
    html += '</tbody></table>';

    if (sim.warnings && sim.warnings.length) {
      html += '<div class="alert alert-warning py-1 px-2 small mb-2">' +
        sim.warnings.map(function (w) { return '<div>' + esc(w) + '</div>'; }).join('') + '</div>';
    }

    // Links into existing surfaces (disabled/absent when null).
    html += '<div class="d-grid gap-1">';
    if (links.marketplace) html += linkBtn(links.marketplace, 'bi-shop', 'Marketplace');
    if (links.boq) html += linkBtn(links.boq, 'bi-list-check', 'BOQ items');
    if (links.financial) html += linkBtn(links.financial, 'bi-graph-up', 'Financials');
    if (links.reports) html += linkBtn(links.reports, 'bi-file-earmark-text', 'Reports');
    html += '</div>';
    // Object actions (Phase 6) -- rendered by dt-ai-actions if present.
    if (DT.actions && DT.actions.objectActionsHtml) html += DT.actions.objectActionsHtml(o);
    return html;
  }

  function row(k, v) {
    return '<tr><td class="text-secondary" style="font-size:11px">' + esc(k) +
      '</td><td>' + v + '</td></tr>';
  }
  function linkBtn(href, icon, label) {
    return '<a href="' + esc(href) + '" class="btn btn-sm btn-outline-warning text-start">' +
      '<i class="bi ' + icon + ' me-1"></i>' + esc(label) + '</a>';
  }

  function renderPanel(objId) {
    var panel = document.getElementById('dt-props');
    if (!panel) return;
    var o = objId ? DT.util.findObject(objId) : null;
    if (!o) {
      panel.innerHTML = '<div class="text-secondary small">Click any object in the ' +
        '3D scene to see its properties, BOQ items, and marketplace shortcut here.</div>';
      return;
    }
    panel.innerHTML = panelHtml(o);
  }

  function select(objId) {
    DT.state.selectedObjectId = objId;
    placeHighlight(objId);
    renderPanel(objId);
    DT.bus.emit('object:selected', objId);
  }

  // ---- context menu ----
  function closeMenu() {
    var m = document.getElementById('dt-context-menu');
    if (m) m.remove();
  }
  function openMenu(objId, x, y) {
    closeMenu();
    var o = DT.util.findObject(objId); if (!o) return;
    var items = [
      { k: 'hide', label: 'Hide layer', icon: 'bi-eye-slash' },
      { k: 'isolate', label: 'Isolate layer', icon: 'bi-bullseye' },
      { k: 'lock', label: (DT.state.lockedObjects[objId] ? 'Unlock' : 'Lock'), icon: 'bi-lock' }
    ];
    if ((o.links || {}).boq) items.push({ k: 'boq', label: 'View BOQ', icon: 'bi-list-check' });
    if ((o.links || {}).marketplace) items.push({ k: 'market', label: 'Marketplace', icon: 'bi-shop' });
    if ((o.engineering || {}).movable && DT.actions) items.push({ k: 'move', label: 'Move (drag)', icon: 'bi-arrows-move' });
    var el = document.createElement('div');
    el.id = 'dt-context-menu';
    el.className = 'dropdown-menu show';
    el.style.cssText = 'position:fixed;z-index:2000;left:' + x + 'px;top:' + y + 'px;display:block';
    el.innerHTML = items.map(function (it) {
      return '<button class="dropdown-item small" data-k="' + it.k + '">' +
        '<i class="bi ' + it.icon + ' me-2"></i>' + esc(it.label) + '</button>';
    }).join('');
    document.body.appendChild(el);
    el.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-k]'); if (!b) return;
      handleMenu(b.getAttribute('data-k'), o);
      closeMenu();
    });
  }
  function handleMenu(k, o) {
    if (k === 'hide') { DT.modes && DT.modes.setLayerVisible(o.layer, false); }
    else if (k === 'isolate') { DT.modes && DT.modes.isolateLayer(o.layer); }
    else if (k === 'lock') { DT.state.lockedObjects[o.id] = !DT.state.lockedObjects[o.id]; renderPanel(o.id); }
    else if (k === 'boq') { window.open((o.links || {}).boq, '_blank'); }
    else if (k === 'market') { window.open((o.links || {}).marketplace, '_blank'); }
    else if (k === 'move' && DT.actions && DT.actions.beginDrag) { DT.actions.beginDrag(o.id); }
  }

  // ---- pointer wiring ----
  function pickAt(clientX, clientY) {
    var t = DT.three, rect = t.renderer.domElement.getBoundingClientRect();
    t.mouse.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    t.mouse.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    t.raycaster.setFromCamera(t.mouse, t.camera);
    var hits = t.raycaster.intersectObjects(t.pickables, false);
    return hits.length ? resolveHit(hits[0]) : null;
  }

  function init() {
    var el = DT.three.renderer.domElement;
    el.addEventListener('click', function (ev) { select(pickAt(ev.clientX, ev.clientY)); });
    el.addEventListener('mousemove', function (ev) {
      var id = pickAt(ev.clientX, ev.clientY);
      DT.state.hoveredObjectId = id;
      el.style.cursor = id ? 'pointer' : 'default';
    });
    el.addEventListener('contextmenu', function (ev) {
      var id = pickAt(ev.clientX, ev.clientY);
      if (id) { ev.preventDefault(); openMenu(id, ev.clientX, ev.clientY); }
    });
    document.addEventListener('click', function (ev) {
      if (!ev.target.closest('#dt-context-menu')) closeMenu();
    });
    renderPanel(null);
  }

  DT.selection = { init: init, select: select, renderPanel: renderPanel,
                   placeHighlight: placeHighlight };
})();
