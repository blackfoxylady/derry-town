(function () {
  'use strict';

  // Gallery filters beyond the URL limit. With two filters in the URL the
  // server renders every photo (others hidden) and this script applies the
  // third and further filters in the browser. Such selections never reach the
  // URL: the server serves at most two, so crawlers cannot multiply addresses.
  var LIMIT = 2;
  var data = document.getElementById('gallery-filter');
  var filters = document.querySelector('.filters');
  if (!data || !filters) return;

  var conf = JSON.parse(data.textContent);
  var state = {place: conf.place, character: conf.character, tags: conf.tags.slice(), year: conf.year};
  var local = false; // the selection has diverged from the page URL
  var cards = Array.prototype.slice.call(document.querySelectorAll('.grid .card'));
  var count = filters.querySelector('.count');
  var empty = document.querySelector('.empty');

  function size(s) {
    return (s.place ? 1 : 0) + (s.character ? 1 : 0) + s.tags.length + (s.year ? 1 : 0);
  }

  // Tags toggle (any of); place, character and year hold one value, the active one clears.
  function next(dim, value) {
    var s = {place: state.place, character: state.character, tags: state.tags.slice(), year: state.year};
    if (dim === 'tag') {
      var i = s.tags.indexOf(value);
      if (i < 0) s.tags.push(value); else s.tags.splice(i, 1);
    } else {
      s[dim] = s[dim] === value ? '' : value;
    }
    return s;
  }

  // Same shape as the server's _gallery_url for combinations; a single value
  // gets a permanent redirect to its landing there.
  function url(s) {
    var pairs = [['place', s.place], ['character', s.character],
                 ['tag', s.tags.slice().sort().join(',')], ['year', s.year]];
    var query = pairs.filter(function (p) { return p[1]; }).map(function (p) {
      return p[0] + '=' + encodeURIComponent(p[1]).replace(/%2C/gi, ',').replace(/%3A/gi, ':');
    }).join('&');
    return conf.base + (query ? '?' + query : '');
  }

  function matches(card) {
    var d = card.dataset;
    return (!state.place || d.place === state.place)
      && (!state.character || d.characters.split(' ').indexOf(state.character) >= 0)
      && (!state.tags.length || d.tags.split(' ').some(function (t) { return state.tags.indexOf(t) >= 0; }))
      && (!state.year || d.year === state.year);
  }

  function apply() {
    var shown = 0;
    cards.forEach(function (card) {
      card.hidden = !matches(card);
      if (!card.hidden) shown += 1;
    });
    filters.querySelectorAll('.chip[data-dim]').forEach(function (chip) {
      var dim = chip.dataset.dim, value = chip.dataset.value;
      chip.classList.toggle('on', dim === 'tag' ? state.tags.indexOf(value) >= 0 : state[dim] === value);
    });
    count.textContent = conf.counts[shown];
    if (empty) empty.hidden = shown > 0;
  }

  filters.addEventListener('click', function (event) {
    var chip = event.target.closest('.chip[data-dim]');
    if (!chip) return;
    // While the selection matches the URL, the server links are right.
    if (!local && chip.tagName === 'A') return;
    event.preventDefault();
    var s = next(chip.dataset.dim, chip.dataset.value);
    if (size(s) <= LIMIT) {
      window.location.href = url(s);
      return;
    }
    state = s;
    local = true;
    apply();
  });
})();
