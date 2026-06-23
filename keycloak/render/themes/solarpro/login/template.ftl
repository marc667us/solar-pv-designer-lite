<#--
    template.ftl  --  SolarPro Keycloak chrome.

    Mirrors templates/base.html in the main app so the KC login page is
    visually indistinguishable from /login?legacy=1.

    Loads Bootstrap 5.3.3 + Bootstrap Icons 1.11.3 from the same CDN
    base.html uses; pulls our own login.css that re-declares the exact
    same :root variables and the two custom solar classes (`.solar-card`,
    `.btn-solar`).  All other styling comes from Bootstrap utilities.

    Sections supplied by the page template (login.ftl etc.) via <#nested>:
      "header"  -- short page heading used in <title>
      "form"    -- the FULL page content (row > col > solar-card > form)
      "info"    -- not rendered here; the legacy auth.html puts the
                   "New user?" footer link INSIDE the .solar-card
                   itself, so login.ftl owns that markup.
-->
<#macro registrationLayout displayInfo=false
                           displayMessage=true
                           displayRequiredFields=false
                           showAnotherWayIfPresent=true
                           bodyClass=""
                           showAuthMessages=true
                           displayWide=false>
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title><#nested "header"> &mdash; SolarPro Global</title>

  <#-- Same Bootstrap + Icons CDN that templates/base.html loads -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet"/>

  <#-- Solar palette + .solar-card / .btn-solar / navbar / footer overrides -->
  <link rel="stylesheet" href="${url.resourcesPath}/css/login.css"/>

  <link rel="icon" href="${url.resourcesPath}/img/solarpro-logo.svg" type="image/svg+xml"/>
</head>
<body>

<#-- =============================================================== -->
<#--  Beta channel banner -- copied verbatim from base.html           -->
<#-- =============================================================== -->
<div class="sp-beta-banner" role="status" aria-live="polite">
  <span class="sp-beta-pill">BETA 0.9.0</span>
  <span class="sp-beta-msg">
    Public beta &mdash; your data may be reset on each deployment.
    Please keep an external copy of any project you can&rsquo;t afford to lose.
  </span>
  <a class="sp-beta-link" href="https://solarpro.aiappinvent.com/rate">Rate&nbsp;the&nbsp;app&nbsp;&rarr;</a>
  <a class="sp-beta-link"
     href="https://github.com/marc667us/solar-pv-designer-lite/releases/tag/v0.9.0-beta.1"
     target="_blank" rel="noopener">Release&nbsp;notes&nbsp;&rarr;</a>
</div>

<#-- =============================================================== -->
<#--  Navbar (guest)  --  same gradient + brand mark as base.html.    -->
<#--  We are on auth.aiappinvent.com so all links are absolute URLs   -->
<#--  back to the solar app.                                           -->
<#-- =============================================================== -->
<nav class="navbar navbar-expand-lg navbar-dark">
  <div class="container-xl">

    <a class="navbar-brand" href="https://solarpro.aiappinvent.com/" style="padding:4px 0">
      <img src="${url.resourcesPath}/img/solarpro-logo.svg"
           alt="SolarPro Global" height="34" style="vertical-align:middle">
    </a>

    <button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#nav">
      <span class="navbar-toggler-icon"></span>
    </button>

    <div class="collapse navbar-collapse" id="nav">

      <ul class="navbar-nav me-auto align-items-center gap-1">
        <li class="nav-item">
          <a class="nav-link" href="https://solarpro.aiappinvent.com/marketplace">
            <i class="bi bi-bag-check-fill me-1 text-warning"></i>Marketplace
            <span class="badge ms-1" style="background:rgba(34,197,94,.18);color:#22c55e;font-size:9px;font-weight:700">FREE</span>
          </a>
        </li>
      </ul>

      <ul class="navbar-nav ms-auto align-items-center gap-1">
        <li class="nav-item">
          <a class="nav-link" href="https://solarpro.aiappinvent.com/">
            <i class="bi bi-house me-1"></i>Home
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="https://solarpro.aiappinvent.com/assess">
            <i class="bi bi-sun me-1 text-warning"></i>Free Assessment
          </a>
        </li>
        <li class="nav-item">
          <a class="nav-link" href="https://solarpro.aiappinvent.com/installer/register">
            <i class="bi bi-tools me-1" style="color:#fb923c"></i>Join as Installer
          </a>
        </li>
        <li class="nav-item ms-1">
          <a class="btn btn-outline-secondary btn-sm active" href="#" aria-current="page">
            <i class="bi bi-box-arrow-in-right me-1"></i>Login
          </a>
        </li>
        <li class="nav-item ms-1">
          <a class="btn btn-solar btn-sm" href="https://solarpro.aiappinvent.com/register">
            <i class="bi bi-rocket-takeoff me-1"></i>Get Started Free
          </a>
        </li>
      </ul>

    </div>
  </div>
