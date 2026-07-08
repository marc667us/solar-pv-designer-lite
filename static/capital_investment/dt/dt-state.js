/* dt-state.js -- Digital Twin shared state + event bus + object index.
 *
 * One global namespace (window.DT) that every other dt-*.js module attaches
 * to. No build step: these are plain UMD-style scripts loaded in order after
 * the vendored Three.js global (THREE). All modules are defensive -- a missing
 * DOM node or scene field must never blank the viewport.
 *
 * Public shape:
 *   DT.state      -- reactive-ish design/session state (see below)
 *   DT.three      -- { scene, camera, renderer, controls, raycaster, mouse }
 *   DT.scene      -- the server scene-graph JSON (dt_scene_v2)
 *   DT.objectIndex-- Map(objectId -> { object, mesh, instanceId })
 *   DT.bus        -- tiny pub/sub: on(evt, fn), off(evt, fn), emit(evt, data)
 *   DT.util       -- small shared helpers
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};

  // ---- session + design state (single source of truth on the client) ----
  DT.state = {
    projectId: null,
    sceneData: null,          // server scene-graph (dt_scene_v2)
    selectedObjectId: null,
    hoveredObjectId: null,
    hiddenLayers: {},         // layerCode -> true when hidden
    lockedObjects: {},        // objectId -> true when locked (client-local)
    simulationMode: 'three_d',
    graphicsTier: 'medium',   // low | medium | high
    labelsVisible: false,
    sun: { month: 6, hour: 12, altitudeDeg: 0, azimuthDeg: 180, isDaylight: true },
    dirty: false              // unsaved client preview edits present
  };

  // Three.js live handles, filled by dt-main during bootstrap.
  DT.three = {
    scene: null, camera: null, renderer: null, controls: null,
    raycaster: null, mouse: null, sunLight: null, ambientLight: null,
    hemiLight: null, layerGroups: {}, pickables: [], instanced: {},
    sunDistance: 500, labelSprites: []
  };

  DT.scene = null;
  DT.objectIndex = new Map();

  // ---- minimal event bus (dashboard cards + panels subscribe to state) ----
  var handlers = {};
  DT.bus = {
    on: function (evt, fn) { (handlers[evt] = handlers[evt] || []).push(fn); },
    off: function (evt, fn) {
      if (!handlers[evt]) return;
      handlers[evt] = handlers[evt].filter(function (h) { return h !== fn; });
    },
    emit: function (evt, data) {
      (handlers[evt] || []).forEach(function (h) {
        try { h(data); } catch (e) { if (window.console) console.warn('DT bus', evt, e); }
      });
    }
  };

  // ---- shared helpers ----
  DT.util = {
    // Escape user/meta text before injecting into innerHTML.
    esc: function (s) {
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    },
    // Read the CSRF token the base template exposes for fetch POSTs.
    csrf: function () {
      var m = document.querySelector('meta[name="csrf-token"]');
      if (m) return m.getAttribute('content');
      var i = document.querySelector('input[name="_csrf"]');
      return i ? i.value : (window.DT_CSRF || '');
    },
    // Fetch JSON with sane defaults + a single catch point.
    getJSON: function (url) {
      return fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
    },
    postJSON: function (url, body) {
      return fetch(url, {
        method: 'POST', credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': DT.util.csrf()
        },
        body: JSON.stringify(body || {})
      }).then(function (r) { return r.json().catch(function () { return {}; }); });
    },
    // Locate an object record in the server scene graph by id.
    findObject: function (id) {
      var e = DT.objectIndex.get(id);
      return e ? e.object : null;
    },
    fmt: function (n, d) {
      if (n == null || isNaN(n)) return '--';
      return Number(n).toLocaleString(undefined, { maximumFractionDigits: d == null ? 0 : d });
    }
  };

  // Rebuild the object index from the current scene graph.
  DT.reindex = function () {
    DT.objectIndex = new Map();
    var objs = (DT.scene && DT.scene.objects) || [];
    objs.forEach(function (o) { DT.objectIndex.set(o.id, { object: o, mesh: null, instanceId: null }); });
  };
})();
