// Place index (block 06): search, faceted filters (OR inside a group, AND between groups),
// sort, Cards / Compact, URL state and the phone filter sheet. Every tile is in the HTML;
// this script only hides, shows and reorders them.
(function () {
  'use strict';
  var root = document.getElementById('placesCatalog');
  var list = document.getElementById('placesList');
  if (!root || !list) return;
  var T = JSON.parse(document.getElementById('placesStrings').textContent);
  var lang = document.documentElement.lang === 'ru' ? 'ru' : 'en';
  var tiles = Array.prototype.slice.call(list.children);
  var total = tiles.length;
  var GROUPS = ['sure', 'kind', 'media'];
  var aside = document.getElementById('placeFilters');
  var inputs = Array.prototype.slice.call(aside.querySelectorAll('.filter-opt__input'));
  var searches = [document.getElementById('placeSearch'), document.getElementById('placeSearchPhone')].filter(Boolean);
  var status = document.getElementById('placeStatus');
  var chips = document.getElementById('activeChips');
  var empty = document.getElementById('placesEmpty');
  var auditChips = Array.prototype.slice.call(document.querySelectorAll('[data-audit]'));
  var sortButton = document.getElementById('sortButton');
  var sortMenu = document.getElementById('sortMenu');
  var openFilters = document.getElementById('openFilters');
  var phone = window.matchMedia('(max-width: 47.99em)');

  // ---- plural forms prepared by the server: [one, few, many] (RU) or [one, other] (EN)
  function pluralIndex(n) {
    if (lang === 'ru') return n % 10 === 1 && n % 100 !== 11 ? 0 : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 1 : 2;
    return n === 1 ? 0 : 1;
  }
  function plural(forms, n) { return fill(forms[pluralIndex(n)], { n: n }); }
  function fill(template, values) {
    return template.replace(/%\((\w+)\)s/g, function (all, key) { return key in values ? values[key] : all; });
  }
  function norm(text) {
    return (text || '').toLowerCase().replace(/ё/g, 'е').normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  // ---- data per tile
  var data = tiles.map(function (li) {
    return {
      li: li, order: +li.dataset.order, name: li.dataset.name, search: norm(li.dataset.search),
      sure: li.dataset.sure, kind: li.dataset.kind,
      media: (li.dataset.media || '').split(' ').filter(Boolean),
      missing: (li.dataset.missing || '').split(' ').filter(Boolean)
    };
  });

  // ---- state
  var state = { q: '', sure: [], kind: [], media: [], missing: [], sort: 'number', view: 'cards' };

  function readUrl() {
    var params = new URLSearchParams(location.search);
    function list(name) { return (params.get(name) || '').toLowerCase().split(',').filter(Boolean); }
    state.q = params.get('q') || '';
    state.sure = list('sure');
    state.kind = list('kind');
    state.media = list('media').filter(function (m) { return m === 'photos' || m === 'cover'; });
    state.missing = list('missing');
    // Old links: ?confidence=A&location=unlocated|mapped
    list('confidence').forEach(function (c) { if (state.sure.indexOf(c) < 0) state.sure.push(c); });
    var location_ = list('location');
    if (location_.indexOf('unlocated') >= 0 && state.sure.indexOf('u') < 0) state.sure.push('u');
    if (location_.indexOf('mapped') >= 0 && !state.sure.length) state.sure = ['a', 'b', 'c'];
    state.sort = ['number', 'name', 'confidence'].indexOf(params.get('sort')) >= 0 ? params.get('sort') : 'number';
    state.view = params.get('view') === 'compact' ? 'compact' : 'cards';
    // Keep only values that exist on the page.
    GROUPS.forEach(function (g) {
      var known = inputs.filter(function (i) { return i.name === g; }).map(function (i) { return i.value; });
      state[g] = state[g].filter(function (v, idx, all) { return known.indexOf(v) >= 0 && all.indexOf(v) === idx; });
    });
    var audits = auditChips.map(function (c) { return c.dataset.audit; });
    state.missing = state.missing.filter(function (v) { return audits.indexOf(v) >= 0; });
  }

  function writeUrl() {
    var params = new URLSearchParams(location.search);
    ['q', 'sure', 'kind', 'media', 'missing', 'sort', 'view', 'confidence', 'location'].forEach(function (k) { params.delete(k); });
    if (state.q) params.set('q', state.q);
    GROUPS.concat('missing').forEach(function (g) { if (state[g].length) params.set(g, state[g].join(',')); });
    if (state.sort !== 'number') params.set('sort', state.sort);
    if (state.view !== 'cards') params.set('view', state.view);
    var query = params.toString().replace(/%2C/g, ',');
    var url = location.pathname + (query ? '?' + query : '') + location.hash;
    if (url !== location.pathname + location.search + location.hash) history.replaceState(history.state, '', url);
  }

  // ---- matching
  function matches(d, skip) {
    if (state.q) {
      var words = norm(state.q).split(/\s+/).filter(Boolean);
      for (var i = 0; i < words.length; i++) if (d.search.indexOf(words[i]) < 0) return false;
    }
    if (skip !== 'sure' && state.sure.length && state.sure.indexOf(d.sure) < 0) return false;
    if (skip !== 'kind' && state.kind.length && state.kind.indexOf(d.kind) < 0) return false;
    if (skip !== 'media' && state.media.length && !state.media.some(function (m) { return d.media.indexOf(m) >= 0; })) return false;
    if (skip !== 'missing' && state.missing.length && !state.missing.some(function (m) { return d.missing.indexOf(m) >= 0; })) return false;
    return true;
  }
  function has(d, group, value) {
    return group === 'sure' ? d.sure === value : group === 'kind' ? d.kind === value
      : (group === 'media' ? d.media : d.missing).indexOf(value) >= 0;
  }

  function activeCount() {
    return state.sure.length + state.kind.length + state.media.length + state.missing.length;
  }
  function labelOf(group, value) {
    var input = inputs.filter(function (i) { return i.name === group && i.value === value; })[0];
    if (input) return input.closest('.filter-opt').querySelector('.filter-opt__label').textContent;
    var chip = auditChips.filter(function (c) { return c.dataset.audit === value; })[0];
    return chip ? chip.firstChild.textContent.trim() : value;
  }

  // ---- render
  function render() {
    var shown = 0;
    data.forEach(function (d) {
      var ok = matches(d);
      d.li.hidden = !ok;
      if (ok) shown++;
    });
    // Faceted counts: how many places each option would hold, given the other groups.
    inputs.forEach(function (input) {
      var group = input.name, value = input.value;
      var n = data.filter(function (d) { return matches(d, group) && has(d, group, value); }).length;
      input.checked = state[group].indexOf(value) >= 0;
      input.disabled = !n && !input.checked;
      input.closest('.filter-opt').querySelector('[data-count]').textContent = n;
    });
    auditChips.forEach(function (chip) {
      var value = chip.dataset.audit;
      chip.setAttribute('aria-pressed', String(state.missing.indexOf(value) >= 0));
      chip.querySelector('.chip__count').textContent =
        data.filter(function (d) { return matches(d, 'missing') && has(d, 'missing', value); }).length;
    });
    var filtered = shown !== total || activeCount() || state.q;
    status.textContent = filtered && shown !== total
      ? fill(T.of_total[pluralIndex(total)], { n: shown, total: total })
      : plural(T.places, total);
    renderChips();
    var any = activeCount() > 0 || !!state.q;
    document.querySelectorAll('[data-clear]').forEach(function (b) {
      if (b.closest('#placesEmpty')) return;
      if (b.classList.contains('index-results__clear')) b.hidden = !activeCount(); else b.disabled = !any;
    });
    // Empty state
    empty.hidden = shown > 0;
    if (!shown) {
      var text = '';
      if (state.q && state.kind.length === 1) text = fill(T.empty_in_kind, { q: state.q, kind: labelOf('kind', state.kind[0]) });
      else if (state.q) text = fill(T.empty_query, { q: state.q });
      empty.querySelector('[data-empty-text]').textContent = text;
      empty.querySelector('[data-empty-text]').hidden = !text;
      empty.querySelector('[data-drop-kind]').hidden = !(state.q && state.kind.length);
    }
    // Phone: the Filters button and the sheet's "Show N places"
    var n = activeCount();
    var badge = openFilters && openFilters.querySelector('[data-filter-count]');
    if (badge) {
      badge.hidden = !n;
      badge.textContent = n;
      openFilters.classList.toggle('btn--primary', n > 0);
      openFilters.classList.toggle('btn--quiet', !n);
      openFilters.setAttribute('aria-label', n ? fill(T.filters_n, { n: n }) : T.filters);
    }
    var show = aside.querySelector('[data-show-count]');
    if (show) show.textContent = plural(T.show, shown);
    sortAndView();
    writeUrl();
  }

  function renderChips() {
    chips.textContent = '';
    GROUPS.concat('missing').forEach(function (group) {
      state[group].forEach(function (value) {
        var label = labelOf(group, value);
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'chip chip--set';
        b.setAttribute('aria-label', fill(T.remove, { name: label }));
        b.innerHTML = '<span></span>' + T.close_icon;
        b.firstChild.textContent = label;
        b.addEventListener('click', function () {
          toggle(group, value, false);
          (chips.querySelector('.chip') || status).focus();
        });
        chips.appendChild(b);
      });
    });
  }

  var currentOrder = '';
  function sortAndView() {
    var key = state.sort + (state.sort === 'name' ? lang : '');
    if (key !== currentOrder) {
      currentOrder = key;
      var sorted = data.slice().sort(function (a, b) {
        if (state.sort === 'name') return a.name.localeCompare(b.name, lang) || a.order - b.order;
        if (state.sort === 'confidence') return a.sure.localeCompare(b.sure) || a.order - b.order;
        return a.order - b.order;
      });
      sorted.forEach(function (d) { list.appendChild(d.li); });
    }
    list.classList.toggle('index-list--compact', state.view === 'compact');
    document.querySelectorAll('[data-view]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.view === state.view)); });
    document.querySelectorAll('[data-sort]').forEach(function (el) {
      var on = el.dataset.sort === state.sort;
      el.setAttribute(el.getAttribute('role') === 'option' ? 'aria-selected' : 'aria-pressed', String(on));
      if (on && el.getAttribute('role') === 'option') sortButton.querySelector('[data-sort-label]').textContent = el.textContent;
    });
  }

  function toggle(group, value, on) {
    var values = state[group];
    var i = values.indexOf(value);
    if (on && i < 0) values.push(value);
    if (!on && i >= 0) values.splice(i, 1);
    render();
  }
  function clearAll() {
    state.q = ''; state.sure = []; state.kind = []; state.media = []; state.missing = [];
    searches.forEach(function (s) { s.value = ''; });
    render();
  }

  // ---- events
  inputs.forEach(function (input) {
    input.addEventListener('change', function () { toggle(input.name, input.value, input.checked); });
  });
  auditChips.forEach(function (chip) {
    chip.addEventListener('click', function () { toggle('missing', chip.dataset.audit, chip.getAttribute('aria-pressed') !== 'true'); });
  });
  var timer;
  searches.forEach(function (search) {
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
  document.querySelectorAll('[data-clear]').forEach(function (b) { b.addEventListener('click', clearAll); });
  empty.querySelector('[data-drop-kind]').addEventListener('click', function () { state.kind = []; render(); });
  document.querySelectorAll('[data-view]').forEach(function (b) {
    b.addEventListener('click', function () { state.view = b.dataset.view; render(); });
  });
  aside.querySelectorAll('.chip[data-sort]').forEach(function (b) {
    b.addEventListener('click', function () { state.sort = b.dataset.sort; render(); });
  });

  // Sort listbox: button opens it, ↑/↓ move, Enter/Space choose, Esc closes.
  var options = Array.prototype.slice.call(sortMenu.querySelectorAll('[role="option"]'));
  function openSort(open) {
    sortMenu.hidden = !open;
    sortButton.setAttribute('aria-expanded', String(open));
    if (open) (options.filter(function (o) { return o.dataset.sort === state.sort; })[0] || options[0]).focus();
  }
  sortButton.addEventListener('click', function () { openSort(sortMenu.hidden); });
  options.forEach(function (option, index) {
    function choose() { state.sort = option.dataset.sort; openSort(false); sortButton.focus(); render(); }
    option.addEventListener('click', choose);
    option.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        options[(index + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length].focus();
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault(); choose();
      } else if (event.key === 'Escape' || event.key === 'Tab') {
        openSort(false); if (event.key === 'Escape') sortButton.focus();
      }
    });
  });
  document.addEventListener('click', function (event) {
    if (!sortMenu.hidden && !sortMenu.contains(event.target) && !sortButton.contains(event.target)) openSort(false);
  });

  // ---- phone filter sheet: a modal dialog over the page; changes apply at once
  var lastFocus = null;
  function focusables() {
    return Array.prototype.slice.call(aside.querySelectorAll('button, input, [href], [tabindex]:not([tabindex="-1"])'))
      .filter(function (el) { return !el.disabled && el.offsetParent !== null; });
  }
  function setSheet(open) {
    aside.classList.toggle('is-sheet-open', open);
    document.documentElement.classList.toggle('has-sheet', open);
    if (open) {
      lastFocus = document.activeElement;
      aside.setAttribute('role', 'dialog');
      aside.setAttribute('aria-modal', 'true');
      aside.setAttribute('aria-labelledby', 'filtersTitle');
      aside.removeAttribute('aria-label');
      openFilters.setAttribute('aria-expanded', 'true');
      (aside.querySelector('[data-close-filters]') || aside).focus();
    } else {
      aside.removeAttribute('role');
      aside.removeAttribute('aria-modal');
      aside.removeAttribute('aria-labelledby');
      aside.setAttribute('aria-label', T.filters);
      openFilters.setAttribute('aria-expanded', 'false');
      if (lastFocus) lastFocus.focus();
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
    var head = aside.querySelector('.index-filters__head'), startY = null;
    head.addEventListener('touchstart', function (e) { startY = e.touches[0].clientY; }, { passive: true });
    head.addEventListener('touchend', function (e) {
      if (startY !== null && e.changedTouches[0].clientY - startY > 60) setSheet(false);
      startY = null;
    });
    // Leaving the phone layout closes the sheet.
    (phone.addEventListener ? phone.addEventListener.bind(phone, 'change') : phone.addListener.bind(phone))(function () {
      if (!phone.matches && aside.classList.contains('is-sheet-open')) setSheet(false);
    });
  }

  readUrl();
  searches.forEach(function (s) { s.value = state.q; });
  render();
}());
