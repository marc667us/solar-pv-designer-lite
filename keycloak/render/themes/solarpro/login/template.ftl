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
    <div class="row justify-content-center">
      <div class="col-md-5 col-lg-4">
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
