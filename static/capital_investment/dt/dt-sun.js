/* dt-sun.js -- real sun light + sun-path arc from the server (Phase 4).
 *
 * The sun is a directional light driven by dt_scene_v2.sun_position (served at
 * DT_SUN_URL). Azimuth convention 0=N,90=E,180=S,270=W is mapped to Three.js
 * (+X=E, +Z=S). Also draws the sun-path arc for the active month and updates
 * the HUD + right-panel Sun-Path card (altitude/azimuth/sunrise/sunset).
 */
(function () {
  'use strict';
  var DT = window.DT = window.DT || {};
  var arc = null;
  var _polarSamples = [];   // daytime arc samples for the right-panel compass

  // ---- polar sun-path compass (right panel, matches mockup) ----------------
  // Stereographic-style plot: zenith at centre, horizon at the rim. Azimuth is
  // measured clockwise from North (up); altitude sets the radius. Drawn as an
  // SVG string so there is no extra dependency and it re-renders cheaply when
  // the time slider moves the current-sun marker.
  function polarPoint(cx, cy, R, alt, az) {
    var r = (90 - Math.max(alt, 0)) / 90 * R;   // 90deg alt -> centre, 0 -> rim
    var a = az * Math.PI / 180;
    return [cx + r * Math.sin(a), cy - r * Math.cos(a)];
  }
  function plabel(x, y, txt) {
    return '<text x="' + x + '" y="' + y + '" text-anchor="middle" ' +
      'fill="#94a3b8" font-size="9" font-weight="bold">' + txt + '</text>';
  }
  function renderPolar() {
    var host = document.getElementById('dt-sunpath-chart');
    if (!host) return;
    var W = 172, cx = W / 2, cy = W / 2, R = 66;
    var s = '<svg viewBox="0 0 ' + W + ' ' + W + '" style="width:100%;max-width:196px;height:auto">';
    s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + R + '" fill="#0b1220" stroke="#334155" stroke-width="1"/>';
    s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (R * 2 / 3).toFixed(1) + '" fill="none" stroke="#1c2a3d" stroke-width="1"/>';
    s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (R / 3).toFixed(1) + '" fill="none" stroke="#1c2a3d" stroke-width="1"/>';
    s += '<line x1="' + cx + '" y1="' + (cy - R) + '" x2="' + cx + '" y2="' + (cy + R) + '" stroke="#1c2a3d"/>';
    s += '<line x1="' + (cx - R) + '" y1="' + cy + '" x2="' + (cx + R) + '" y2="' + cy + '" stroke="#1c2a3d"/>';
    s += plabel(cx, cy - R - 3, 'N') + plabel(cx + R + 5, cy + 3, 'E') +
      plabel(cx, cy + R + 10, 'S') + plabel(cx - R - 5, cy + 3, 'W');
    var pts = [];
    _polarSamples.forEach(function (o) {
      if (!o.is_daylight) return;
      pts.push(polarPoint(cx, cy, R, o.altitude_deg, o.azimuth_deg));
    });
    if (pts.length > 1) {
      s += '<polyline points="' + pts.map(function (p) {
        return p[0].toFixed(1) + ',' + p[1].toFixed(1);
      }).join(' ') + '" fill="none" stroke="#ffd54a" stroke-width="1.6" stroke-dasharray="3 2"/>';
    }
    var cs = DT.state.sun;
    if (cs.isDaylight) {
      var sp = polarPoint(cx, cy, R, cs.altitudeDeg, cs.azimuthDeg);
      s += '<circle cx="' + sp[0].toFixed(1) + '" cy="' + sp[1].toFixed(1) +
        '" r="5" fill="#ffd54a" stroke="#fff" stroke-width="1"/>';
    }
    s += '</svg>';
    host.innerHTML = s;
  }

  // Convert a server sun dict into a Three.js light direction * distance.
  function sunVector(sun, dist) {
    var altR = (sun.altitude_deg || 0) * Math.PI / 180;
    var azR = (sun.azimuth_deg || 180) * Math.PI / 180;
    var horiz = Math.cos(altR) * dist;
    return [Math.sin(azR) * horiz, Math.max(Math.sin(altR) * dist, -dist * 0.05),
            Math.cos(azR) * horiz];
  }

  function applyLighting(sun) {
    var t = DT.three, THREE = window.THREE;
    if (!t.sunLight) return;
    var v = sunVector(sun, t.sunDistance);
    t.sunLight.position.set(v[0], v[1], v[2]);
    var day = !!sun.is_daylight;
    t.sunLight.intensity = day ? 1.6 : 0.04;
    if (t.ambientLight) t.ambientLight.intensity = day ? 0.32 : 0.12;
    if (t.scene) {
      // Keep the atmospheric gradient sky on daytime updates (the old code
      // flattened it to a single pale blue every tick, which washed the whole
      // scene into a "white board"). Only night swaps to a dark flat sky.
      if (day && t.skyTexture) t.scene.background = t.skyTexture;
      else t.scene.background = new THREE.Color(day ? 0x9ec6e6 : 0x05060f);
      if (t.scene.fog) t.scene.fog.color =
        new THREE.Color(day ? (t.horizonHex || 0xc4d8e6) : 0x05060f);
    }
  }

  function updateHud(sun) {
    var setTxt = function (id, txt) { var e = document.getElementById(id); if (e) e.textContent = txt; };
    setTxt('hud-sun-info', 'Sun - month ' + sun.month + ', ' + (+sun.hour).toFixed(2) + 'h  |  alt ' +
      (+sun.altitude_deg).toFixed(1) + 'deg, az ' + (+sun.azimuth_deg).toFixed(1) + 'deg');
    setTxt('tl-sun-summary', 'alt ' + (+sun.altitude_deg).toFixed(1) + 'deg, az ' +
      (+sun.azimuth_deg).toFixed(1) + 'deg' + (sun.is_daylight ? '' : ' (night)'));
    var panel = document.getElementById('dt-sunpath-body');
    if (panel) {
      panel.innerHTML =
        card('Altitude', (+sun.altitude_deg).toFixed(1) + ' deg') +
        card('Azimuth', (+sun.azimuth_deg).toFixed(1) + ' deg') +
        card('Sunrise', hhmm(sun.sunrise_hour)) +
        card('Sunset', hhmm(sun.sunset_hour)) +
        card('Solar noon', hhmm(sun.solar_noon_hour)) +
        card('Shadow factor', (+sun.shadow_length_factor).toFixed(2) + ' x');
    }
  }
  function card(k, v) {
    return '<div class="d-flex justify-content-between small py-1 border-bottom" ' +
      'style="border-color:#1e1e3a!important"><span class="text-secondary">' + k +
      '</span><span class="text-warning fw-bold">' + v + '</span></div>';
  }
  function hhmm(h) {
    if (h == null || isNaN(h)) return '--';
    var m = Math.round((h - Math.floor(h)) * 60);
    return ('0' + Math.floor(h)).slice(-2) + ':' + ('0' + m).slice(-2);
  }

  // Build/refresh the sun-path arc for the given month from AUTHORITATIVE
  // server samples (same solar model as the light + shadows) -- never a
  // hardcoded ellipse. Falls back to no arc if the endpoint is unavailable.
  function buildArc(month) {
    var t = DT.three, THREE = window.THREE;
    if (!window.DT_SUN_ARC_URL) return;
    DT.util.getJSON(window.DT_SUN_ARC_URL + '?month=' + month).then(function (data) {
      if (arc) { t.scene.remove(arc); if (arc.geometry) arc.geometry.dispose(); arc = null; }
      _polarSamples = data.samples || [];      // feed the right-panel compass
      renderPolar();
      var arr = [];
      (data.samples || []).forEach(function (s) {
        if (!s.is_daylight) return;                 // only the daytime span
        var v = sunVector({ altitude_deg: s.altitude_deg, azimuth_deg: s.azimuth_deg },
                          t.sunDistance * 0.92);
        arr.push(v[0], Math.max(v[1], 1), v[2]);
      });
      if (arr.length < 6) return;                   // sun never rises this month
      var geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
      arc = new THREE.Line(geom, new THREE.LineDashedMaterial(
        { color: 0xffd54a, dashSize: 6, gapSize: 4 }));
      if (arc.computeLineDistances) arc.computeLineDistances();
      t.scene.add(arc);
    }).catch(function () { /* no arc on transient error */ });
  }

  function sunUrl(month, hour) {
    return (window.DT_SUN_URL || '') + '?month=' + month + '&hour=' + hour;
  }

  // Fetch the authoritative sun position and apply it everywhere.
  function update(month, hour) {
    DT.state.sun.month = month; DT.state.sun.hour = hour;
    return DT.util.getJSON(sunUrl(month, hour)).then(function (sun) {
      DT.state.sun.altitudeDeg = sun.altitude_deg;
      DT.state.sun.azimuthDeg = sun.azimuth_deg;
      DT.state.sun.isDaylight = sun.is_daylight;
      applyLighting(sun);
      updateHud(sun);
      renderPolar();                 // move the current-sun marker on the compass
      DT.bus.emit('sun:changed', sun);
      return sun;
    }).catch(function () { /* keep last-known sun on transient error */ });
  }

  DT.sun = { update: update, buildArc: buildArc, sunVector: sunVector,
             renderPolar: renderPolar };
})();
