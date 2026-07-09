/* SolarPro Tutorial & Demo Engine -- shared service, one engine for every page.
 *
 * Spec: pvsolar1/"video tutorial.txt". A page never hard-codes its tutorial; it
 * ships a scenario definition at
 *     /static/tutorial/scenarios/<flask-endpoint>.json
 * and this engine plays it: animated cursor, click ripples, highlight cut-out,
 * step tooltip, captions, Web-Speech narration, transport controls, and an
 * optional MediaRecorder screen capture that EXPORTS the demo as a .webm video.
 * Recorded video is therefore an export of the engine, not separate collateral.
 *
 * Modes
 *   guided  -- user drives Next/Prev; narration + highlight per step
 *   auto    -- engine drives: cursor moves, ripples, types, scrolls, advances
 *   watch   -- auto, but strictly read-only (no real clicks dispatched at all)
 *   explain -- text/voice explanation of the page (AI Orchestrator, else static)
 *
 * SAFETY (spec "Tutorials must not click destructive actions on real data"):
 * a step's click is *simulated* (cursor + ripple) and only dispatched against
 * the real DOM when the scenario explicitly sets "dispatch": true AND the mode
 * is not "watch". Nothing else in the app is ever touched.
 *
 * Zero-cost: no libraries, no paid voice/video service, no server rendering.
 *
 * in : data-page attribute on this script tag (the Flask endpoint name)
 * out: window.SolarProTutorial = { start(mode), stop(), available }
 */
