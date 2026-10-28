/* Map page UI (blocks 09-10): the place list with search and sort, the place card with its
   pager, the search pill and the notice for an unlocated place, the address and focus. map.js owns the map and the
   data; it hands them over through window.DerryMapUI(ctx) once the payload has loaded. */
(function () {
'use strict';
window.DerryMapUI = function (ctx) {
 const {state, all, photos, placeUrl, photoUrl, galleryUrl, hits, kindShort, confMeta, _, n_} = ctx;
 const sub = (text, values) => text.replace(/%\((\w+)\)s|%s/g, (m, k) => String(k ? values[k] : values.n));
 const q = s => document.querySelector(s);
 const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
 const T = JSON.parse(q('#map-terms').textContent);
 const tpl = q('#glyphs').content;
 const glyph = letter => tpl.querySelector(`[data-glyph="${letter}"]`).outerHTML;
 const icon = name => tpl.querySelector(`[data-icon="${name}"]`).innerHTML;
 const browse = q('#browse'), listEl = q('#list'), card = q('#detail'), notice = q('#mapNotice');
 const phone = matchMedia('(max-width:63.99em)'), sheet = q('#index');
 // Sort orders: map number (1…84, then U1…U8), name, confidence (A, B, C, U, then number).
 const rankOf = s => typeof s.id === 'number' ? s.id : 1000 + Number(s.id.slice(1));
 const SORTS = {
  number: (a, b) => rankOf(a) - rankOf(b),
  name: (a, b) => a.name.localeCompare(b.name, document.documentElement.lang),
  confidence: (a, b) => 'ABCU'.indexOf(a.confidence) - 'ABCU'.indexOf(b.confidence) || rankOf(a) - rankOf(b),
 };
 const sorted = () => all.slice().sort(Object.hasOwn(SORTS, state.sort) ? SORTS[state.sort] : SORTS.number);
 // The list shows what passes the search and the filters, in the chosen order; the pager walks
 // the same list (all places when the selected one is filtered out).
 const shown = () => sorted().filter(hits);
 const pagerSeq = () => { const seq = shown(); return seq.some(p => p.id === state.selected) ? seq : sorted(); };
 const label = s => typeof s.id === 'number' ? String(s.id).padStart(2, '0') : s.id;
 const numClass = s => s.confidence === 'U' ? 'num num--u' : `num num--${s.confidence.toLowerCase()} num--${s.kind.toLowerCase()}`;
 // "Homes · 1957–58 · named in the novel": inferred and proposed in pencil blue; U has no kind.
 function metaLine(s) {
  const conf = s.confidence === 'B' || s.confidence === 'C' ? `<span class="pencil-word">${esc(confMeta[s.confidence])}</span>` : esc(confMeta[s.confidence]);
  return [s.confidence === 'U' ? '' : esc(kindShort[s.kind] || s.kind), esc(s.period), conf].filter(Boolean).join(' · ');
 }

 // ---- List ---------------------------------------------------------------------------
 const search = q('#search'), clear = q('#clearSearch'), peekText = q('.index-peek .t-meta'), peekDefault = peekText.textContent;
 const mark = (text, i, n) => esc(text.slice(0, i)) + '<mark>' + esc(text.slice(i, i + n)) + '</mark>' + esc(text.slice(i + n));
 // A search result: the name with the match marked, else a snippet of the note (or an alias)
 // around the match, cut at word boundaries.
 function result(s) {
  const qn = state.search, at = t => ctx.norm(t).indexOf(qn);
  if (/^\d{1,2}$/.test(qn)) return {title: esc(s.name), snip: ''};
  if (at(s.name) >= 0) return {title: mark(s.name, at(s.name), qn.length), snip: ''};
  const src = [s.note, ...(s.search_aliases || [])].find(t => t && at(t) >= 0);
  if (!src) return {title: esc(s.name), snip: ''};
  const i = at(src); let a = Math.max(0, i - 40), b = Math.min(src.length, i + qn.length + 70);
  if (a > 0) a = Math.min(i, src.indexOf(' ', a) + 1 || a);
  if (b < src.length) b = Math.max(i + qn.length, src.lastIndexOf(' ', b));
  const part = src.slice(a, b).replace(b < src.length ? /[.,;:]+$/ : /$^/, '');
  return {title: esc(s.name), snip: (a > 0 ? '…' : '') + mark(part, i - a, qn.length) + (b < src.length ? '…' : '')};
 }
 function row(s) {
  const r = state.search ? result(s) : {title: esc(s.name), snip: ''};
  return `<li><button type="button" class="place-row${state.search ? ' place-row--result' : ''}" data-place="${s.id}"${state.selected === s.id ? ' aria-current="true"' : ''}><span class="${numClass(s)}">${label(s)}</span><span class="place-row__body"><span class="place-row__title">${r.title}</span>${r.snip ? `<span class="place-row__snip">${r.snip}</span>` : ''}<span class="place-row__meta">${metaLine(s)}</span></span></button></li>`;
 }
 function list() {
  const result = shown(), n = result.length, count = q('#count'), zoomTo = q('#zoomTo');
  // Search results hidden by the filters are counted, with a way back to them.
  const hidden = state.search ? all.filter(s => ctx.searchOk(s) && !ctx.filterOk(s)).length : 0;
  count.classList.toggle('is-results', !!state.search);
  q('#sort').hidden = !!state.search;
  q('#listAll').hidden = state.list !== 'unlocated';
  if (state.search) {
   count.textContent = sub(n_('%s place matches', '%s places match', n), {n});
   const mapped = result.filter(s => typeof s.id === 'number').length;
   zoomTo.hidden = !mapped;
   zoomTo.querySelector('span').textContent = mapped === 1 ? _('Zoom to the place') : sub(n_('Zoom to %s place', 'Zoom to %s places', mapped), {n: mapped});
  } else {
   count.textContent = sub(n_('%s place', '%s places', n), {n});
   zoomTo.hidden = true;
  }
  peekText.textContent = state.search ? sub(n_('%s place', '%s places', n), {n}) : peekDefault;
  const note = hidden ? `<li class="list-note">${esc(sub(n_('%s more hidden by filters', '%s more hidden by filters', hidden), {n: hidden}))} · <button type="button" class="link" data-show-hidden>${esc(_('Show them'))}</button></li>` : '';
  // All three kinds switched off in the key: nothing to list, one way back.
  if (state.hide.size === 3 && state.list !== 'unlocated') { count.textContent = sub(n_('%s place', '%s places', 0), {n: 0}); listEl.innerHTML = `<li class="list-empty"><p>${esc(_('All marks are hidden.'))}</p><button type="button" class="btn btn--secondary btn--compact" data-show-all>${esc(_('Show all'))}</button></li>`; return; }
  listEl.innerHTML = n ? result.map(row).join('') + note
   : state.search ? note || `<li class="list-empty"><h3>${esc(sub(_('Nothing in Derry matches “%s”'), {n: search.value.trim()}))}</h3><p>${esc(_('Try a different search.'))}</p><button type="button" class="btn btn--secondary btn--compact" data-clear-search>${esc(_('Clear search'))}</button></li>`
   : '<li class="empty">' + esc(_('No matching places. Try a shorter name or enable more categories.')) + '</li>';
 }
 // One pass after any change: the list, the map, the pill over it and the address.
 function apply() { list(); controls(); ctx.render(); pill(); syncURL(); if (!card.hidden) cardNav(); }
 listEl.addEventListener('click', e => {
  const b = e.target.closest('.place-row');
  if (b) ctx.select(/^U/.test(b.dataset.place) ? b.dataset.place : Number(b.dataset.place), {zoom: true, opener: {row: b.dataset.place}});
  else if (e.target.closest('[data-show-hidden]')) { ctx.resetFilters(); apply(); search.focus(); }
  else if (e.target.closest('[data-clear-search]')) { clearSearch(); search.focus(); }
  else if (e.target.closest('[data-show-all]')) { state.hide.clear(); apply(); (listEl.querySelector('.place-row') || search).focus(); }
 });
 q('#listAll').addEventListener('click', () => { state.list = 'all'; listEl.scrollTop = 0; apply(); search.focus(); });
 // ↑/↓ move through the rows; ↑ from the first goes back to the search field.
 listEl.addEventListener('keydown', e => {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  const rows = [...listEl.querySelectorAll('.place-row')], i = rows.indexOf(document.activeElement);
  if (i < 0) return;
  e.preventDefault();
  (e.key === 'ArrowDown' ? rows[i + 1] : rows[i - 1] || search)?.focus();
 });
 function markCurrent() {
  listEl.querySelectorAll('.place-row').forEach(b => {
   if (b.dataset.place === String(state.selected)) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
  });
 }
 // A hovered marker lights its row.
 function hot(id) {
  listEl.querySelectorAll('.place-row.is-hot').forEach(b => b.classList.remove('is-hot'));
  if (id != null) listEl.querySelector(`.place-row[data-place="${id}"]`)?.classList.add('is-hot');
 }
 q('#zoomTo').addEventListener('click', () => { if (phone.matches) setSheet('peek'); ctx.zoomToPlaces(shown()); });

 // ---- Search ---------------------------------------------------------------------------
 // From the 2nd character (a number from the 1st), 150 ms after typing stops. Typing never
 // moves the map; every way of clearing (×, Esc, the pill) leaves it where it is.
 let timer = 0;
 function readQuery() { const n = ctx.norm(search.value.trim()); state.search = n.length >= 2 || /^\d/.test(n) ? n : ''; }
 function fieldState() { clear.hidden = !search.value; search.parentElement.classList.toggle('search--filled', !!search.value); }
 search.addEventListener('input', () => {
  fieldState(); clearTimeout(timer);
  timer = setTimeout(() => {
   const was = state.search; readQuery();
   if (state.search === was) return;
   listEl.scrollTop = 0; apply();
   if (state.search && sheet.dataset.sheet === 'peek') setSheet('half');
   else if (!state.search && sheet.dataset.sheet === 'half') setSheet('peek');
  }, 150);
 });
 search.addEventListener('keydown', e => {
  if (e.key === 'Escape' && search.value) { e.preventDefault(); clearSearch(); }
  else if (e.key === 'ArrowDown') { const first = listEl.querySelector('.place-row'); if (first) { e.preventDefault(); first.focus(); } }
 });
 clear.addEventListener('click', () => { clearSearch(); search.focus(); });
 function clearSearch() {
  clearTimeout(timer); search.value = ''; fieldState(); state.search = ''; apply();
  if (sheet.dataset.sheet === 'half') setSheet('peek');
 }
 // The pill over the map: "Showing 3 results for “library” · Clear" (phone, with the sheet
 // lowered: "3 results for “library” ×").
 function pill() {
  const el = q('#mapPill'), raw = search.value.trim();
  if (!state.search) { el.replaceChildren(); return; }
  const n = shown().length;
  const text = n ? sub(phone.matches ? n_('%(n)s result for “%(q)s”', '%(n)s results for “%(q)s”', n) : n_('Showing %(n)s result for “%(q)s”', 'Showing %(n)s results for “%(q)s”', n), {n, q: raw})
   : sub(_('No results for “%s”'), {n: raw});
  el.innerHTML = `<div class="map-notice__box"><span>${esc(text)}</span>` + (phone.matches
   ? `<button type="button" class="btn btn--icon btn--compact" aria-label="${esc(_('Clear search: show all places'))}">${icon('close')}</button>`
   : `<button type="button" class="btn btn--compact">${esc(_('Clear'))}</button>`) + '</div>';
  el.querySelector('button').addEventListener('click', () => { clearSearch(); (!card.hidden ? q('#place-title') : phone.matches ? q('#map') : search).focus(); });
 }

 // ---- Sort -----------------------------------------------------------------------------
 // A listbox under "↕ Map number ▾": ↑/↓ move, Enter or a click chooses, Esc cancels, Tab leaves.
 const sortBtn = q('#sortBtn'), sortMenu = q('#sortMenu'), sortOpts = [...sortMenu.querySelectorAll('[data-sort]')];
 const SORT_ARIA = {number: _('Sort places: by map number'), name: _('Sort places: by name'), confidence: _('Sort places: by confidence')};
 function showSort() {
  sortOpts.forEach(o => o.setAttribute('aria-selected', String(o.dataset.sort === state.sort)));
  q('#sortLabel').textContent = sortOpts.find(o => o.dataset.sort === state.sort).textContent;
  sortBtn.setAttribute('aria-label', SORT_ARIA[state.sort]);
 }
 function setSortMenu(open, refocus) {
  sortMenu.hidden = !open; sortBtn.setAttribute('aria-expanded', String(open));
  if (open) sortOpts.find(o => o.dataset.sort === state.sort).focus(); else if (refocus) sortBtn.focus();
 }
 sortBtn.addEventListener('click', () => setSortMenu(sortMenu.hidden));
 sortMenu.addEventListener('click', e => {
  const o = e.target.closest('[data-sort]'); if (!o) return;
  state.sort = o.dataset.sort; showSort(); setSortMenu(false, true); listEl.scrollTop = 0; apply();
 });
 sortMenu.addEventListener('keydown', e => {
  const i = sortOpts.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); sortOpts[(i + (e.key === 'ArrowDown' ? 1 : sortOpts.length - 1)) % sortOpts.length].focus(); }
  else if (e.key === 'Escape') { e.preventDefault(); setSortMenu(false, true); }
  else if (e.key === 'Tab') setSortMenu(false);
 });
 document.addEventListener('click', e => { if (!sortMenu.hidden && !q('#sort').contains(e.target)) setSortMenu(false); });

 // ---- Filters: Category, With photos and the key ----------------------------------------
 // Each control counts what the rest of the selection leaves (search included), itself aside.
 const catBtn = q('#catBtn'), catMenu = q('#catMenu'), catOpts = q('#catOpts'), scrim = q('#menuScrim');
 const photosBtn = q('#photosBtn'), key = q('#mapKey'), keyTip = q('#keyTip');
 catOpts.innerHTML = ctx.kinds.map(k => `<button type="button" class="menu__opt cat--${k.toLowerCase()}" role="menuitemcheckbox" aria-checked="true" data-kind="${k}" tabindex="-1"><span class="menu__box">${icon('check')}</span><span class="menu__swatch" aria-hidden="true"></span>${esc(ctx.kindLabels[k] || k)}<span class="menu__count"></span></button>`).join('');
 const catItems = [...catOpts.querySelectorAll('[data-kind]')];
 // On the phone the Category sheet keeps a draft until "Show N places".
 let draft = null;
 const chosen = () => draft || state.active;
 const count = test => all.filter(s => ctx.searchOk(s) && test(s)).length;
 function controls() {
  catItems.forEach(b => {
   b.setAttribute('aria-checked', String(chosen().has(b.dataset.kind)));
   b.querySelector('.menu__count').textContent = count(s => s.kind === b.dataset.kind && ctx.filterOk(s, 'kind'));
  });
  const n = state.active.size, total = ctx.kinds.length, cc = q('#catCount');
  catBtn.classList.toggle('chip--set', n < total);
  cc.hidden = n === total; cc.textContent = sub(_('%(n)s of %(total)s'), {n, total});
  if (draft) {
   const keep = state.active; state.active = draft; const m = all.filter(hits).length; state.active = keep;
   const go = catMenu.querySelector('[data-cat-apply]');
   go.textContent = sub(n_('Show %s place', 'Show %s places', m), {n: m}); go.disabled = !m;
  }
  photosBtn.setAttribute('aria-pressed', String(state.withPhotos));
  q('#photosCount').textContent = count(s => photos[String(s.id)] && ctx.filterOk(s, 'photos'));
  document.querySelectorAll('.key [data-hide]').forEach(b => {
   const L = b.dataset.hide, off = state.hide.has(L), n = count(s => s.confidence === L && ctx.filterOk(s, 'hide'));
   b.setAttribute('aria-pressed', String(!off)); b.querySelector('.key__count').textContent = n;
   b.disabled = !n && !off;
  });
  const nu = count(s => s.confidence === 'U' && ctx.filterOk(s));
  document.querySelectorAll('.key [data-list]').forEach(u => {
   u.querySelector('.key__count').textContent = nu; u.disabled = !nu;
   u.setAttribute('aria-label', sub(n_('No location: show the %s place without a point in the list', 'No location: show the %s places without a point in the list', nu), {n: nu}));
  });
 }
 // Category: a checklist under the chip (↑/↓, Space, Esc, Tab leaves); a modal bottom sheet on the phone.
 function setCat(open, refocus) {
  const asSheet = open && phone.matches;
  catMenu.hidden = !open; catBtn.setAttribute('aria-expanded', String(open));
  catMenu.classList.toggle('is-sheet', asSheet); scrim.hidden = !asSheet;
  catMenu.setAttribute('role', asSheet ? 'dialog' : 'group');
  if (asSheet) catMenu.setAttribute('aria-modal', 'true'); else catMenu.removeAttribute('aria-modal');
  draft = asSheet ? new Set(state.active) : null;
  controls();
  if (open) catItems[0].focus(); else if (refocus) catBtn.focus();
 }
 const changed = () => { if (draft) controls(); else apply(); };
 catBtn.addEventListener('click', () => setCat(catMenu.hidden));
 catOpts.addEventListener('click', e => {
  const b = e.target.closest('[data-kind]'); if (!b) return;
  const set = chosen(); if (set.has(b.dataset.kind)) set.delete(b.dataset.kind); else set.add(b.dataset.kind);
  changed();
 });
 catMenu.querySelector('[data-cat-all]').addEventListener('click', () => { ctx.kinds.forEach(k => chosen().add(k)); changed(); });
 catMenu.querySelector('[data-cat-none]').addEventListener('click', () => { chosen().clear(); changed(); });
 catMenu.querySelector('[data-cat-apply]').addEventListener('click', () => { state.active = draft; setCat(false, true); apply(); });
 catMenu.querySelector('[data-cat-close]').addEventListener('click', () => setCat(false, true));
 scrim.addEventListener('click', () => setCat(false, true));
 catMenu.addEventListener('keydown', e => {
  const i = catItems.indexOf(document.activeElement);
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && i >= 0) { e.preventDefault(); catItems[(i + (e.key === 'ArrowDown' ? 1 : catItems.length - 1)) % catItems.length].focus(); }
  else if (e.key === 'Escape') { e.preventDefault(); setCat(false, true); }
 });
 document.addEventListener('keydown', e => {
  if (!draft || catMenu.hidden || e.key !== 'Tab') return;
  const items = [...catMenu.querySelectorAll('button:not([disabled]):not([tabindex="-1"]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter(el => el.offsetParent !== null);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (!catMenu.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
  else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
 });
 catMenu.addEventListener('focusout', e => { if (!draft && !catMenu.hidden && !catMenu.contains(e.relatedTarget) && e.relatedTarget !== catBtn) setCat(false); });
 document.addEventListener('click', e => { if (!catMenu.hidden && !draft && !q('.cat').contains(e.target)) setCat(false); });
 photosBtn.addEventListener('click', () => { state.withPhotos = !state.withPhotos; apply(); });
 // The key: A, B, C toggle those pins on the map and in the list; "No location →" lists the
 // places without a point (the map does not change).
 document.querySelectorAll('.key').forEach(k => k.addEventListener('click', e => {
  const b = e.target.closest('.key__item'); if (!b || b.disabled) return;
  if (b.dataset.list) {
   if (!card.hidden) { beforeCard = 'full'; ctx.close(); }
   state.list = 'unlocated'; listEl.scrollTop = 0; apply(); if (phone.matches) setSheet('full'); return;
  }
  const L = b.dataset.hide; if (state.hide.has(L)) state.hide.delete(L); else state.hide.add(L);
  apply(); if (k === key) tipText(b);
 }));
 // Tooltip after 0.4 s on hover or focus; the text is there at once for screen readers.
 let tipTimer = 0;
 function tipText(b) {
  const L = b.dataset.hide, lv = T.levels[L];
  keyTip.innerHTML = `<b>${esc(lv.label)} · ${L}</b> — ${esc(lv.explanation)} ${esc(state.hide.has(L) ? _('Press to show these pins.') : _('Press to hide these pins.'))}`;
 }
 function showTip(b) {
  tipText(b); clearTimeout(tipTimer);
  tipTimer = setTimeout(() => { keyTip.style.left = b.offsetLeft + 'px'; keyTip.hidden = false; }, 400);
 }
 function hideTip() { clearTimeout(tipTimer); keyTip.hidden = true; }
 key.querySelectorAll('[data-hide]').forEach(b => {
  b.addEventListener('pointerenter', () => showTip(b)); b.addEventListener('focus', () => showTip(b));
  b.addEventListener('pointerleave', hideTip); b.addEventListener('blur', hideTip);
 });
 document.addEventListener('keydown', e => { if (e.key === 'Escape' && !keyTip.hidden) { e.preventDefault(); hideTip(); } });

 // The address carries the view: ?q=library&kind=civic,homes&photos=1&hide=C&sort=name&place=12
 // &list=unlocated (defaults left out).
 const P = new URLSearchParams(location.search);
 if (Object.hasOwn(SORTS, P.get('sort') || '')) state.sort = P.get('sort');
 if (P.has('kind')) {
  const want = P.get('kind').toLowerCase().split(','), kinds = ctx.kinds.filter(k => want.includes(k.toLowerCase()));
  if (kinds.length || want.includes('none')) state.active = new Set(kinds);
 }
 if (P.get('photos') === '1') state.withPhotos = true;
 if (P.get('hide')) state.hide = new Set(P.get('hide').toUpperCase().split(',').filter(L => ['A', 'B', 'C'].includes(L)));
 if (P.get('list') === 'unlocated') state.list = 'unlocated';
 if (P.get('q')) { search.value = P.get('q'); fieldState(); readQuery(); }
 showSort();

 // ---- Card -----------------------------------------------------------------------------
 // The nav row is built once, so focus stays on ‹ / › while paging; the body is rebuilt.
 card.innerHTML = `<div class="place-card__nav"><button type="button" class="btn btn--quiet btn--compact place-card__back" data-close>${icon('back')}<span></span></button>`
  + `<div class="place-card__pager"><button type="button" class="btn btn--icon" data-step="-1" aria-label="${esc(_('Previous place'))}">‹</button><span class="t-meta"></span><button type="button" class="btn btn--icon" data-step="1" aria-label="${esc(_('Next place'))}">›</button></div>`
  + `<button type="button" class="btn btn--icon" data-close aria-label="${esc(_('Close place'))}">${icon('close')}</button></div>`
  + '<div class="place-card__body"></div><div class="place-card__foot"></div><span class="visually-hidden" aria-live="polite" data-live></span>';
 const body = card.querySelector('.place-card__body'), foot = card.querySelector('.place-card__foot');
 const pos = card.querySelector('.place-card__pager .t-meta'), steps = card.querySelectorAll('[data-step]');
 card.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => ctx.close()));
 steps.forEach(b => b.addEventListener('click', () => {
  const seq = pagerSeq(), next = seq[seq.findIndex(s => s.id === state.selected) + Number(b.dataset.step)];
  if (next) ctx.select(next.id, {zoom: true, paging: true});
 }));
 let opener = null, listScroll = 0, beforeCard = 'peek';

 function cardBody(s) {
  const L = s.confidence, lv = T.levels[L], fp = photos[String(s.id)];
  const kind = L === 'U' ? '' : `<span class="eyebrow eyebrow--cat cat--${s.kind.toLowerCase()}">${esc(kindShort[s.kind] || s.kind)}</span><span class="place-meta__sep" aria-hidden="true">·</span>`;
  const head = `<div class="place-card__head"><div class="place-meta"><span class="${numClass(s)}" aria-hidden="true">${label(s)}</span>${kind}`
   + `<span class="place-meta__tipwrap"><button type="button" class="place-meta__conf" aria-expanded="false" aria-controls="conf-tip">${glyph(L)}<span class="eyebrow">${esc(lv.label)}</span><span class="place-meta__info">${icon('info')}</span></button>`
   + `<span class="key__tip place-meta__tip" id="conf-tip" role="status" hidden><b>${esc(lv.label)} · ${L}</b> — ${esc(lv.explanation)} <a href="${esc(T.method)}">${esc(T.how)}</a></span></span></div>`
   + `<h2 class="place-card__title" id="place-title" tabindex="-1"><span class="visually-hidden">${esc(_('Place %s:').replace('%s', label(s)))} </span>${esc(s.name)}</h2>`
   + (s.period ? `<span class="place-when">${esc(s.period)}</span>` : '') + '</div>';
  const unlocated = L === 'U' ? `<p class="place-card__unlocated">${esc(_('No point on the map: the novel doesn’t say where it stands.'))}</p>` : '';
  // Up to two polaroids, captioned with the year; the rest are behind the gallery link.
  const pics = fp ? `<div class="card-photos">${fp.photos.slice(0, 2).map(p => `<a class="card-photo" href="${esc(photoUrl(p.id))}"><img src="${esc(p.thumb)}" alt="${esc(p.caption || s.name)}" loading="lazy"><span class="card-photo__cap" aria-hidden="true">${p.year || ''}</span></a>`).join('')}</div>`
   + `<p class="place-card__more"><a class="link link--arrow" href="${esc(fp.gallery || galleryUrl + '?place=' + s.id)}">${esc(_('All photos of this place'))}</a></p>` : '';
  const refs = (s.refs || []).length ? `<details class="card-sec"${phone.matches ? '' : ' open'}><summary>${esc(_('In the novel'))}<small>${esc(n_('%s chapter', '%s chapters', s.chapters).replace('%s', s.chapters))}</small></summary><ol class="refs">`
   + s.refs.map(([ch, title, part]) => `<li><span class="refs__ch">${esc(ch)}<span class="visually-hidden"> · </span></span><span>${esc(title)}</span>${part ? `<span class="refs__part"><span class="visually-hidden"> · </span>§${esc(part)}</span>` : ''}</li>`).join('') + '</ol></details>' : '';
  return head + unlocated + pics + (s.note ? `<p class="place-card__note">${esc(s.note)}</p>` : '') + refs;
 }

 function open(s, opts = {}) {
  const wasOpen = !card.hidden;
  if (!wasOpen) {
   listScroll = listEl.scrollTop;
  }
  // A new opener (another row or marker picked while the card is open) replaces the old one;
  // paging keeps it.
  if (!wasOpen || opts.opener) opener = opts.opener || null;
  body.innerHTML = cardBody(s);
  // The place page opens in a new tab, so the map keeps its view and card (Dina, 28.10).
  foot.innerHTML = `<a class="btn btn--primary" href="${esc(placeUrl(s))}" target="_blank" rel="noopener">${esc(_('Open place page'))}<span class="visually-hidden"> ${esc(_('(opens in a new tab)'))}</span></a>`;
  cardNav();
  body.scrollTop = 0;
  if (!wasOpen) beforeCard = sheet.dataset.sheet === 'card' ? 'peek' : sheet.dataset.sheet;
  browse.hidden = true; card.hidden = false; setSheet('card');
  toggletip(body.querySelector('.place-meta__conf'));
  showNotice(s.confidence === 'U' ? s : null);
  markCurrent(); syncURL();
  if (opts.paging) card.querySelector('[data-live]').textContent = s.name;
  else if (opts.focus !== false) card.querySelector('#place-title').focus();
 }

 // The nav row: "← Back to results" after a search, the pager over the current list.
 function cardNav() {
  card.querySelector('.place-card__back span').textContent = state.search ? _('Back to results') : _('All places');
  const seq = pagerSeq(), i = seq.findIndex(p => p.id === state.selected);
  pos.textContent = `${i + 1} / ${seq.length}`;
  const focused = document.activeElement;
  steps[0].disabled = i <= 0; steps[1].disabled = i === seq.length - 1;
  // A pager arrow that just went disabled hands focus to the other one.
  if (focused?.disabled) steps[focused === steps[0] ? 1 : 0].focus();
 }

 function close() {
  card.hidden = true; browse.hidden = false; setSheet(beforeCard); listEl.scrollTop = listScroll;
  showNotice(null); markCurrent(); syncURL();
  // Focus goes back to what opened the card: the row, else the marker, else the map.
  const o = opener; opener = null;
  const target = o?.row != null ? listEl.querySelector(`.place-row[data-place="${o.row}"]`) : o?.mk != null ? q(`#markers .mk[data-id="${o.mk}"]`) : null;
  return target;
 }

 // ⓘ toggletip: click or Enter opens, Esc or a click elsewhere closes; focus stays on the button.
 let tipButton = null;
 function toggletip(button) {
  tipButton = button;
  const tip = q('#conf-tip');
  button.addEventListener('click', () => setTip(button.getAttribute('aria-expanded') !== 'true'));
  function setTip(on) { button.setAttribute('aria-expanded', String(on)); tip.hidden = !on; }
  button._set = setTip;
 }
 document.addEventListener('click', e => {
  if (tipButton?.getAttribute('aria-expanded') === 'true' && !tipButton.parentElement.contains(e.target)) tipButton._set(false);
 });
 function closeTip() {
  if (tipButton?.isConnected && tipButton.getAttribute('aria-expanded') === 'true') { tipButton._set(false); tipButton.focus(); return true; }
  return false;
 }

 // Unlocated place: the map does not move; a dark notice says why there is nothing to show.
 function showNotice(s) {
  if (!s) { notice.replaceChildren(); return; }
  notice.innerHTML = `<div class="map-notice__box">${glyph('U')}<span>${esc(_('%s has no point on the map: the novel doesn’t say where it stands').replace('%s', s.name))}</span><button type="button" class="btn btn--compact">${esc(_('Close'))}</button></div>`;
  notice.querySelector('button').addEventListener('click', () => { q('#place-title')?.focus(); notice.replaceChildren(); });
 }

 // The address follows the view with replaceState, so Back from a place page lands on the same
 // list or card; the language switch keeps it too.
 function syncURL() {
  const put = u => {
   const p = u.searchParams, set = (k, v) => { if (v) p.set(k, v); else p.delete(k); };
   const kinds = state.active.size === ctx.kinds.length ? '' : ctx.kinds.filter(k => state.active.has(k)).map(k => k.toLowerCase()).join(',') || 'none';
   set('q', state.search ? search.value.trim() : ''); set('kind', kinds); set('photos', state.withPhotos ? '1' : '');
   set('hide', [...state.hide].sort().join(',')); set('sort', state.sort !== 'number' ? state.sort : '');
   set('place', state.selected ?? ''); set('list', state.list === 'unlocated' ? 'unlocated' : '');
   return u.pathname + u.search.replace(/%2C/g, ',') + u.hash;
  };
  history.replaceState(history.state, '', put(new URL(location.href)));
  document.querySelectorAll('.lang a').forEach(a => { a.href = put(new URL(a.href, location.href)); });
 }

 // ---- Phone sheet (< 1024 px) ------------------------------------------------------------
 // The panel is a bottom sheet over the map: peek (search, counts, "List ↑"), half (search
 // results), full (the list, with a "Show map" pill) and card. The grabber drags between them;
 // × on the card returns to where the sheet was. --sheet-h keeps the scale, key and cookie
 // notice above it.
 function setSheet(pos) {
  sheet.dataset.sheet = document.documentElement.dataset.sheet = pos;
  q('[data-sheet-to="full"]').setAttribute('aria-expanded', String(pos === 'full'));
  syncHeight();
 }
 function syncHeight() {
  const h = phone.matches ? Math.round(sheet.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty('--sheet-h', h + 'px');
 }
 sheet.addEventListener('transitionend', syncHeight);
 phone.addEventListener('change', syncHeight);
 // "List ↑" and "Show map" swap places, so focus moves to the other one.
 sheet.querySelectorAll('[data-sheet-to]').forEach(b => b.addEventListener('click', () => {
  const to = b.dataset.sheetTo === 'full' && state.search ? 'half' : b.dataset.sheetTo;
  setSheet(to);
  (to === 'full' ? sheet.querySelector('.sheet-pill') : to === 'peek' ? sheet.querySelector('[data-sheet-to="full"]') : listEl.querySelector('.place-row') || search).focus();
 }));
 const grab = sheet.querySelector('.index-grab');
 grab.addEventListener('pointerdown', e => {
  if (!phone.matches) return;
  grab.setPointerCapture(e.pointerId);
  const y0 = e.clientY, h0 = sheet.getBoundingClientRect().height, max = innerHeight - 70;
  let dy = 0;
  sheet.classList.add('is-dragging');
  const move = ev => { dy = ev.clientY - y0; sheet.style.height = Math.max(96, Math.min(max, h0 - dy)) + 'px'; syncHeight(); };
  const up = () => {
   grab.removeEventListener('pointermove', move); grab.removeEventListener('pointerup', up); grab.removeEventListener('pointercancel', up);
   sheet.classList.remove('is-dragging'); sheet.style.height = ''; snap(dy);
  };
  grab.addEventListener('pointermove', move); grab.addEventListener('pointerup', up); grab.addEventListener('pointercancel', up);
 });
 // A drag of 40 px moves one position; a tap toggles peek and the list. Down from peek does
 // nothing; half exists only while searching; the card closes on a firm drag down.
 function snap(dy) {
  const pos = sheet.dataset.sheet;
  if (pos === 'card') { if (dy > 80) ctx.close(); else syncHeight(); return; }
  const stops = state.search ? ['peek', 'half', 'full'] : ['peek', 'full'];
  let i = stops.indexOf(pos); if (i < 0) i = 0;
  if (Math.abs(dy) < 8) i = pos === 'peek' ? stops.length - 1 : 0;
  else if (dy <= -40) i = Math.min(stops.length - 1, i + 1);
  else if (dy >= 40) i = Math.max(0, i - 1);
  setSheet(stops[i]);
 }
 // Screen pixels the card covers at the bottom of the map (phone only): the place is centred above it.
 const cover = () => phone.matches ? Math.round(innerHeight * 0.66) : 0;
 const sheetCover = () => phone.matches ? Math.round(sheet.getBoundingClientRect().height) : 0;
 if (state.list === 'unlocated') setSheet('full'); else if (state.search) setSheet('half');
 requestAnimationFrame(syncHeight);

 return {apply, list, open, close, hot, closeTip, markCurrent, cover, sheetCover};
};
})();
