/* dt-materials.js -- tiered PBR material factory (Phase 7).
 *
 * Turns the server material library (scene.materials) into Three.js materials,
 * choosing fidelity by DT.state.graphicsTier:
 *   low    -> MeshLambertMaterial (cheap, no metalness/roughness), no shadows
 *   medium -> MeshStandardMaterial with modest roughness/metalness
 *   high   -> MeshStandardMaterial (full), envMap-ready
 * Materials are cached per (materialKey, tier) so 181k instanced modules share
 * one material instance -- essential for large-farm performance.
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var cache = {};

  function libEntry(key) {
    var lib = (DT.scene && DT.scene.materials) || {};
    return lib[key] || lib.building_wall || { color: '#cccccc', roughness: 0.8, metalness: 0.1 };
  }

  // Return (and cache) a Three.js material for a material-library key.
  function get(key) {
    var THREE = window.THREE;
    var tier = DT.state.graphicsTier || 'medium';
    var ck = key + '|' + tier;
    if (cache[ck]) return cache[ck];
    var e = libEntry(key);
    var color = new THREE.Color(e.color || '#cccccc');
    var mat;
    if (tier === 'low' || !THREE.MeshStandardMaterial) {
      mat = new THREE.MeshLambertMaterial({ color: color });
    } else {
      mat = new THREE.MeshStandardMaterial({
        color: color,
        roughness: e.roughness == null ? 0.8 : e.roughness,
        metalness: e.metalness == null ? 0.1 : e.metalness
      });
    }
    mat.userData.materialKey = key;
    cache[ck] = mat;
    return mat;
  }

  // Material used to tint an object by shadow severity (Phase 5 shadow mode).
  var SEVERITY_COLOR = {
    none: '#2e7d32', light: '#c9d400', moderate: '#f59e0b', heavy: '#e02020'
  };
  function severityColor(sev) { return SEVERITY_COLOR[sev] || '#2050a0'; }

  // Clear cache when the tier changes so subsequent builds pick new fidelity.
  function reset() { cache = {}; }

  DT.materials = { get: get, severityColor: severityColor, reset: reset,
                   SEVERITY_COLOR: SEVERITY_COLOR };
})();