</nav>

<#-- =============================================================== -->
<#--  Page content -- the form card is delivered by login.ftl        -->
<#-- =============================================================== -->
<main class="container-xl py-4">
  <#nested "form">
</main>

<#-- =============================================================== -->
<#--  Footer -- compact version of base.html's footer-bar            -->
<#-- =============================================================== -->
<footer class="footer-bar">
  <div class="container-xl">
    <div class="row g-3 align-items-start mb-3">
      <div class="col-md-4">
        <div class="mb-1">
          <img src="${url.resourcesPath}/img/solarpro-logo.svg"
               alt="SolarPro Global" height="36" style="vertical-align:middle">
        </div>
        <div class="small" style="color:#4a4a7a;line-height:1.6">
          Intelligent PV Solar System Design Platform.<br>
          BS 7671 &middot; IEC 60364 &middot; NEC &middot; IEEE
        </div>
      </div>
      <div class="col-md-4">
        <div class="small fw-bold mb-2" style="color:#5a5a90;text-transform:uppercase;letter-spacing:.5px">Platform</div>
        <div class="d-flex flex-column gap-1">
          <a class="footer-link" href="https://solarpro.aiappinvent.com/register">Start Free Trial</a>
          <a class="footer-link" href="https://solarpro.aiappinvent.com/login">Login</a>
          <a class="footer-link" href="https://solarpro.aiappinvent.com/upgrade">Pricing</a>
        </div>
      </div>
      <div class="col-md-4">
        <div class="small fw-bold mb-2" style="color:#5a5a90;text-transform:uppercase;letter-spacing:.5px">Standards</div>
        <div class="d-flex flex-wrap gap-2">
          <span class="badge border" style="font-size:9px;background:rgba(245,158,11,.06);color:#6868a0;border-color:#1e1e3a!important">BS 7671</span>
          <span class="badge border" style="font-size:9px;background:rgba(245,158,11,.06);color:#6868a0;border-color:#1e1e3a!important">IEC 60364</span>
          <span class="badge border" style="font-size:9px;background:rgba(245,158,11,.06);color:#6868a0;border-color:#1e1e3a!important">NEC 2023</span>
          <span class="badge border" style="font-size:9px;background:rgba(245,158,11,.06);color:#6868a0;border-color:#1e1e3a!important">IEEE 1547</span>
          <span class="badge border" style="font-size:9px;background:rgba(245,158,11,.06);color:#6868a0;border-color:#1e1e3a!important">MCS</span>
          <span class="badge border" style="font-size:9px;background:rgba(245,158,11,.06);color:#6868a0;border-color:#1e1e3a!important">IEC 62446</span>
        </div>
        <div class="mt-3 small" style="color:#3a3a6a">
          &copy; 2026 <strong style="color:#5a5a90">Global Engineering and Technology Services</strong> &nbsp;&middot;&nbsp; v2.0
        </div>
      </div>
    </div>
    <div class="text-center" style="border-top:1px solid #1e1e3a;padding-top:12px;color:#3a3a6a;font-size:11px">
      Intelligent Global PV Solar System Design Platform &nbsp;&middot;&nbsp; 22 countries &nbsp;&middot;&nbsp;
      &copy; 2026 Global Engineering and Technology Services. All rights reserved.
      <span style="color:#2a2a4a">&nbsp;|&nbsp;</span>
      <a href="https://solarpro.aiappinvent.com/terms" style="color:#4a4a7a;text-decoration:none">Terms</a>
      &nbsp;&middot;&nbsp;
      <a href="https://solarpro.aiappinvent.com/privacy" style="color:#4a4a7a;text-decoration:none">Privacy</a>
      &nbsp;&middot;&nbsp;
      <a href="https://solarpro.aiappinvent.com/data-protection" style="color:#4a4a7a;text-decoration:none">Data Protection</a>
    </div>
  </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
</#macro>
