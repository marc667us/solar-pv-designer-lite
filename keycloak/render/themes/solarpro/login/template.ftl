<#--
    template.ftl -- SolarPro chrome around every KC login screen.

    Mirrors templates/auth.html (the legacy SolarPro login template).
    The card uses Bootstrap 5.3.3 utility classes + the .solar-card /
    .btn-solar custom classes from templates/base.html, so the rendered
    KC page is visually identical to /login?legacy=1.

    Structure preserved from the last-known-good 3658ecc version:
      <#nested "header">      page heading
      <#nested "form">        login form
      <#if displayInfo>       "New user?" footer cluster
        <#nested "info">

    Only the HTML class names + chrome have changed -- the FreeMarker
    spine is identical to the working baseline.
-->
<#macro registrationLayout displayInfo=false displayMessage=true displayRequiredFields=false showAnotherWayIfPresent=true bodyClass="" showAuthMessages=true displayWide=false>
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title><#nested "header"> &mdash; SolarPro Global</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet"/>
  <link rel="icon" href="${url.resourcesPath}/img/solarpro-logo.svg" type="image/svg+xml"/>
  <link rel="stylesheet" href="${url.resourcesPath}/css/login.css"/>
</head>
<body class="sp-page">
  <main class="sp-page__container container-xl py-4">

    <#-- 3-column layout at lg+: marketing pitch | login card | marketing pitch
         At md (768-991px) the side pitches are hidden and the login card
         sits centered. At sm (<768px) everything stacks. -->
    <div class="row align-items-start justify-content-center gx-4 gy-3">

      <#-- LEFT pitch -- visible at lg+ only -->
      <aside class="col-lg-3 d-none d-lg-block mt-4">
        <div class="solar-card p-3">
          <div class="d-flex align-items-center mb-2">
            <i class="bi bi-lightning-charge-fill text-warning me-2" style="font-size:20px"></i>
            <h6 class="fw-bold mb-0">Engineer-grade PV design</h6>
          </div>
          <ul class="small text-secondary mb-0 ps-3" style="line-height:1.7">
            <li>22-country irradiance + tariff database</li>
            <li>Loads &rarr; PV &rarr; battery &rarr; inverter &rarr; cable &rarr; BOQ in one wizard</li>
            <li>BS 7671 / IEC 60364 / NEC compliance baked in</li>
            <li>3D shading + sun-path simulation</li>
            <li>Branded proposal PDFs ready to send</li>
          </ul>
        </div>
      </aside>

      <#-- CENTER login card -- legacy auth.html structure preserved -->
      <div class="col-md-7 col-lg-5">
        <div class="solar-card p-4 mt-4">

          <div class="text-center mb-4">
            <div style="font-size:36px">&#9728;&#65039;</div>
            <h4 class="fw-bold mt-2"><#nested "header"></h4>
            <p class="text-secondary small">Sign in to your account.</p>
          </div>

          <#-- Realm-level message banner (locked / disabled / info).
               Class is alert-${message.type}; an `alert-error` alias is
               defined in login.css so the legacy KC "error" type maps to
               Bootstrap red. Same one-line shape as the working 3658ecc
               template -- no ternary, no <#assign>. -->
          <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
            <div class="alert alert-${message.type} small py-2 px-3 mb-3" role="alert">
              ${kcSanitize(message.summary)?no_esc}
            </div>
          </#if>

          <#-- The form goes here -->
          <#nested "form">

          <#-- "New user? Create account" cluster (legacy: text-center mt-3 small text-secondary) -->
          <#if displayInfo>
            <div class="text-center mt-3 small text-secondary">
              <#nested "info">
            </div>
          </#if>

        </div>
      </div>

      <#-- RIGHT pitch -- visible at lg+ only -->
      <aside class="col-lg-3 d-none d-lg-block mt-4">
        <div class="solar-card p-3">
          <div class="d-flex align-items-center mb-2">
            <i class="bi bi-bag-check-fill text-warning me-2" style="font-size:20px"></i>
            <h6 class="fw-bold mb-0">Marketplace + procurement</h6>
          </div>
          <ul class="small text-secondary mb-0 ps-3" style="line-height:1.7">
            <li>437+ products across 21 categories</li>
            <li>140 brand suppliers &mdash; Ghana, UK, and global</li>
            <li>RFQ workflow with auto-supplier matching</li>
            <li>Multi-currency BOMs (USD / GHS / NGN / KES / GBP)</li>
            <li>Free to browse &mdash; sign in to send RFQs</li>
          </ul>
        </div>
      </aside>

    </div>

    <#-- Privacy + Data Protection summary -- two cards side by side
         below the login card on md+, stacked on sm. Mirrors the summary
         that lives on the solar app's /data-protection page. -->
    <div class="row justify-content-center mt-3 gx-3">
      <div class="col-md-10 col-lg-8">
        <div class="row g-3">

          <div class="col-md-6">
            <div class="solar-card p-3 h-100">
              <div class="d-flex align-items-center mb-2">
                <span style="font-size:18px" class="me-2">&#128274;</span>
                <h6 class="fw-bold mb-0 text-warning small text-uppercase" style="letter-spacing:.5px">Privacy at a glance</h6>
              </div>
              <ul class="small text-secondary mb-0 ps-3" style="line-height:1.7">
                <li>We collect only what we need to run your account.</li>
                <li>No payment card data is ever stored on our servers.</li>
                <li>We never sell or rent your data.</li>
                <li>You can export or delete your account at any time.</li>
              </ul>
            </div>
          </div>

          <div class="col-md-6">
            <div class="solar-card p-3 h-100">
              <div class="d-flex align-items-center mb-2">
                <span style="font-size:18px" class="me-2">&#128737;&#65039;</span>
                <h6 class="fw-bold mb-0 text-warning small text-uppercase" style="letter-spacing:.5px">Data Protection at a glance</h6>
              </div>
              <ul class="small text-secondary mb-0 ps-3" style="line-height:1.7">
                <li>Lawful bases: contract, legitimate interest, consent where required.</li>
                <li>Retention: project data while your account is active; financial records 7 years.</li>
                <li>Hosting: Render (US), Brevo (EU), Keycloak self-hosted.</li>
                <li>Your 8 rights honoured within 30 days. <a class="text-warning" href="https://solarpro.aiappinvent.com/data-protection" target="_blank" rel="noopener">Read the full statement &rarr;</a></li>
              </ul>
            </div>
          </div>

        </div>
      </div>
    </div>

    <footer class="sp-legal text-center small mt-3">
      <a href="https://solarpro.aiappinvent.com/privacy"        target="_blank" rel="noopener">Privacy</a>
      <span class="sp-legal__sep">&middot;</span>
      <a href="https://solarpro.aiappinvent.com/terms"          target="_blank" rel="noopener">Terms</a>
      <span class="sp-legal__sep">&middot;</span>
      <a href="https://solarpro.aiappinvent.com/data-protection" target="_blank" rel="noopener">Data Protection</a>
    </footer>
  </main>
</body>
</html>
</#macro>
