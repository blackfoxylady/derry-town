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

  function initConsent() {
    var notice = document.getElementById('cookieConsent');
    var choice = readChoice();

    if (choice === 'accepted') {
      loadAnalytics();
      return;
    }
    if (choice === 'rejected' || !notice) return;

    notice.hidden = false;
    notice.querySelector('[data-cookie-accept]').addEventListener('click', function () {
      saveChoice('accepted');
      notice.hidden = true;
      loadAnalytics();
    });
    notice.querySelector('[data-cookie-reject]').addEventListener('click', function () {
      saveChoice('rejected');
      notice.hidden = true;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initConsent, { once: true });
  } else {
    initConsent();
  }
}());
