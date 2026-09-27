(function () {
  'use strict';

  var search = document.getElementById('placeSearch');
  var list = document.getElementById('placesList');
  var catalog = document.getElementById('placesCatalog');
  if (!search || !list || !catalog) return;

  var cards = Array.prototype.slice.call(list.querySelectorAll('.place-card'));
  var total = cards.length;
  var count = document.getElementById('placeResultCount');
  var empty = document.getElementById('placesEmpty');
  var sort = document.getElementById('placeSort');
  var clear = document.getElementById('clearPlaces');
  var params = new URLSearchParams(window.location.search);
  var state = {
    q: params.get('q') || '',
    location: params.get('location') || '',
    confidence: params.get('confidence') || '',
    kind: params.get('kind') || '',
    media: params.get('media') || '',
    audit: params.get('audit') || '',
    sort: params.get('sort') === 'name' ? 'name' : 'number',
    view: params.get('view') === 'compact' ? 'compact' : 'cards'
  };

  function normalized(value) {
    return (value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  }

  cards.forEach(function (card) {
    card._search = normalized(card.dataset.search);
  });

  function mediaMatches(card) {
    var photos = Number(card.dataset.photos);
    var covers = Number(card.dataset.covers);
    if (state.media === 'photos') return photos > 0;
    if (state.media === 'cover') return covers > 0;
    if (state.media === 'none') return photos === 0 && covers === 0;
    return true;
  }

  function auditMatches(card) {
    if (state.audit === 'photos') return Number(card.dataset.photos) === 0;
    if (state.audit === 'cover') return Number(card.dataset.covers) === 0;
    if (state.audit === 'content') return card.dataset.contentComplete === '0';
    if (state.audit === 'ru') return card.dataset.ruComplete === '0';
    if (state.audit === 'sources') return Number(card.dataset.sources) === 0;
    return true;
  }

  function matches(card) {
    var terms = normalized(state.q).split(/\s+/).filter(Boolean);
    return terms.every(function (term) { return card._search.indexOf(term) !== -1; }) &&
      (!state.location || card.dataset.location === state.location) &&
      (!state.confidence || card.dataset.confidence === state.confidence) &&
      (!state.kind || card.dataset.kind === state.kind) &&
      mediaMatches(card) && auditMatches(card);
  }

  function updateUrl() {
    var url = new URL(window.location.href);
    ['q', 'location', 'confidence', 'kind', 'media', 'audit', 'sort', 'view'].forEach(function (key) {
      url.searchParams.delete(key);
    });
    if (state.q) url.searchParams.set('q', state.q);
    ['location', 'confidence', 'kind', 'media', 'audit'].forEach(function (key) {
      if (state[key]) url.searchParams.set(key, state[key]);
    });
    if (state.sort !== 'number') url.searchParams.set('sort', state.sort);
    if (state.view !== 'cards') url.searchParams.set('view', state.view);
    history.replaceState(null, '', url.pathname + url.search + url.hash);
  }

  function syncControls() {
    search.value = state.q;
    sort.value = state.sort;
    document.querySelectorAll('[data-filter-group]').forEach(function (group) {
      var value = state[group.dataset.filterGroup] || '';
      group.querySelectorAll('.chip').forEach(function (button) {
        var on = button.dataset.value === value;
        button.classList.toggle('on', on);
        button.setAttribute('aria-pressed', String(on));
      });
    });
    document.querySelectorAll('.view-switch button').forEach(function (button) {
      var on = button.dataset.view === state.view;
      button.classList.toggle('on', on);
      button.setAttribute('aria-pressed', String(on));
    });
    catalog.classList.toggle('compact', state.view === 'compact');
    var audit = document.querySelector('.audit-filters');
    if (audit && state.audit) audit.open = true;
  }

  function render(writeUrl) {
    cards.sort(function (a, b) {
      if (state.sort === 'name') return a.dataset.name.localeCompare(b.dataset.name, document.documentElement.lang);
      return Number(a.dataset.order) - Number(b.dataset.order);
    }).forEach(function (card) { list.appendChild(card); });

    var visible = 0;
    cards.forEach(function (card) {
      var show = matches(card);
      card.hidden = !show;
      if (show) visible += 1;
    });
    count.innerHTML = '<b>' + visible + '</b> / ' + total;
    empty.hidden = visible !== 0;
    syncControls();
    if (writeUrl) updateUrl();
  }

  search.addEventListener('input', function () {
    state.q = search.value.trim();
    render(true);
  });
  sort.addEventListener('change', function () {
    state.sort = sort.value;
    render(true);
  });
  document.querySelectorAll('[data-filter-group] .chip').forEach(function (button) {
    button.addEventListener('click', function () {
      state[button.closest('[data-filter-group]').dataset.filterGroup] = button.dataset.value;
      render(true);
    });
  });
  document.querySelectorAll('.view-switch button').forEach(function (button) {
    button.addEventListener('click', function () {
      state.view = button.dataset.view;
      render(true);
    });
  });
  clear.addEventListener('click', function () {
    state.q = '';
    state.location = state.confidence = state.kind = state.media = state.audit = '';
    state.sort = 'number';
    state.view = 'cards';
    render(true);
    search.focus();
  });

  render(false);
}());
