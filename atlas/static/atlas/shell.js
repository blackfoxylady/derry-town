/* Site shell (block 02): the About Derry disclosure and the menu panel.
   Both work on server-rendered HTML; without JS the dropdown stays closed and
   the footer carries the same links. */
(function () {
  'use strict';

  // ---- About Derry: a disclosure (plain links, Tab works as usual) ----------
  var disclosures = [];
  document.querySelectorAll('[data-disclosure]').forEach(function (item) {
    var button = item.querySelector('.nav__disclosure');
    var menu = document.getElementById(button.getAttribute('aria-controls'));
    if (!menu) return;
    var links = function () { return Array.prototype.slice.call(menu.querySelectorAll('a')); };

    function setOpen(open, focusButton) {
      button.setAttribute('aria-expanded', String(open));
      menu.hidden = !open;
      if (!open && focusButton) button.focus();
    }
    disclosures.push(setOpen);

    button.addEventListener('click', function () {
      setOpen(button.getAttribute('aria-expanded') !== 'true');
    });
    button.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setOpen(true);
        links()[0].focus();
      }
    });
    menu.addEventListener('keydown', function (event) {
      var list = links();
      var index = list.indexOf(document.activeElement);
      var next = null;
      if (event.key === 'ArrowDown') next = list[(index + 1) % list.length];
      else if (event.key === 'ArrowUp') next = list[(index - 1 + list.length) % list.length];
      else if (event.key === 'Home') next = list[0];
      else if (event.key === 'End') next = list[list.length - 1];
      if (next) {
        event.preventDefault();
        next.focus();
      }
    });
    item.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !menu.hidden) {
        event.preventDefault();
        setOpen(false, true);
      }
    });
    // Clicking outside or tabbing out closes it.
    document.addEventListener('click', function (event) {
      if (!menu.hidden && !item.contains(event.target)) setOpen(false);
    });
    item.addEventListener('focusout', function (event) {
      if (!menu.hidden && event.relatedTarget && !item.contains(event.relatedTarget)) setOpen(false);
    });
  });

  // ---- Menu panel: a modal dialog --------------------------------------------
  var panel = document.getElementById('site-menu');
  var scrim = document.querySelector('[data-menu-scrim]');
  if (!panel || !scrim) return;
  var openers = document.querySelectorAll('[data-menu-open]');
  var lastOpener = null;
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function openPanel(opener) {
    lastOpener = opener || document.activeElement;
    panel.hidden = false;
    scrim.hidden = false;
    document.documentElement.classList.add('is-menu-open');
    openers.forEach(function (button) { button.setAttribute('aria-expanded', 'true'); });
    panel.querySelector('[data-menu-close]').focus();
  }

  function closePanel(returnFocus) {
    if (panel.hidden) return;
    panel.hidden = true;
    scrim.hidden = true;
    document.documentElement.classList.remove('is-menu-open');
    openers.forEach(function (button) { button.setAttribute('aria-expanded', 'false'); });
    if (returnFocus && lastOpener && document.contains(lastOpener)) lastOpener.focus();
  }

  openers.forEach(function (button) {
    button.addEventListener('click', function () { openPanel(button); });
  });
  panel.querySelector('[data-menu-close]').addEventListener('click', function () { closePanel(true); });
  scrim.addEventListener('click', function () { closePanel(true); });
  // "Cookie settings" inside the panel: the notice takes the focus instead.
  document.addEventListener('derry:close-menu', function () { closePanel(false); });

  // On document, not on the panel: a click on an empty part of the panel moves
  // focus to <body>, and Tab must still stay inside.
  document.addEventListener('keydown', function (event) {
    if (panel.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closePanel(true);
      return;
    }
    if (event.key !== 'Tab') return;
    var items = Array.prototype.filter.call(panel.querySelectorAll(FOCUSABLE), function (node) {
      return node.offsetParent !== null;
    });
    if (!items.length) return;
    var first = items[0];
    var last = items[items.length - 1];
    if (!panel.contains(document.activeElement)) {
      event.preventDefault();
      panel.querySelector('[data-menu-close]').focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  // Back from the bfcache: a page left through a panel link returns with the panel closed.
  window.addEventListener('pageshow', function () {
    closePanel(false);
    disclosures.forEach(function (setOpen) { setOpen(false); });
  });
}());