(function () {
  'use strict';

  // currentScript is set for classic deferred scripts, but fall back to a
  // lookup so the engine still finds its config if it is ever loaded async.
  var SELF = document.currentScript || document.querySelector('script[data-page]');
  var PAGE = (SELF && SELF.getAttribute('data-page')) || '';
  var BASE = (SELF && SELF.getAttribute('data-base')) || '/static/tutorial/scenarios/';
  if (!PAGE) return;

  var T = {
    scenario: null, i: 0, mode: 'guided', playing: false, muted: false, speed: 1,
    els: {}, timer: null, rec: null, chunks: [], stream: null, alive: false
  };

  // ---------- multi-screen flows ----------
  // A feature's tutorial spans every screen the feature touches, so a tour must
  // survive a page navigation. Before navigating we park {flow, i, mode} in
  // sessionStorage; on the next page the engine reloads the SAME scenario file
  // (the flow's entry endpoint) and resumes at the next step. Stale state is
  // ignored so a tour abandoned an hour ago never ambushes the user.
  var FLOW_KEY = 'spTutFlow';
  var FLOW_TTL_MS = 10 * 60 * 1000;

  function saveFlow(nextIndex) {
    try {
      sessionStorage.setItem(FLOW_KEY, JSON.stringify({
        flow: T.scenario.pageId, i: nextIndex, mode: T.mode, muted: T.muted,
        speed: T.speed, ts: Date.now()
      }));
    } catch (e) {}
  }
  function clearFlow() { try { sessionStorage.removeItem(FLOW_KEY); } catch (e) {} }
  function readFlow() {
    try {
      var s = JSON.parse(sessionStorage.getItem(FLOW_KEY) || 'null');
      if (!s || !s.flow || (Date.now() - (s.ts || 0)) > FLOW_TTL_MS) return null;
      return s;
    } catch (e) { return null; }
  }

  // ---------- tiny helpers ----------
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function sleep(ms) { return new Promise(function (r) { T.timer = setTimeout(r, Math.max(0, ms / T.speed)); }); }
  function q(sel) { try { return sel ? document.querySelector(sel) : null; } catch (e) { return null; } }
  function steps() { return (T.scenario && T.scenario.steps) || []; }
  function cur() { return steps()[T.i] || null; }

  // ---------- narration (Web Speech API; captions are the fallback) ----------
  function speak(text) {
    return new Promise(function (resolve) {
      if (T.muted || !text || !('speechSynthesis' in window)) return resolve();
      try {
        window.speechSynthesis.cancel();
        var u = new SpeechSynthesisUtterance(text);
        u.lang = (T.scenario && T.scenario.language) || 'en-US';
        u.rate = Math.min(2, Math.max(.5, T.speed));
        u.onend = u.onerror = function () { resolve(); };
        window.speechSynthesis.speak(u);
        // Chrome sometimes never fires onend; cap the wait.
        setTimeout(resolve, Math.min(14000, 380 * String(text).split(/\s+/).length));
      } catch (e) { resolve(); }
    });
  }
  function hushSpeech() { try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (e) {} }

  // ---------- chrome ----------
  function buildChrome() {
    if (T.els.bar) return;
    var ring = el('div', 'sp-tut-ring');
    ring.style.cssText = 'top:-9999px;left:-9999px;width:0;height:0';
    var cursor = el('div', 'sp-tut-cursor');
    cursor.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24">' +
      '<path d="M3 2l7.5 18 2.2-7.3L20 10.5 3 2z" fill="#fff" stroke="#111" stroke-width="1"/></svg>';
    cursor.style.cssText = 'top:50%;left:50%';
    var tip = el('div', 'sp-tut-tip');
    var bar = el('div', 'sp-tut-bar',
      '<div class="sp-tut-cap"></div>' +
      '<div class="sp-tut-ctl">' +
        '<button data-a="prev">&#9664; Prev</button>' +
        '<button data-a="toggle" class="primary">Pause</button>' +
        '<button data-a="next">Next &#9654;</button>' +
        '<button data-a="restart">Restart</button>' +
        '<span class="grow"></span>' +
        '<select data-a="speed" title="Playback speed">' +
          '<option value="0.75">0.75x</option><option value="1" selected>1x</option>' +
          '<option value="1.5">1.5x</option><option value="2">2x</option></select>' +
        '<button data-a="mute">Mute</button>' +
        '<button data-a="record" class="rec">Record</button>' +
        '<button data-a="stop">Exit</button>' +
      '</div>');
    [ring, cursor, tip, bar].forEach(function (n) { document.body.appendChild(n); });
    T.els = { ring: ring, cursor: cursor, tip: tip, bar: bar,
              cap: bar.querySelector('.sp-tut-cap') };
    bar.addEventListener('click', onCtl);
    bar.querySelector('[data-a=speed]').addEventListener('change', function (e) {
      T.speed = parseFloat(e.target.value) || 1;
    });
  }
  function destroyChrome() {
    ['ring', 'cursor', 'tip', 'bar'].forEach(function (k) {
      if (T.els[k] && T.els[k].parentNode) T.els[k].parentNode.removeChild(T.els[k]);
    });
    T.els = {};
  }
  function toast(msg) {
    var t = el('div', 'sp-tut-toast', esc(msg));
    document.body.appendChild(t);
    setTimeout(function () { t.parentNode && t.parentNode.removeChild(t); }, 2600);
  }

  // ---------- highlight + cursor motion ----------
  function ringTo(node) {
    var r = T.els.ring;
    if (!node) { r.style.cssText = 'top:-9999px;left:-9999px;width:0;height:0'; return; }
    var b = node.getBoundingClientRect();
    r.style.top = (b.top - 6) + 'px';
    r.style.left = (b.left - 6) + 'px';
    r.style.width = (b.width + 12) + 'px';
    r.style.height = (b.height + 12) + 'px';
    r.classList.add('pulse');
  }
  function easeInOut(t) { return t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }
  // Glide the cursor from where it is to (x,y) with acceleration/deceleration.
  function moveCursor(x, y, ms) {
    return new Promise(function (resolve) {
      var c = T.els.cursor;
      var sx = parseFloat(c.style.left) || window.innerWidth / 2;
      var sy = parseFloat(c.style.top) || window.innerHeight / 2;
      var dur = Math.max(120, (ms || 700) / T.speed), t0 = performance.now();
      (function frame(now) {
        if (!T.alive) return resolve();
        var p = Math.min(1, (now - t0) / dur), e = easeInOut(p);
        c.style.left = (sx + (x - sx) * e) + 'px';
        c.style.top = (sy + (y - sy) * e) + 'px';
        p < 1 ? requestAnimationFrame(frame) : resolve();
      })(t0);
    });
  }
  function centerOf(node) {
    var b = node.getBoundingClientRect();
    return { x: b.left + b.width / 2, y: b.top + b.height / 2 };
  }
  function ripple(x, y) {
    var r = el('div', 'sp-tut-ripple');
    r.style.left = x + 'px'; r.style.top = y + 'px';
    document.body.appendChild(r);
    T.els.cursor.classList.add('down');
    setTimeout(function () { T.els.cursor.classList.remove('down'); }, 140);
    setTimeout(function () { r.parentNode && r.parentNode.removeChild(r); }, 600);
  }

  // ---------- tooltip ----------
  function placeTip(step, node) {
    var tip = T.els.tip, n = steps().length;
    tip.innerHTML =
      '<h6>' + esc(step.title || 'Step') + '</h6>' +
      '<div>' + esc(step.description || '') + '</div>' +
      '<div class="sp-tut-prog">Step ' + (T.i + 1) + ' of ' + n +
        (T.scenario.title ? ' &middot; ' + esc(T.scenario.title) : '') + '</div>' +
      (T.mode === 'guided'
        ? '<div class="sp-tut-nav">' +
            '<button data-a="prev">Back</button>' +
            '<button data-a="next" class="primary">' + (T.i === n - 1 ? 'Finish' : 'Next') + '</button>' +
            '<button data-a="stop">Skip tour</button></div>'
        : '');
    tip.querySelectorAll('[data-a]').forEach(function (b) { b.onclick = onCtl; });

    var tb = tip.getBoundingClientRect();
    var top, left;
    if (node) {
      var b = node.getBoundingClientRect();
      var below = b.bottom + 14 + tb.height < window.innerHeight;
      top = below ? b.bottom + 14 : Math.max(12, b.top - tb.height - 14);
      left = Math.min(Math.max(12, b.left), window.innerWidth - tb.width - 12);
    } else {
      top = 96; left = Math.max(12, window.innerWidth / 2 - tb.width / 2);
    }
    // never sit under the caption bar
    top = Math.min(top, window.innerHeight - tb.height - 120);
    tip.style.top = Math.max(12, top) + 'px';
    tip.style.left = left + 'px';
  }
  function caption(text) { if (T.els.cap) T.els.cap.textContent = text || ''; }

  // ---------- actions ----------
  // Perform one scenario step. Returns a promise resolving when the step is done.
  async function runStep() {
    var s = cur();
    if (!s) return finish();
    markFlow();                       // survive a navigation from any step
    var node = q(s.targetSelector);

    if (!node && s.targetSelector) {
      // Missing target must degrade, never abort (spec: handle missing target).
      caption(s.fallbackMessage || ('Skipping: "' + (s.title || 'step') + '" is not on this page.'));
      ringTo(null); placeTip(s, null);
      await sleep(900);
      return;
    }

    if (node && typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ behavior: 'smooth', block: 'center' });
      await sleep(320);
    }
    ringTo(node);
    placeTip(s, node);
    caption(s.captionText || s.voiceScript || s.description || '');

    if (s.delayBefore) await sleep(s.delayBefore);

    // Every step that has a target shows the cursor travelling to it -- including
    // a navigate step, so the user sees WHICH control opens the next screen.
    var act = s.action || 'highlightOnly';
    if (node && act !== 'highlightOnly' && act !== 'scroll') {
      var c = centerOf(node);
      await moveCursor(c.x, c.y, 620);
    }

    if (act === 'click' || act === 'doubleClick') {
      var p = centerOf(node); ripple(p.x, p.y);
      if (act === 'doubleClick') { await sleep(160); ripple(p.x, p.y); }
      // Only ever touch real controls when the scenario opts in AND we're not
      // in read-only watch mode.
      if (s.dispatch === true && T.mode !== 'watch') { try { node.click(); } catch (e) {} }
      await sleep(260);
    } else if (act === 'typeText') {
      // watch mode is strictly read-only: never write into a real field, even
      // if the scenario opted in with dispatch:true.
      await typeInto(node, s.typeText || '', s.dispatch === true && T.mode !== 'watch');
    } else if (act === 'drag' || act === 'rotate3D' || act === 'pan' || act === 'zoom') {
      await gesture(node, act);
    } else if (act === 'scroll') {
      window.scrollBy({ top: s.scrollBy || 320, behavior: 'smooth' });
      await sleep(500);
    } else if (act === 'navigate') {
      // Cross-screen hop. The destination is either a literal href or resolved
      // from a link on this page (project-scoped URLs carry an id we cannot know
      // when the scenario is authored). Navigation is a GET, so it is safe in
      // every mode -- showing the next screen IS the point of the tutorial.
      var href = s.href || '';
      if (!href && s.hrefFromSelector) {
        var link = q(s.hrefFromSelector);
        href = (link && link.getAttribute('href')) || '';
      }
      if (!href) {
        caption(s.fallbackMessage || 'The next screen is not reachable from here.');
        await sleep(1100);
        return;
      }
      if (node) { var np = centerOf(node); ripple(np.x, np.y); }
      await speak(s.voiceScript || s.captionText || '');
      await sleep(280);
      saveFlow(T.i + 1);          // resume on the next screen
      location.href = href;
      return 'navigated';         // stop the loop; the new page picks the tour up
    }

    await speak(s.voiceScript || s.captionText || '');
    await sleep(s.duration || 500);
    if (s.delayAfter) await sleep(s.delayAfter);
  }

  // Show a drag / orbit / pan / zoom gesture as cursor motion across the target.
  // Purely visual: the engine never synthesises pointer events on the app, so a
  // demo can rehearse a 3D orbit or a slider drag without mutating anything.
  // in : node (Element), kind (string)   out: promise
  async function gesture(node, kind) {
    if (!node) return;
    var b = node.getBoundingClientRect();
    var cy = b.top + b.height / 2;
    var pts = kind === 'zoom'
      ? [[b.left + b.width * .5, cy], [b.left + b.width * .5, cy - b.height * .18],
         [b.left + b.width * .5, cy + b.height * .18]]
      : [[b.left + b.width * .30, cy], [b.left + b.width * .50, cy - b.height * .12],
         [b.left + b.width * .72, cy]];
    T.els.cursor.classList.add('down');
    for (var i = 0; i < pts.length; i++) await moveCursor(pts[i][0], pts[i][1], 420);
    T.els.cursor.classList.remove('down');
    await sleep(180);
  }

  // Animate character-by-character typing. Only writes into the real input when
  // dispatch=true; otherwise it types into the caption so nothing is mutated.
  async function typeInto(node, text, dispatch) {
    var isField = node && ('value' in node);
    if (!isField || !dispatch) {
      for (var i = 1; i <= text.length; i++) { caption('Typing: ' + text.slice(0, i)); await sleep(38); }
      return;
    }
    node.focus(); node.value = '';
    for (var j = 0; j < text.length; j++) {
      node.value += text[j];
      node.dispatchEvent(new Event('input', { bubbles: true }));
      await sleep(42);
    }
    node.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // ---------- transport ----------
  async function loop() {
    while (T.alive && T.playing && T.i < steps().length) {
      var r = await runStep();
      if (r === 'navigated') return;    // the next screen resumes the tour
      if (!T.alive || !T.playing) return;
      T.i++;
    }
    if (T.alive && T.i >= steps().length) finish();
  }
  function finish() {
    caption('Tutorial complete.');
    ringTo(null);
    clearFlow();
    T.playing = false;
    setTimeout(stop, 1400);
  }
  function onCtl(ev) {
    var a = (ev.target.closest && ev.target.closest('[data-a]'));
    if (!a) return;
    var k = a.getAttribute('data-a');
    if (k === 'stop') return stop();
    // On the last step "Next" reads "Finish" -- it must end the tour, not replay
    // the final step forever.
    if (k === 'next') {
      hushSpeech(); clearTimeout(T.timer);
      if (T.i >= steps().length - 1) return finish();
      T.i += 1; return step0();
    }
    if (k === 'prev') { hushSpeech(); clearTimeout(T.timer); T.i = Math.max(0, T.i - 1); return step0(); }
    if (k === 'restart') { hushSpeech(); clearTimeout(T.timer); T.i = 0; return step0(); }
    if (k === 'mute') { T.muted = !T.muted; a.textContent = T.muted ? 'Unmute' : 'Mute'; if (T.muted) hushSpeech(); return; }
    if (k === 'record') return toggleRecord(a);
    if (k === 'toggle') {
      T.playing = !T.playing;
      a.textContent = T.playing ? 'Pause' : 'Play';
      if (T.playing) loop(); else { hushSpeech(); clearTimeout(T.timer); }
    }
  }
  // Render the current step once (guided mode / manual navigation).
  async function step0() {
    if (T.mode === 'guided') { await runStep(); return; }
    if (T.playing) return;                    // auto loop already running
    await runStep();
  }
  // In guided mode the user drives, so the flow index must be parked on every
  // step -- otherwise a navigate step would resume at the wrong place.
  function markFlow() { if (T.alive && T.scenario) saveFlow(T.i); }

  // ---------- recording: MediaRecorder screen capture -> .webm export ----------
  async function toggleRecord(btn) {
    if (T.rec) {
      T.rec.stop();
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia || !window.MediaRecorder) {
      return toast('Recording is not supported in this browser.');
    }
    try {
      toast('Your screen may show project data — pick this tab only.');
      T.stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 30 }, audio: false });
      T.chunks = [];
      T.rec = new MediaRecorder(T.stream, { mimeType: 'video/webm' });
      T.rec.ondataavailable = function (e) { if (e.data && e.data.size) T.chunks.push(e.data); };
      T.rec.onstop = function () {
        var blob = new Blob(T.chunks, { type: 'video/webm' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'solarpro-' + PAGE + '-tutorial.webm';
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
        (T.stream.getTracks() || []).forEach(function (t) { t.stop(); });
        T.rec = null; T.stream = null;
        btn.classList.remove('on'); btn.textContent = 'Record';
        toast('Video exported (.webm).');
      };
      T.rec.start();
      btn.classList.add('on'); btn.textContent = 'Stop rec';
    } catch (e) { toast('Recording cancelled.'); }
  }

  // ---------- AI explain ----------
  async function explain() {
    var sc = T.scenario;
    var fallback = (sc.description || '') + '\n\n' +
      steps().map(function (s, i) { return (i + 1) + '. ' + (s.title || '') + ' — ' + (s.description || ''); }).join('\n');
    buildChrome();
    T.alive = true;
    caption('Asking the assistant about this page…');
    var text = fallback;
    try {
      var tok = (document.querySelector('meta[name=csrf-token]') || {}).content ||
                (document.querySelector('input[name=_csrf]') || {}).value || '';
      var r = await fetch('/api/assistant/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': tok },
        body: JSON.stringify({ message: 'Explain the "' + (sc.title || PAGE) +
          '" page of SolarPro: what it does, its main buttons, the recommended workflow, ' +
          'common mistakes, and the next step. Be concise.' })
      });
      if (r.ok) { var j = await r.json(); if (j && (j.reply || j.message)) text = j.reply || j.message; }
    } catch (e) { /* offline / rate-limited -> static help text */ }
    T.els.tip.innerHTML = '<h6>' + esc(sc.title || 'This page') + '</h6><div>' +
      esc(text).replace(/\n/g, '<br>') + '</div>' +
      '<div class="sp-tut-nav"><button data-a="stop" class="primary">Close</button></div>';
    T.els.tip.querySelectorAll('[data-a]').forEach(function (b) { b.onclick = onCtl; });
    T.els.tip.style.top = '96px';
    T.els.tip.style.left = Math.max(12, window.innerWidth / 2 - 165) + 'px';
    caption('');
    speak(text.slice(0, 600));
  }

  // ---------- lifecycle ----------
  function start(mode) {
    if (!T.scenario) return;
    closeMenu();
    T.mode = mode || 'guided';
    T.i = 0; T.alive = true;
    if (T.mode === 'explain') return explain();
    clearFlow();
    begin();
  }
  // Pick the tour back up on a new screen at the step the previous screen parked.
  function resume(index, mode) {
    if (!T.scenario) return;
    T.mode = mode || 'auto';
    T.i = Math.max(0, Math.min(steps().length - 1, index));
    T.alive = true;
    begin();
  }
  function begin() {
    buildChrome();
    T.playing = (T.mode !== 'guided');
    var tgl = T.els.bar.querySelector('[data-a=toggle]');
    tgl.textContent = T.playing ? 'Pause' : 'Play';
    markFlow();
    if (T.playing) loop(); else runStep();
  }
  function stop() {
    T.alive = false; T.playing = false;
    clearFlow();                       // an exited tour must not resume elsewhere
    hushSpeech(); clearTimeout(T.timer);
    if (T.rec) { try { T.rec.stop(); } catch (e) {} }
    destroyChrome();
  }

  // ---------- launcher ----------
  var menu = null;
  function closeMenu() { if (menu && menu.parentNode) menu.parentNode.removeChild(menu); menu = null; }
  function openMenu() {
    if (menu) return closeMenu();
    menu = el('div', 'sp-tut-menu',
      '<button data-m="guided">&#9654;&nbsp; Start Guided Tour</button>' +
      '<button data-m="auto">&#9673;&nbsp; Auto Demo</button>' +
      '<button data-m="watch">&#128065;&nbsp; Watch Demo (read-only)</button>' +
      '<button data-m="explain">&#10024;&nbsp; AI Explain This Page</button>');
    menu.addEventListener('click', function (e) {
      var b = e.target.closest('[data-m]');
      if (b) start(b.getAttribute('data-m'));
    });
    document.body.appendChild(menu);
  }
  function mountLauncher() {
    var b = el('div', 'sp-tut-launcher no-print',
      '<span aria-hidden="true">&#63;</span><span>Help &amp; Tutorial</span>');
    b.setAttribute('role', 'button');
    b.setAttribute('title', 'Guided tour, auto demo, AI explain');
    b.addEventListener('click', openMenu);
    document.body.appendChild(b);
  }

  // Boot. If a multi-screen tour is mid-flight we reload ITS scenario (the flow's
  // entry endpoint) and resume; otherwise we load this page's own scenario. Pages
  // with neither never see the engine.
  var flow = readFlow();
  var wanted = flow ? flow.flow : PAGE;

  fetch(BASE + encodeURIComponent(wanted) + '.json', { credentials: 'same-origin' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) {
      if (!j || !j.steps || !j.steps.length) {
        if (flow) clearFlow();          // flow file vanished (route renamed)
        return;
      }
      // A draft is machine-generated from the page's controls and still carries
      // TODO narration. It exists so coverage is visible, not so users see it.
      if (j.draft === true) { if (flow) clearFlow(); return; }
      T.scenario = j;
      mountLauncher();
      window.SolarProTutorial = { start: start, stop: stop, available: true, scenario: j };

      if (flow) {
        if (flow.i >= j.steps.length) { clearFlow(); return; }
        T.muted = !!flow.muted;
        T.speed = flow.speed || 1;
        // Give the destination page a beat to paint before we hunt for targets.
        setTimeout(function () { resume(flow.i, flow.mode); }, 900);
        return;
      }
      // ?tutorial=guided|auto|watch|explain deep-links a tour (used by /guides).
      var m = new URLSearchParams(location.search).get('tutorial');
      if (m) setTimeout(function () { start(m); }, 700);
    })
    .catch(function () { if (flow) clearFlow(); });

  window.addEventListener('resize', function () { if (T.alive) { var s = cur(); ringTo(q(s && s.targetSelector)); } });
  window.addEventListener('keydown', function (e) { if (e.key === 'Escape' && T.alive) stop(); });
})();
