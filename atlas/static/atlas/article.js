/* Article pages (block 03): scroll-spy for the table of contents.
   The links are plain anchors and work without JS; the script only marks the
   section in view with aria-current="true" and never moves focus. */
(function () {
  'use strict';

  var links = Array.prototype.slice.call(document.querySelectorAll('.toc__link'));
  if (!links.length) return;
  var ids = [];
  links.forEach(function (link) {
    var id = decodeURIComponent(link.hash.slice(1));
    if (ids.indexOf(id) < 0) ids.push(id);
  });
  var headings = ids.map(function (id) { return document.getElementById(id); }).filter(Boolean);
  if (!headings.length) return;

  var current = null;
  function mark(id) {
    if (id === current) return;
    current = id;
    links.forEach(function (link) {
      if (decodeURIComponent(link.hash.slice(1)) === id) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
  }

  // The section in view is the last heading above a line just under the
  // sticky header; at the very bottom of the page it is the last section.
  function update() {
    var line = 120;
    var id = headings[0].id;
    for (var i = 0; i < headings.length; i++) {
      if (headings[i].getBoundingClientRect().top <= line) id = headings[i].id;
      else break;
    }
    var doc = document.documentElement;
    if (window.innerHeight + window.scrollY >= doc.scrollHeight - 2) {
      var last = headings[headings.length - 1];
      if (last.getBoundingClientRect().top < window.innerHeight) id = last.id;
    }
    mark(id);
  }

  var queued = false;
  function onScroll() {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(function () { queued = false; update(); });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  window.addEventListener('hashchange', update);
  update();
})();
