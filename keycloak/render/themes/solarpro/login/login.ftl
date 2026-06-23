<#--
    login.ftl  --  byte-faithful mirror of templates/auth.html (mode=login).

    The HTML below is structurally identical to the Jinja block in
    templates/auth.html when rendered under base.html.  Every class name
    is a Bootstrap 5.3.3 utility OR one of the two custom solar classes
    (`solar-card`, `btn-solar`) defined in templates/base.html and
    re-declared in login.css.

    The only Keycloak-specific substitutions:
      - <form action> points at ${url.loginAction} (KC handles CSRF itself)
      - the "Forgot password?" link uses ${url.loginResetCredentialsUrl}
      - the "Create account" link uses ${url.registrationUrl}
      - the username input is pre-filled from ${login.username!''}
      - a `credentialId` hidden field is added (KC requires it)
      - inline KC error message rendered as a Bootstrap `alert alert-danger`
      - field-level errors flip the input to `.is-invalid` (Bootstrap)
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password')
                            displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>

  <#if section = "header">
    Welcome Back

  <#elseif section = "form">

    <div class="row justify-content-center">
    <div class="col-md-5 col-lg-4">
      <div class="solar-card p-4 mt-4">

        <div class="text-center mb-4">
          <div style="font-size:36px">&#9728;&#65039;</div>
          <h4 class="fw-bold mt-2">Welcome Back</h4>
          <p class="text-secondary small">Sign in to your account.</p>
        </div>

        <#-- Realm-level message banner (locked-out / temporary-disabled / info) -->
        <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
          <#assign alertClass = (message.type == 'error')?then('danger',
                                (message.type == 'success')?then('success',
                                (message.type == 'warning')?then('warning', 'info'))) />
          <div class="alert alert-${alertClass} small py-2 px-3 mb-3" role="alert">
            ${kcSanitize(message.summary)?no_esc}
          </div>
        </#if>

        <form id="kc-form-login" method="post" action="${url.loginAction}" autocomplete="off">

          <div class="mb-3">
            <label class="form-label small fw-bold text-secondary" for="username">USERNAME</label>
            <input id="username" name="username" type="text"
                   value="${(login.username!'')}"
                   class="form-control <#if messagesPerField.existsError('username','password')>is-invalid</#if>"
                   placeholder="username"
                   autocomplete="username"
                   autofocus required/>
          </div>

          <div class="mb-3">
            <div class="d-flex justify-content-between align-items-center mb-1">
              <label class="form-label small fw-bold text-secondary mb-0" for="password">PASSWORD</label>
              <#if realm.resetPasswordAllowed>
                <a href="${url.loginResetCredentialsUrl}" class="small text-warning" style="font-size:11px">Forgot password?</a>
              </#if>
            </div>
            <input id="password" name="password" type="password"
                   class="form-control <#if messagesPerField.existsError('username','password')>is-invalid</#if>"
                   placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;"
                   autocomplete="current-password" required/>
          </div>

          <#-- Inline field-level error mirrors Bootstrap invalid-feedback styling -->
          <#if messagesPerField.existsError('username','password')>
            <div class="alert alert-danger small py-2 px-3 mb-3" role="alert">
              ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
            </div>
          </#if>

          <#-- Remember-me toggle (Bootstrap form-check) -->
          <#if realm.rememberMe && !usernameHidden??>
            <div class="form-check mb-3">
              <input class="form-check-input" type="checkbox" id="rememberMe" name="rememberMe"
                     <#if login.rememberMe??>checked</#if>>
              <label class="form-check-label small text-secondary" for="rememberMe">
                Keep me signed in
              </label>
            </div>
          </#if>

          <#-- KC requires this hidden field on every login POST -->
          <input type="hidden" id="id-hidden-input" name="credentialId"
                 <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>

          <button type="submit" name="login" id="kc-login" class="btn btn-solar w-100 mt-2">
            Sign In
          </button>
        </form>

        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
          <div class="text-center mt-3 small text-secondary">
            New user? <a href="${url.registrationUrl}" class="text-warning">Create account</a>
          </div>
        </#if>

      </div>
    </div>
    </div>

  </#if>

</@layout.registrationLayout>
