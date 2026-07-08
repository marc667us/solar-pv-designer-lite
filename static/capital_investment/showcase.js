/* Photoreal Showcase — customer-facing scene switcher + present mode.
 * Self-contained, no Three.js dependency. Reads scene data from data-* attrs on
 * the thumbnail buttons (no inline JS data needed → CSP-safe).
 *
 * Behaviour:
 *   - click a scene thumbnail  -> swaps the hero image + caption + active state,
 *     hides the aerial-only callout chips on non-aerial scenes.
 *   - "Present" button         -> fullscreen the stage; Esc exits.
 *   - "Play" button            -> auto-advance the scenes every 4.5 s (toggle).
 * Everything degrades gracefully if an element is missing.
 */
(function () {
  "use strict";

  function init() {
    var stage = document.getElementById("sc-stage");
    var heroImg = document.getElementById("sc-hero-img");
    var caption = document.getElementById("sc-caption");
    var chips = document.getElementById("sc-callouts");
    var thumbs = Array.prototype.slice.call(
      document.querySelectorAll(".sc-thumb")
    );
    if (!stage || !heroImg || !thumbs.length) return;

    var idx = 0;

    function show(i) {
      if (i < 0 || i >= thumbs.length) return;
      idx = i;
      var t = thumbs[i];
      var full = t.getAttribute("data-full");
      if (full) {
        // fade swap
        heroImg.style.opacity = "0";
        var pre = new Image();
        pre.onload = function () {
          heroImg.src = full;
          heroImg.style.opacity = "1";
        };
        pre.src = full;
      }
      if (caption) caption.textContent = t.getAttribute("data-caption") || "";
      // callouts are positioned for the aerial only — show on aerial scene only
      if (chips) chips.style.display = t.getAttribute("data-key") === "aerial" ? "" : "none";
      thumbs.forEach(function (el) { el.classList.remove("active"); });
      t.classList.add("active");
    }

    thumbs.forEach(function (t, i) {
      t.addEventListener("click", function () {
        stopAuto();
        show(i);
      });
    });

    // Present (fullscreen) --------------------------------------------------
    var presentBtn = document.getElementById("sc-present");
    if (presentBtn) {
      presentBtn.addEventListener("click", function () {
        var el = stage;
        if (document.fullscreenElement) {
          if (document.exitFullscreen) document.exitFullscreen();
        } else if (el.requestFullscreen) {
          el.requestFullscreen();
        } else if (el.webkitRequestFullscreen) {
          el.webkitRequestFullscreen();
        }
      });
    }

    // Auto-advance slideshow ------------------------------------------------
    var timer = null;
    var playBtn = document.getElementById("sc-play");
    function stopAuto() {
      if (timer) { clearInterval(timer); timer = null; }
      if (playBtn) playBtn.classList.remove("active");
    }
    function startAuto() {
      stopAuto();
      timer = setInterval(function () {
        show((idx + 1) % thumbs.length);
      }, 4500);
      if (playBtn) playBtn.classList.add("active");
    }
    if (playBtn) {
      playBtn.addEventListener("click", function () {
        if (timer) stopAuto(); else startAuto();
      });
    }

    show(0);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
