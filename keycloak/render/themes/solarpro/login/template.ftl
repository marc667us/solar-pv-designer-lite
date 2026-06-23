<#--
    template.ftl -- SolarPro chrome around every KC login screen.

    Mirrors templates/auth.html in the main app: a centered .solar-card
    holding a small ☀️ icon, a title, a subtitle, the form, and a footer
    link cluster. The look + class names match the legacy SolarPro login
    so the KC page sits inside the rest of the app visually.

    Sections that login.ftl / register.ftl / etc. supply via <#nested>:
      "header"  -- short page heading (e.g. "Welcome Back")
      "form"    -- the actual <form>...</form>
      "info"    -- bottom footer link (e.g. "New user? Create account")
-->
<#macro registrationLayout displayInfo=false displayMessage=true displayRequiredFields=false showAnotherWayIfPresent=true bodyClass="" showAuthMessages=true displayWide=false>
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title><#nested "header"> &mdash; SolarPro Global</title>
  <link rel="icon" href="${url.resourcesPath}/img/solarpro-logo.svg" type="image/svg+xml"/>
  <link rel="stylesheet" href="${url.resourcesPath}/css/login.css"/>
</head>
<body class="sp-page">
  <main class="sp-page__container">
    <section class="solar-card">

      <header class="solar-card__header">
        <div class="solar-card__icon" aria-hidden="true">&#9728;&#65039;</div>
        <h1 class="solar-card__title"><#nested "header"></h1>
        <p class="solar-card__subtitle">Sign in to your account.</p>
      </header>

      <#-- Error / info banner area -->
      <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
        <div class="solar-alert solar-alert--${message.type}">
          ${kcSanitize(message.summary)?no_esc}
        </div>
      </#if>

      <#-- The form goes here -->
      <#nested "form">

      <#-- Bottom info row (register link / 'try another way' etc.) -->
      <#if displayInfo>
        <div class="solar-card__footer">
          <#nested "info">
        </div>
      </#if>

    </section>

    <footer class="sp-legal">
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
