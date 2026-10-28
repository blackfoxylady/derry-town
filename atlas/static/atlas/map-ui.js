/* Map page UI (block 09): the place list, the place card with its pager, the notice for an
   unlocated place, ?place in the address and where focus goes. map.js owns the map and the
   data; it hands them over through window.DerryMapUI(ctx) once the payload has loaded. */
(function () {
'use strict';
window.DerryMapUI = function (ctx) {
 const {state, all, photos, placeUrl, photoUrl, galleryUrl, hits, kindShort, confMeta, _, n_} = ctx;
 const q = s => document.querySelector(s);
 const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
 const T = JSON.parse(q('#map-terms').textContent);
 const tpl = q('#glyphs').content;
 const glyph = letter => tpl.querySelector(`[data-glyph="${letter}"]`).outerHTML;
 const icon = name => tpl.querySelector(`[data-icon="${name}"]`).innerHTML;
 const browse = q('#browse'), listEl = q('#list'), card = q('#detail'), notice = q('#mapNotice');
 const phone = matchMedia('(max-width:63.99em)'), sheet = q('#index');
 // The pager walks every place in the list order: 1…84, then U1…U8.
 const rankOf = s => typeof s.id === 'number' ? s.id : 1000 + Number(s.id.slice(1));
 const order = all.slice().sort((a, b) => rankOf(a) - rankOf(b));
 const label = s => typeof s.id === 'number' ? String(s.id).padStart(2, '0') : s.id;
 const numClass = s => s.confidence === 'U' ? 'num num--u' : `num num--${s.confidence.toLowerCase()} num--${s.kind.toLowerCase()}`;
 // "Homes · 1957–58 · named in the novel": inferred and proposed in pencil blue; U has no kind.
 function metaLine(s) {
  const conf = s.confidence === 'B' || s.confidence === 'C' ? `<span class="pencil-word">${esc(confMeta[s.confidence])}</span>` : esc(confMeta[s.confidence]);
  return [s.confidence === 'U' ? '' : esc(kindShort[s.kind] || s.kind), esc(s.period), conf].filter(Boolean).join(' · ');
 }

 // ---- List ---------------------------------------------------------------------------
 function list() {
  const result = order.filter(hits);
  q('#count').textContent = n_('%s place', '%s places', result.length).replace('%s', result.length);
  listEl.innerHTML = result.length ? result.map(s => `<li><button type="button" class="place-row" data-place="${s.id}"${state.selected === s.id ? ' aria-current="true"' : ''}><span class="${numClass(s)}">${label(s)}</span><span class="place-row__body"><span class="place-row__title">${esc(s.name)}</span><span class="place-row__meta">${metaLine(s)}</span></span></button></li>`).join('')
   : '<li class="empty">' + esc(_('No matching places. Try a shorter name or enable more categories.')) + '</li>';
 }
 listEl.addEventListener('click', e => {
  const b = e.target.closest('.place-row');
  if (b) ctx.select(/^U/.test(b.dataset.place) ? b.dataset.place : Number(b.dataset.place), {zoom: true, opener: {row: b.dataset.place}});
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

 // ---- Search and the category stopgap (block 10 replaces both) ------------------------
 const search = q('#search'), clear = q('#clearSearch');
 search.addEventListener('input', () => {
  state.search = search.value.trim().toLowerCase(); clear.hidden = !search.value;
  search.parentElement.classList.toggle('search--filled', !!search.value); list(); ctx.render();
  if (state.search && sheet.dataset.sheet === 'peek') setSheet('half');
  else if (!state.search && sheet.dataset.sheet === 'half') setSheet('peek');
 });
 clear.addEventListener('click', () => { search.value = ''; search.dispatchEvent(new Event('input')); search.focus(); });

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
  const next = order[order.findIndex(s => s.id === state.selected) + Number(b.dataset.step)];
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
  foot.innerHTML = `<a class="btn btn--primary" href="${esc(placeUrl(s))}">${esc(_('Open place page'))}</a>`;
  card.querySelector('.place-card__back span').textContent = state.search ? _('Back to results') : _('All places');
  const i = order.findIndex(p => p.id === s.id);
  pos.textContent = `${i + 1} / ${order.length}`;
  const focused = document.activeElement;
  steps[0].disabled = i === 0; steps[1].disabled = i === order.length - 1;
  // A pager arrow that just went disabled hands focus to the other one.
  if (focused?.disabled) steps[focused === steps[0] ? 1 : 0].focus();
  body.scrollTop = 0;
  if (!wasOpen) beforeCard = sheet.dataset.sheet === 'card' ? 'peek' : sheet.dataset.sheet;
  browse.hidden = true; card.hidden = false; setSheet('card');
  toggletip(body.querySelector('.place-meta__conf'));
  showNotice(s.confidence === 'U' ? s : null);
  markCurrent(); setAddress(s.id);
  if (opts.paging) card.querySelector('[data-live]').textContent = s.name;
  else if (opts.focus !== false) card.querySelector('#place-title').focus();
 }

 function close() {
  card.hidden = true; browse.hidden = false; setSheet(beforeCard); listEl.scrollTop = listScroll;
  showNotice(null); markCurrent(); setAddress(null);
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

 // ?place=N follows the card, so Back from a place page lands on the same card; the
 // language switch keeps it too.
 function setAddress(id) {
  const put = u => { if (id == null) u.searchParams.delete('place'); else u.searchParams.set('place', id); return u.pathname + u.search + u.hash; };
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
  setSheet(b.dataset.sheetTo);
  sheet.querySelector(`[data-sheet-to="${b.dataset.sheetTo === 'full' ? 'peek' : 'full'}"]`).focus();
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
 requestAnimationFrame(syncHeight);

 return {list, open, close, hot, closeTip, markCurrent, cover, sheetCover};
};
})();
