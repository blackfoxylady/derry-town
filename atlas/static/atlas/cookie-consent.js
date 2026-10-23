(function () {
  'use strict';

  var STORAGE_KEY = 'derry_analytics_consent_v2';
  var script = document.currentScript;
  var googleId = script && script.dataset.googleId;
  var yandexId = script && script.dataset.yandexId;
  var analyticsLoaded = false;

  function readChoice() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function saveChoice(choice) {
    try {
      window.localStorage.setItem(STORAGE_KEY, choice);
    } catch (error) {
      // Browsers may disable storage. The choice still applies to this page.
    }
  }

  function loadGoogleAnalytics() {
    if (!googleId) return;

    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () {
      window.dataLayer.push(arguments);
    };
    window.gtag('js', new Date());
    window.gtag('config', googleId);

    var googleScript = document.createElement('script');
    googleScript.async = true;
    googleScript.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(googleId);
    document.head.appendChild(googleScript);
  }

  function loadYandexMetrica() {
    if (!yandexId) return;

    window.ym = window.ym || function () {
      (window.ym.a = window.ym.a || []).push(arguments);
    };
    window.ym.l = Number(new Date());

    var metricaScript = document.createElement('script');
    metricaScript.async = true;
    metricaScript.src = 'https://mc.yandex.ru/metrika/tag.js?id=' + encodeURIComponent(yandexId);
    document.head.appendChild(metricaScript);

    window.ym(Number(yandexId), 'init', {
      ssr: true,
      webvisor: true,
      clickmap: true,
      ecommerce: 'dataLayer',
      referrer: document.referrer,
      url: window.location.href,
      accurateTrackBounce: true,
      trackLinks: true
    });
  }

  function loadAnalytics() {
    if (analyticsLoaded) return;
    analyticsLoaded = true;
    loadGoogleAnalytics();
    loadYandexMetrica();
  }

  // Analytics cookies are first-party (_ga*, _gid, _ym_*). With the choice
  // "rejected" they are removed for this host and its parent domains on every
  // page load: scripts that were live before a reload may have rewritten them.
  function clearAnalyticsCookies() {
    var names = document.cookie.split(';').map(function (pair) {
      return pair.split('=')[0].trim();
    }).filter(function (name) {
      return /^(_ga|_gid|_gat|_ym)/.test(name);
    });
    var parts = window.location.hostname.split('.');
    var domains = [''];
    for (var i = 0; i < parts.length - 1; i++) domains.push('; domain=.' + parts.slice(i).join('.'));
    names.forEach(function (name) {
      domains.forEach(function (domain) {
        document.cookie = name + '=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' + domain;
      });
    });
    try {
      Object.keys(window.localStorage).forEach(function (key) {
        if (/^_ym/.test(key)) window.localStorage.removeItem(key);
      });
    } catch (error) {
      // Storage may be disabled; there is nothing to remove then.
    }
  }

  function initConsent() {
    var notice = document.getElementById('cookieConsent');
    var choice = readChoice();

    if (choice === 'accepted') loadAnalytics();
    if (choice === 'rejected') clearAnalyticsCookies();
    if (!notice) return;

    var accept = notice.querySelector('[data-cookie-accept]');
    var reject = notice.querySelector('[data-cookie-reject]');
    var returnTo = null;  // where focus goes after a choice in a reopened notice

    function hide() {
      notice.hidden = true;
      if (returnTo && document.contains(returnTo)) returnTo.focus();
      returnTo = null;
    }

    function show(stored) {
      // Reopened from "Cookie settings": the stored choice is marked as pressed.
      accept.removeAttribute('aria-pressed');
      reject.removeAttribute('aria-pressed');
      if (stored === 'accepted' || stored === 'rejected') {
        accept.setAttribute('aria-pressed', String(stored === 'accepted'));
        reject.setAttribute('aria-pressed', String(stored === 'rejected'));
      }
      notice.hidden = false;
    }

    accept.addEventListener('click', function () {
      saveChoice('accepted');
      hide();
      loadAnalytics();
    });
    reject.addEventListener('click', function () {
      saveChoice('rejected');
      hide();
      if (analyticsLoaded) {
        // Loaded scripts cannot be switched off in place: stop GA, drop the cookies, reload.
        if (googleId) window['ga-disable-' + googleId] = true;
        clearAnalyticsCookies();
        window.location.reload();
      }
    });

    // "Cookie settings" in the footer and the menu panel reopen the notice.
    document.addEventListener('click', function (event) {
      var opener = event.target.closest && event.target.closest('[data-cookie-settings]');
      if (!opener) return;
      // From the menu panel, focus later returns to the button that opened the panel.
      returnTo = opener.closest('#site-menu') ? document.querySelector('[data-menu-open]') : opener;
      document.dispatchEvent(new CustomEvent('derry:close-menu'));
      show(readChoice());
      (readChoice() === 'accepted' ? accept : reject).focus();
    });

    if (!choice) show(null);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initConsent, { once: true });
  } else {
    initConsent();
  }
}());
