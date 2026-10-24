// Gallery (block 07): multi-select filters with faceted counts (OR inside a group, AND between
// groups), caption search, URL state for up to two values, "Show more", a reading-order layout
// and the phone filter sheet. The server renders the current selection; every photo comes in
// #galleryState. Selections beyond the URL limit and the search live in sessionStorage only,
// so crawlers never see more addresses (incident 17.10.2026).
(function () {
  'use strict';
  var stateEl = document.getElementById('galleryState');
  var grid = document.getElementById('galleryGrid');
  var aside = document.getElementById('galleryFilters');
  if (!stateEl || !grid || !aside) return;
  var conf = JSON.parse(stateEl.textContent);
  var T = conf.strings;
  var lang = document.documentElement.lang === 'ru' ? 'ru' : 'en';
  var GROUPS = ['character', 'place', 'year', 'tag'];
  var QUERY = ['place', 'character', 'tag', 'year'];  // parameter order, as on the server
  var URL_LIMIT = 2;
  var STORE = 'derry.gallery';
  var photos = conf.photos;
  var searches = [document.getElementById('gallerySearch'), document.getElementById('gallerySearchPhone')].filter(Boolean);
  var status = document.getElementById('galleryStatus');
  var chips = document.getElementById('galleryChips');
  var empty = document.getElementById('galleryEmpty');
  var more = document.getElementById('galleryMore');
  var head = document.getElementById('galleryHead');
  var openFilters = document.getElementById('openGalleryFilters');
  var phone = window.matchMedia('(max-width: 47.99em)');
  var twoColumns = window.matchMedia('(max-width: 63.99em)');

  // ---- plural forms prepared by the server: [one, few, many] (RU) or [one, other, other] (EN)
  function pluralIndex(n) {
    if (lang === 'ru') return n % 10 === 1 && n % 100 !== 11 ? 0 : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 1 : 2;
    return n === 1 ? 0 : 1;
  }
  function fill(template, values) {
    return template.replace(/%\((\w+)\)s/g, function (all, key) { return key in values ? values[key] : all; });
  }
  function norm(text) {
    return (text || '').toLowerCase().replace(/ё/g, 'е').normalize('NFD').replace(/[̀-ͯ]/g, '');
  }
  function copySelection(sel) {
    var out = {};
    GROUPS.forEach(function (g) { out[g] = (sel && sel[g] || []).slice(); });
    return out;
  }
  function selectionKey(sel) {
    return GROUPS.map(function (g) { return g + '=' + sel[g].slice().sort().join(','); }).join('&');
  }
  function count(sel) {
    return GROUPS.reduce(function (n, g) { return n + sel[g].length; }, 0);
  }
  photos.forEach(function (p) { p.search = norm(p.caption); });

  // ---- sidebar options: links for crawlers and no-JS, toggles from here on
  var options = [];
  Array.prototype.forEach.call(aside.querySelectorAll('a[data-group]'), function (link) {
    var button = document.createElement('button');
    var tag = link.dataset.group === 'tag';
    button.type = 'button';
    button.className = link.className;
    button.innerHTML = link.innerHTML;
    button.dataset.group = link.dataset.group;
    button.dataset.value = link.dataset.value;
    if (!tag) button.setAttribute('role', 'checkbox');
    link.parentNode.replaceChild(button, link);
    var label = tag ? button.firstChild.textContent.trim() : button.querySelector('.filter-opt__label').textContent;
    options.push({ el: button, group: button.dataset.group, value: button.dataset.value, label: label,
                   count: button.querySelector('.chip__count'), state: tag ? 'aria-pressed' : 'aria-checked' });
  });
  function labelOf(group, value) {
    var o = options.filter(function (o) { return o.group === group && o.value === value; })[0];
    return o ? o.label : value;
  }
  function known(group, value) {
    return options.some(function (o) { return o.group === group && o.value === value; });
  }

  // ---- state: the server's selection, or the stored one when coming back to the same address
  var initial = copySelection(conf.selection);
  var state = { sel: copySelection(initial), q: '', limit: T.page };
  function here() { return location.pathname + location.search; }
  (function restore() {
    var stored;
    try { stored = JSON.parse(sessionStorage.getItem(STORE) || 'null'); } catch (e) { stored = null; }
    if (!stored || stored.path !== here()) return;
    var nav = (window.performance && performance.getEntriesByType && performance.getEntriesByType('navigation')[0] || {}).type;
    var from = '';
    try { from = document.referrer ? new URL(document.referrer).pathname : ''; } catch (e) { from = ''; }
    if (nav !== 'back_forward' && nav !== 'reload' && !/\/photos\/\d+\/$/.test(from)) return;
    var sel = copySelection(stored.sel);
    GROUPS.forEach(function (g) { sel[g] = sel[g].filter(function (v) { return known(g, v); }); });
    state.sel = sel;
    state.q = typeof stored.q === 'string' ? stored.q : '';
    state.limit = Math.max(T.page, +stored.limit || 0);
  }());

  // ---- matching
  var words = [];
  function matches(p, skip) {
    for (var i = 0; i < words.length; i++) if (p.search.indexOf(words[i]) < 0) return false;
    for (var j = 0; j < GROUPS.length; j++) {
      var g = GROUPS[j], values = state.sel[g];
      if (g === skip || !values.length) continue;
      if (!values.some(function (v) { return p[g].indexOf(v) >= 0; })) return false;
    }
    return true;
  }

  // ---- addresses: one value — its landing page, two — the query form, more — unchanged
  function urlFor(sel) {
    var n = count(sel);
    if (!n) return conf.base;
    if (n === 1) {
      for (var i = 0; i < GROUPS.length; i++) if (sel[GROUPS[i]].length) return conf.landings[GROUPS[i] + ':' + sel[GROUPS[i]][0]];
    }
    return conf.base + '?' + QUERY.filter(function (g) { return sel[g].length; }).map(function (g) {
      return g + '=' + sel[g].slice().sort().map(function (v) {
        return encodeURIComponent(v).replace(/%3A/gi, ':');
      }).join(',');
    }).join('&');
  }

  // ---- grid items: server ones are reused, the rest are built from the data on demand
  var items = {};
  Array.prototype.forEach.call(grid.children, function (li) { items[li.dataset.id] = li; });
  var sizes = grid.querySelector('img') ? grid.querySelector('img').getAttribute('sizes')
    : '(max-width: 47.99em) calc(50vw - 22px), (max-width: 63.99em) calc(50vw - 170px), 270px';
  function item(p) {
    if (items[p.id]) return items[p.id];
    var li = document.createElement('li');
    li.className = 'gallery-item';
    li.dataset.id = p.id;
    var a = document.createElement('a');
    a.className = 'gallery-item__link';
    a.href = p.url;
    var img = document.createElement('img');
    img.className = 'gallery-item__img';
    img.src = p.src;
    img.srcset = p.srcset;
    img.sizes = sizes;
    img.alt = p.alt;
    img.width = p.w;
    img.height = p.h;
    img.loading = 'lazy';
    img.decoding = 'async';
    var caption = document.createElement('span');
    caption.className = 'gallery-item__caption';
    caption.setAttribute('aria-hidden', 'true');
    caption.textContent = p.caption;
    a.appendChild(img);
    a.appendChild(caption);
    if (p.meta) {
      var meta = document.createElement('span');
      meta.className = 't-meta';
      meta.textContent = p.meta;
      a.appendChild(meta);
    }
    li.appendChild(a);
    items[p.id] = li;
    return li;
  }

  // ---- render
  var hits = [];
  var headHtml = head.innerHTML;
  var headChanged = false;
  function render(keepLimit) {
    if (!keepLimit) state.limit = T.page;
    words = norm(state.q).split(/\s+/).filter(Boolean);
    hits = photos.filter(function (p) { return matches(p); });
    var selected = count(state.sel);
    var changed = selectionKey(state.sel) !== selectionKey(initial);

    // Faceted counts: what each option gives with the other groups (and the search) applied.
    options.forEach(function (o) {
      var on = state.sel[o.group].indexOf(o.value) >= 0;
      var n = photos.filter(function (p) { return p[o.group].indexOf(o.value) >= 0 && matches(p, o.group); }).length;
      o.count.textContent = n;
      o.el.setAttribute(o.state, String(on));
      o.el.classList.toggle('is-empty', !n);
      if (!n && !on) o.el.setAttribute('aria-disabled', 'true'); else o.el.removeAttribute('aria-disabled');
    });
    Array.prototype.forEach.call(aside.querySelectorAll('.gallery-filters__more'), function (d) {
      if (d.querySelector('[aria-checked="true"]')) d.open = true;
    });

    // Head: a single-filter page keeps its heading only while its own filter is selected.
    if (changed !== headChanged) {
      headChanged = changed;
      if (changed) {
        head.querySelector('h1').textContent = T.heading;
        Array.prototype.forEach.call(head.querySelectorAll('.gallery-head__intro, .gallery-head__links, .crumbs li:nth-child(3)'), function (el) { el.hidden = true; });
      } else {
        head.innerHTML = headHtml;
      }
    }

    // Status line and chips of the selection.
    var showChips = selected > 0 && (changed || selected > 1);
    var text = showChips || state.q
      ? fill(T.of_total[pluralIndex(photos.length)], { n: hits.length, total: photos.length })
      : fill(T.photos[pluralIndex(hits.length)], { n: hits.length });
    if (status.textContent !== text) status.textContent = text;
    chips.textContent = '';
    if (showChips) {
      GROUPS.forEach(function (group) {
        state.sel[group].forEach(function (value) {
          var label = labelOf(group, value);
          var b = document.createElement('button');
          b.type = 'button';
          b.className = 'chip chip--set';
          b.setAttribute('aria-label', fill(T.remove, { name: label }));
          b.innerHTML = '<span></span>' + T.close_icon;
          b.firstChild.textContent = label;
          b.addEventListener('click', function () {
            toggle(group, value);
            var next = chips.querySelector('.chip');
            if (next) next.focus(); else focusAfterClear();
          });
          chips.appendChild(b);
        });
      });
    }
    document.querySelectorAll('[data-clear]').forEach(function (b) {
      if (b.classList.contains('gallery-results__clear')) b.hidden = !showChips;
      else if (b.tagName === 'BUTTON') b.disabled = !selected && !state.q;
    });

    renderGrid();

    // Phone: the Filters button and the sheet's "Show N photographs".
    if (openFilters) {
      var badge = openFilters.querySelector('[data-filter-count]');
      badge.hidden = !selected;
      badge.textContent = selected;
      openFilters.classList.toggle('btn--primary', selected > 0);
      openFilters.classList.toggle('btn--quiet', !selected);
      openFilters.setAttribute('aria-label', selected ? fill(T.filters_n, { n: selected }) : T.filters);
    }
    var show = aside.querySelector('[data-show-count]');
    if (show) show.textContent = fill(T.show[pluralIndex(hits.length)], { n: hits.length });

    if (selected <= URL_LIMIT) {
      var url = urlFor(state.sel);
      if (url && url !== here()) history.replaceState(history.state, '', url);
    }
    save();
  }

  function renderGrid() {
    var visible = hits.slice(0, state.limit);
    var keep = {};
    visible.forEach(function (p) { keep[p.id] = true; grid.appendChild(item(p)); });
    Object.keys(items).forEach(function (id) { if (!keep[id] && items[id].parentNode) grid.removeChild(items[id]); });
    grid.hidden = !hits.length;
    empty.hidden = hits.length > 0;
    var rest = hits.length - visible.length;
    more.hidden = rest <= 0;
    if (rest > 0) {
      more.querySelector('[data-shown]').textContent = fill(T.shown, { n: visible.length, total: hits.length });
      more.querySelector('[data-more]').textContent = fill(T.more, { n: Math.min(T.page, rest) });
    }
    layout();
  }

  function save() {
    try {
      sessionStorage.setItem(STORE, JSON.stringify({
        path: here(), sel: state.sel, q: state.q, limit: state.limit,
        ids: hits.map(function (p) { return p.id; })
      }));
    } catch (e) { /* private mode: the selection simply is not remembered */ }
  }

  // ---- layout: columns filled in reading order (each item goes to the shortest column)
  function layout() {
    var list = Array.prototype.slice.call(grid.children);
    var width = grid.clientWidth;
    if (!width || !list.length) { grid.style.height = ''; return; }
    var cols = twoColumns.matches ? 2 : 3;
    var gap = phone.matches ? 12 : 24;
    var colWidth = (width - gap * (cols - 1)) / cols;
    grid.classList.add('is-laid-out');
    list.forEach(function (li) { li.style.width = colWidth + 'px'; });
    var heights = list.map(function (li) { return li.offsetHeight; });
    var tops = [];
    for (var c = 0; c < cols; c++) tops.push(0);
    list.forEach(function (li, i) {
      var col = tops.indexOf(Math.min.apply(null, tops));
      li.style.left = col * (colWidth + gap) + 'px';
      li.style.top = tops[col] + 'px';
      tops[col] += heights[i] + gap;
    });
    grid.style.height = Math.max(0, Math.max.apply(null, tops) - gap) + 'px';
  }
  // Re-measure on width changes (ResizeObserver) and on window resizes (text zoom changes the
  // caption heights without changing the width); once per frame, outside the observer callback.
  var lastWidth = 0, frame = 0;
  function relayout() {
    if (frame) return;
    frame = requestAnimationFrame(function () { frame = 0; layout(); });
  }
  if (window.ResizeObserver) {
    new ResizeObserver(function () {
      if (grid.clientWidth !== lastWidth) { lastWidth = grid.clientWidth; relayout(); }
    }).observe(grid);
  }
  window.addEventListener('resize', relayout);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(relayout);

  // ---- actions
  function toggle(group, value) {
    var values = state.sel[group];
    var i = values.indexOf(value);
    if (i < 0) values.push(value); else values.splice(i, 1);
    render();
  }
  function clearAll() {
    state.sel = copySelection(null);
    state.q = '';
    searches.forEach(function (s) { s.value = ''; });
    render();
    focusAfterClear();
  }
  // Clearing hides or disables the pressed button: keep focus somewhere useful
  // (inside the sheet while it is open, so the focus trap still holds).
  function focusAfterClear() {
    if (aside.classList.contains('is-sheet-open')) { aside.querySelector('.gallery-filters__close').focus(); return; }
    var visible = searches.filter(function (s) { return s.offsetParent !== null; })[0];
    (visible || status).focus();
  }

  options.forEach(function (o) {
    o.el.addEventListener('click', function () {
      if (o.el.getAttribute('aria-disabled') === 'true') return;
      toggle(o.group, o.value);
    });
  });
  document.querySelectorAll('[data-clear]').forEach(function (b) {
    b.addEventListener('click', function (event) { event.preventDefault(); clearAll(); });
  });
  more.querySelector('[data-more]').addEventListener('click', function () {
    var first = state.limit;
    state.limit += T.page;
    renderGrid();
    save();
    var next = grid.children[first];
    if (next) next.querySelector('a').focus();
  });
  var timer;
  searches.forEach(function (search) {
    search.value = state.q;
    search.addEventListener('input', function () {
      searches.forEach(function (other) { if (other !== search) other.value = search.value; });
      clearTimeout(timer);
      timer = setTimeout(function () { state.q = search.value.trim(); render(); }, 150);
    });
    search.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && search.value) {
        event.preventDefault();
        event.stopPropagation();
        searches.forEach(function (s) { s.value = ''; });
        state.q = '';
        render();
      }
    });
  });

  // ---- phone filter sheet: a modal dialog over the page; changes apply at once
  var lastFocus = null;
  function focusables() {
    return Array.prototype.slice.call(aside.querySelectorAll('button, input, summary, [href], [tabindex]:not([tabindex="-1"])'))
      .filter(function (el) { return !el.disabled && el.offsetParent !== null; });
  }
  // Everything outside the sheet is inert while it is open (aria-modal alone is not enough on iOS).
  function setInert(on) {
    for (var node = aside; node && node !== document.body; node = node.parentElement) {
      Array.prototype.forEach.call(node.parentElement.children, function (sibling) {
        if (sibling !== node && sibling.tagName !== 'SCRIPT') sibling.inert = on;
      });
    }
  }
  function setSheet(open) {
    aside.classList.toggle('is-sheet-open', open);
    setInert(open);
    document.documentElement.classList.toggle('has-sheet', open);
    if (open) {
      lastFocus = document.activeElement;
      aside.setAttribute('role', 'dialog');
      aside.setAttribute('aria-modal', 'true');
      aside.setAttribute('aria-labelledby', 'galleryFiltersTitle');
      aside.removeAttribute('aria-label');
      openFilters.setAttribute('aria-expanded', 'true');
      aside.querySelector('.gallery-filters__close').focus();
    } else {
      aside.removeAttribute('role');
      aside.removeAttribute('aria-modal');
      aside.removeAttribute('aria-labelledby');
      aside.setAttribute('aria-label', T.filters);
      openFilters.setAttribute('aria-expanded', 'false');
      if (lastFocus && lastFocus.offsetParent !== null) lastFocus.focus();
    }
  }
  if (openFilters) {
    openFilters.setAttribute('aria-expanded', 'false');
    openFilters.addEventListener('click', function () { setSheet(true); });
    aside.querySelectorAll('[data-close-filters]').forEach(function (b) { b.addEventListener('click', function () { setSheet(false); }); });
    aside.addEventListener('keydown', function (event) {
      if (!aside.classList.contains('is-sheet-open')) return;
      if (event.key === 'Escape') { event.preventDefault(); setSheet(false); return; }
      if (event.key !== 'Tab') return;
      var f = focusables();
      if (!f.length) return;
      if (event.shiftKey && document.activeElement === f[0]) { event.preventDefault(); f[f.length - 1].focus(); }
      else if (!event.shiftKey && document.activeElement === f[f.length - 1]) { event.preventDefault(); f[0].focus(); }
    });
    // Swipe down on the sheet head closes it.
    var sheetHead = aside.querySelector('.gallery-filters__head'), startY = null;
    sheetHead.addEventListener('touchstart', function (e) { startY = e.touches[0].clientY; }, { passive: true });
    sheetHead.addEventListener('touchend', function (e) {
      if (startY !== null && e.changedTouches[0].clientY - startY > 60) setSheet(false);
      startY = null;
    });
    // Leaving the phone layout closes the sheet.
    (phone.addEventListener ? phone.addEventListener.bind(phone, 'change') : phone.addListener.bind(phone))(function () {
      if (!phone.matches && aside.classList.contains('is-sheet-open')) {
        lastFocus = document.getElementById('gallerySearch');
        setSheet(false);
      }
      layout();
    });
  }
  (twoColumns.addEventListener ? twoColumns.addEventListener.bind(twoColumns, 'change') : twoColumns.addListener.bind(twoColumns))(layout);

  render(true);
}());
