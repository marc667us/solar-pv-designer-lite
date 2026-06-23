<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>

  <#if section = "header">
    Welcome Back
  <#elseif section = "form">

    <form id="kc-form-login" class="solar-form" action="${url.loginAction}" method="post" autocomplete="off">

      <div class="solar-field">
        <label class="solar-field__label" for="username">USERNAME</label>
        <input type="text"
               id="username" name="username"
               value="${(login.username!'')}"
               class="solar-field__input <#if messagesPerField.existsError('username','password')>solar-field__input--error</#if>"
               placeholder="username"
               autocomplete="username"
               autofocus required/>
      </div>

      <div class="solar-field">
        <div class="solar-field__row">
          <label class="solar-field__label" for="password">PASSWORD</label>
          <#if realm.resetPasswordAllowed>
            <a class="solar-link-warning solar-link-warning--small" href="${url.loginResetCredentialsUrl}">Forgot password?</a>
          </#if>
        </div>
        <input type="password"
               id="password" name="password"
               class="solar-field__input <#if messagesPerField.existsError('username','password')>solar-field__input--error</#if>"
               placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;"
               autocomplete="current-password" required/>
      </div>

      <#-- Inline field-level error message -->
      <#if messagesPerField.existsError('username','password')>
        <div class="solar-alert solar-alert--error">
          ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
        </div>
      </#if>

      <#-- Remember me (only if realm enables it) -->
      <#if realm.rememberMe && !usernameHidden??>
        <label class="solar-check">
          <input tabindex="3" id="rememberMe" name="rememberMe" type="checkbox" <#if login.rememberMe??>checked</#if>>
          <span>Keep me signed in</span>
        </label>
      </#if>

      <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>

      <button type="submit" name="login" id="kc-login" class="solar-btn-primary">
        Sign In
      </button>
    </form>

  <#elseif section = "info">
    <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
      <span class="solar-info-text">New user?</span>
      <a class="solar-link-warning" href="${url.registrationUrl}">Create account</a>
    </#if>
  </#if>

</@layout.registrationLayout>
