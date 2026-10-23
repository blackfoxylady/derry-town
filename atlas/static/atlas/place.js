// Place page (block 05): the confidence toggletip, the cover year switch and
// "In the novel" folded on the phone. Everything works without it: the toggletip
// text is also in the panel, the default cover year is shown and the details is native.
(function () {
  'use strict';

  // ⓘ toggletip: Enter / click opens, Esc or a click elsewhere closes; focus stays on the button.
  document.querySelectorAll('[data-toggletip]').forEach(function (button) {
    var tip = document.getElementById(button.getAttribute('aria-controls'));
    if (!tip) return;
    function set(open) {
      button.setAttribute('aria-expanded', String(open));
      tip.hidden = !open;
    }
    button.addEventListener('click', function () { set(button.getAttribute('aria-expanded') !== 'true'); });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') { set(false); button.focus(); }
    });
    document.addEventListener('click', function (event) {
      if (!button.contains(event.target) && !tip.contains(event.target)) set(false);
    });
  });

  // Cover years: role=tablist, ←/→ move between years, the image is the tabpanel.
  document.querySelectorAll('.place-cover').forEach(function (box) {
    var tabs = Array.prototype.slice.call(box.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        // Both years stay in the layout so they can crossfade (CSS); the hidden one is out of the tree.
        var panel = document.getElementById(t.getAttribute('aria-controls'));
        panel.classList.toggle('is-on', on);
        panel.setAttribute('aria-hidden', String(!on));
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () { select(tab, false); });
      tab.addEventListener('keydown', function (event) {
        var step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (!step) return;
        event.preventDefault();
        select(tabs[(index + step + tabs.length) % tabs.length], true);
      });
    });
  });

  // "In the novel" is open on the desktop and folded on the phone.
  if (window.matchMedia('(max-width: 63.99em)').matches) {
    document.querySelectorAll('details[data-fold-on-phone]').forEach(function (d) { d.open = false; });
  }
}());
