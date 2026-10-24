// Photo page (block 08): ← → and swipe move within the gallery's current selection, Esc and
// Close return to it. The selection comes from gallery.js through sessionStorage; without it
// the server's links (all photos in gallery order) stay as they are.
(function () {
  'use strict';
  var stateEl = document.getElementById('viewerState');
  if (!stateEl) return;
  var conf = JSON.parse(stateEl.textContent);
  var T = conf.strings;
  var byId = {};
  conf.sequence.forEach(function (p) { byId[p.id] = p; });
  var prevLink = document.querySelector('[data-prev]');
  var nextLink = document.querySelector('[data-next]');
  var closeLinks = Array.prototype.slice.call(document.querySelectorAll('[data-close]'));
  var counter = document.querySelector('[data-counter]');
  var counterLabel = document.querySelector('[data-counter-label]');
  var dots = document.querySelector('[data-dots]');
  var MAX_DOTS = 12;  // D30: more photos — only the counter

  function fill(template, values) {
    return template.replace(/%\((\w+)\)s/g, function (all, key) { return key in values ? values[key] : all; });
  }
  function isGallery(path) {
    return path.indexOf(conf.base) === 0 && !/\/photos\/\d+\/$/.test(path.split('?')[0]);
  }

  // The selection the visitor came from: stored by the gallery (only while browsing from the
  // gallery or between photos, not when arriving from the map or a place page), or the
  // referring gallery page.
  var list = conf.sequence;
  var back = null;
  var stored = null;
  var ref = null;
  try { ref = document.referrer ? new URL(document.referrer) : null; } catch (e) { ref = null; }
  var fromSite = ref && ref.origin === location.origin;
  var fromGallery = fromSite && ref.pathname.indexOf(conf.base) === 0;  // gallery or a photo page
  try { stored = JSON.parse(sessionStorage.getItem('derry.gallery') || 'null'); } catch (e) { stored = null; }
  if (fromGallery && stored && stored.path && isGallery(stored.path)) {
    back = stored.path;
    if (stored.ids && stored.ids.indexOf(conf.id) >= 0) {
      list = stored.ids.map(function (id) { return byId[id]; }).filter(Boolean);
    }
  } else if (fromSite && isGallery(ref.pathname)) {
    back = ref.pathname + ref.search;
  }
  if (back) closeLinks.forEach(function (a) { a.href = back; });

  var index = -1;
  list.forEach(function (p, i) { if (p.id === conf.id) index = i; });
  if (index < 0) { list = conf.sequence; index = list.map(function (p) { return p.id; }).indexOf(conf.id); }
  var prev = list[index - 1], next = list[index + 1];
  function point(link, photo, template) {
    link.hidden = !photo;
    if (!photo) { link.removeAttribute('href'); link.removeAttribute('aria-label'); return; }
    link.href = photo.url;
    link.setAttribute('aria-label', fill(template, { caption: photo.caption }));
  }
  point(prevLink, prev, T.prev);
  point(nextLink, next, T.next);
  counter.textContent = (index + 1) + ' / ' + list.length;
  counterLabel.textContent = fill(T.counter, { n: index + 1, total: list.length });
  if (list.length > 1 && list.length <= MAX_DOTS) {
    list.forEach(function (p, i) {
      var dot = document.createElement('span');
      dot.className = 'viewer__dot' + (i === index ? ' is-current' : '');
      dots.appendChild(dot);
    });
  }

  function go(photo) { if (photo) location.href = photo.url; }
  function close() { location.href = closeLinks[0].href; }

  document.addEventListener('keydown', function (event) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    var t = event.target;
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    if (event.key === 'ArrowLeft') { event.preventDefault(); go(prev); }
    else if (event.key === 'ArrowRight') { event.preventDefault(); go(next); }
    else if (event.key === 'Escape' && !(t && t.closest && t.closest('#cookieConsent'))) { event.preventDefault(); close(); }
  });

  // Swipe: a mostly horizontal move of 40px or more; vertical scrolling is left alone.
  var stage = document.getElementById('viewerStage');
  var start = null;
  stage.addEventListener('touchstart', function (e) {
    var zoomed = window.visualViewport && window.visualViewport.scale > 1;  // panning a zoomed page
    start = e.touches.length === 1 && !zoomed ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
  }, { passive: true });
  stage.addEventListener('touchend', function (e) {
    if (!start) return;
    var dx = e.changedTouches[0].clientX - start.x, dy = e.changedTouches[0].clientY - start.y;
    start = null;
    if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? next : prev);
  });
}());
