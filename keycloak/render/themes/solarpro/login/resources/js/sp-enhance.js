/*
 * sp-enhance.js -- progressively enhances the SolarPro Keycloak login
 * screens with a marketing hero, a sales pitch, technical-feature
 * bullets, and a privacy / data-protection footer.
 *
 * KC's theme system loads this via theme.properties (scripts=...). It
 * runs at end of <head>, so we defer DOM work until DOMContentLoaded.
 *
 * Why JS instead of Freemarker template overrides:
 *   * Avoids re-implementing keycloak.v2 template.ftl (PF5-heavy).
 *   * Keeps the form rendering, error messages, required-actions and
 *     credential flows untouched -- those are KC's job.
 *   * Easier to iterate on copy without re-deploying the realm.
 */
(function () {
  'use strict';

  function ready(fn) {
    if (document.readyState !== 'loading') return fn();
    document.addEventListener('DOMContentLoaded', fn);
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
        if (k === 'className')      node.className = attrs[k];
        else if (k === 'innerHTML') node.innerHTML = attrs[k];
        else                        node.setAttribute(k, attrs[k]);
      }
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  }

  // Resolve the theme resources base (KC injects a global keycloak object
  // with .resourceUrl when login pages render). Fall back to a wildcard
  // path if that global isn't present (very old KC builds).
  function resourceBase() {
    if (typeof window.keycloak !== 'undefined' && window.keycloak.resourceUrl) {
      return window.keycloak.resourceUrl;
    }
    // KC v2 always emits a <link rel="stylesheet" href="/resources/<ver>/login/solarpro/css/login.css">
    var link = document.querySelector('link[href*="/login/solarpro/css/"]');
    if (link) return link.getAttribute('href').replace(/\/css\/[^/]+$/, '');
    return '';
  }

  function buildHero() {
    var base = resourceBase();
    var logoUrl = base ? base + '/img/solarpro-logo.svg' : '/img/solarpro-logo.svg';

    var features = [
      { icon: '☀',  label: 'NREL-grade PV sizing, shading & yield modelling'    },
      { icon: '⚡',  label: 'AC & DC cable sizing aligned to BS 7671 / IEC 60364'},
      { icon: '\u{1F4CB}', label: 'Bill of Quantities + cost estimates in GHS / USD'   },
      { icon: '\u{1F6D2}', label: 'Component marketplace -- 437 verified products'    },
      { icon: '\u{1F4C4}', label: 'Engineering reports + client proposals (PDF / Excel)'},
    ];

    var hero = el('aside', { className: 'sp-hero', 'data-sp-injected': '1' }, [
      el('div', { className: 'sp-hero__brand' }, [
        el('img', { src: logoUrl, alt: 'SolarPro Global', className: 'sp-hero__logo' }),
        el('div', { className: 'sp-hero__wordmark' }, [
          el('div', { className: 'sp-hero__title' },    ['SolarPro Global']),
          el('div', { className: 'sp-hero__subtitle' }, ['Intelligent PV Solar System Design Platform']),
        ]),
      ]),
      el('p', { className: 'sp-hero__pitch' }, [
        'From residential rooftops to industrial farms -- design, size, cost ' +
        'and propose grid-tied, off-grid and hybrid PV systems in minutes.',
      ]),
      el('ul', { className: 'sp-hero__features' },
        features.map(function (f) {
          return el('li', null, [
            el('span', { className: 'sp-hero__icon', 'aria-hidden': 'true' }, [f.icon]),
            el('span', { className: 'sp-hero__feature-text' }, [f.label]),
          ]);
        })
      ),
      el('div', { className: 'sp-hero__sales' }, [
        el('span', { className: 'sp-hero__chip' }, ['Free 14-day trial']),
        el('span', { className: 'sp-hero__sales-text' }, [
          'Trusted by engineers across Ghana, Nigeria, Kenya, the UK and the US.',
        ]),
      ]),
    ]);
    return hero;
  }

  function buildFooter() {
    var year = (new Date()).getFullYear();
    return el('footer', { className: 'sp-privacy', 'data-sp-injected': '1' }, [
      el('div', { className: 'sp-privacy__row' }, [
        el('span', null, ['© ' + year + ' AI App Invent -- SolarPro Global']),
      ]),
      el('div', { className: 'sp-privacy__row' }, [
        el('a', { href: 'https://solarpro.aiappinvent.com/privacy', target: '_blank', rel: 'noopener' }, ['Privacy Policy']),
        el('span', { className: 'sp-privacy__sep' }, ['•']),
        el('a', { href: 'https://solarpro.aiappinvent.com/terms',   target: '_blank', rel: 'noopener' }, ['Terms of Service']),
        el('span', { className: 'sp-privacy__sep' }, ['•']),
        el('a', { href: 'https://solarpro.aiappinvent.com/data-protection', target: '_blank', rel: 'noopener' }, ['Data Protection']),
      ]),
      el('div', { className: 'sp-privacy__row sp-privacy__fineprint' }, [
        'Identity managed by Keycloak (Apache 2.0). Authentication credentials ' +
        'never leave SolarPro infrastructure. Personal data is processed under ' +
        'a lawful basis -- see Data Protection for retention windows, your ' +
        'rights of access and erasure, and the data-processor list.',
      ]),
    ]);
  }

  function mount() {
    if (document.querySelector('[data-sp-injected="1"]')) return; // idempotent

    var page = document.querySelector('.login-pf-page')
            || document.querySelector('.pf-v5-c-login')
            || document.body;

    // Find the existing main card to wrap. KC v2 puts the form inside
    // .card-pf (legacy) or .pf-v5-c-login__main (v2). We construct a flex
    // wrapper that holds [hero | form] side-by-side, fall back to stacked
    // on narrow screens.
    var card = document.querySelector('.card-pf')
            || document.querySelector('.pf-v5-c-login__main')
            || document.querySelector('main')
            || page;
    if (!card || !card.parentNode) return;

    var wrap = el('div', { className: 'sp-shell', 'data-sp-injected': '1' });
    var formPanel = el('section', { className: 'sp-form-panel', 'data-sp-injected': '1' });

    card.parentNode.insertBefore(wrap, card);
    wrap.appendChild(buildHero());
    formPanel.appendChild(card);
    wrap.appendChild(formPanel);

    // Append the privacy footer at page-level (outside the flex wrap) so
    // it sits centred under both columns.
    page.appendChild(buildFooter());

    document.documentElement.setAttribute('data-sp-enhanced', '1');
  }

  ready(mount);
})();
