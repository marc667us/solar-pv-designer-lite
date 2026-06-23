<#--
    login.ftl -- byte-faithful mirror of templates/auth.html (mode=login).

    FreeMarker spine is unchanged from the working 3658ecc baseline
    (header / form / info sections, same conditionals). Only the HTML
    class names have been switched to the legacy Bootstrap utilities
    plus the .btn-solar custom class -- both as used by templates/auth.html.

    KC-specific bits preserved:
      - <form action> uses ${url.loginAction}
      - "Forgot password?" link uses ${url.loginResetCredentialsUrl}
      - "Create account" link uses ${url.registrationUrl}
      - field-level errors flip the input to `.is-invalid` (Bootstrap)
      - the credentialId hidden input is required by KC
-->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>

  <#if section = "header">
    Welcome Back

  <#elseif section = "form">

    <form id="kc-form-login" action="${url.loginAction}" method="post" autocomplete="off">

      <div class="mb-3">
        <label class="form-label small fw-bold text-secondary" for="username">EMAIL</label>
        <input type="email"
               id="username" name="username"
               value="${(login.username!'')}"
               class="form-control <#if messagesPerField.existsError('username','password')>is-invalid</#if>"
               placeholder="you@email.com"
               autocomplete="email"
               autofocus required/>
      </div>

      <div class="mb-3">
        <div class="d-flex justify-content-between align-items-center mb-1">
          <label class="form-label small fw-bold text-secondary mb-0" for="password">PASSWORD</label>
          <#if realm.resetPasswordAllowed>
            <a class="small text-warning" style="font-size:11px" href="${url.loginResetCredentialsUrl}">Forgot password?</a>
          </#if>
        </div>
        <input type="password"
               id="password" name="password"
               class="form-control <#if messagesPerField.existsError('username','password')>is-invalid</#if>"
               placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;"
               autocomplete="current-password" required/>
      </div>

      <#-- Inline field-level error -->
      <#if messagesPerField.existsError('username','password')>
        <div class="alert alert-danger small py-2 px-3 mb-3" role="alert">
          ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
        </div>
      </#if>

      <#-- Remember me (only if realm enables it) -->
      <#if realm.rememberMe && !usernameHidden??>
        <div class="form-check mb-3">
          <input tabindex="3" class="form-check-input" id="rememberMe" name="rememberMe" type="checkbox" <#if login.rememberMe??>checked</#if>>
          <label class="form-check-label small text-secondary" for="rememberMe">Keep me signed in</label>
        </div>
      </#if>

      <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>

      <button type="submit" name="login" id="kc-login" class="btn btn-solar w-100 mt-2">
        Sign In
      </button>
    </form>

  <#elseif section = "info">
    <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
      New user? <a class="text-warning" href="${url.registrationUrl}">Create account</a>
    </#if>
  </#if>

</@layout.registrationLayout>
