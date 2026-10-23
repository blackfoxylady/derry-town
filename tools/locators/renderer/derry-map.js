/* ==========================================================================
   Derry map: reference renderer v2 (stage 02)
   Vanilla JS + SVG, no dependencies. Draws data/map-geometry.json
   (y already flipped to screen orientation) in one of three styles:
   "survey" (A), "plate" (B), "atlas" (C).

   API
     const map = DerryMap.create(svgElement, geometry, {style, photos, selected})
     map.setView(cx, cy, k)   world centre + scale (screen px per metre)
     map.fit([x0,y0,x1,y1], pad)
     map.select(id)           highlight a place (null clears)
     map.setStyle(name)
     map.screen(x, y)         world → screen

   Technique (kept from the "Lithograph" round):
     - the world is one <g transform="translate scale(k)">;
     - --u = (1/k)px on the <svg>, so `calc(var(--u)*N)` is N screen px;
     - LOD by <svg data-z="far|mid|near">, thresholds k < 0.16 / < 0.42;
       houses by <svg data-bld="tint|plan">: built-up tint below k 0.8, footprints above;
     - markers, labels and photos live in a screen-space overlay that is
       rebuilt on setView (cheap: ~150 nodes).
   Every block below is independent so it can be ported one at a time.
   ========================================================================== */
(function (global) {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';
  const FR = [-6150, -3450, 3450, 4380];           // sheet frame, world metres
  const LOD = { far: 0.16, mid: 0.42, plan: 0.8 };  // k thresholds; plan: house footprints replace the built-up tint
  const ROADS = {                                   // [world width m, min screen px], drawn in this order
    track: [6, 1], trackdash: [6, 1], lane: [6, 1],
    secondary: [13, 1.6], primary: [19, 2.4], main: [24, 2.8], highway: [30, 3.2]
  };
  const STYLE = {                                   // per-style geometry knobs (colours live in CSS)
    survey: { massW: 0,  builtR: 30, frame: 'survey', smooth: true },
    plate:  { massW: 0,  builtR: 0,  frame: 'plate',  smooth: true },
    atlas:  { massW: 16, builtR: 62, frame: 'none',   smooth: true }
  };

  // ---- helpers -------------------------------------------------------------
  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  const r1 = (v) => Math.round(v * 10) / 10;
  function pd(pts, close) {                         // straight polyline
    let s = '';
    for (let i = 0; i < pts.length; i++) s += (i ? 'L' : 'M') + r1(pts[i][0]) + ' ' + r1(pts[i][1]);
    return close ? s + 'Z' : s;
  }
  function sd(pts, close) {                         // Catmull-Rom → cubic, passes through every point
    if (pts.length < 3) return pd(pts, close);
    const P = close ? pts.concat([pts[0], pts[1], pts[2]]) : pts;
    const n = close ? pts.length : P.length - 1;
    let s = 'M' + r1(P[0][0]) + ' ' + r1(P[0][1]);
    for (let i = 0; i < n; i++) {
      const p0 = P[i - 1] || (close ? pts[pts.length - 1] : P[i]), p1 = P[i], p2 = P[i + 1], p3 = P[i + 2] || p2;
      s += 'C' + r1(p1[0] + (p2[0] - p0[0]) / 6) + ' ' + r1(p1[1] + (p2[1] - p0[1]) / 6) + ' ' +
        r1(p2[0] - (p3[0] - p1[0]) / 6) + ' ' + r1(p2[1] - (p3[1] - p1[1]) / 6) + ' ' + r1(p2[0]) + ' ' + r1(p2[1]);
    }
    return close ? s + 'Z' : s;
  }
  const px = (n) => `calc(var(--u)*${n})`;                       // n screen px
  const wpx = (w, min) => `max(${w}px, calc(var(--u)*${min}))`;   // world width, at least min screen px
  const areaClass = (fill) => ({
    '#dce2c7': 'm-park', '#d7cbb5': 'm-yard', '#d5c7a2': 'm-yard', '#c3b18c': 'm-yard',
    '#e7e1bf': 'm-sand', '#e0ddc9': 'm-field', '#d4d4b7': 'm-field'
  }[fill] || 'm-field');
  // Letter-spaced source labels → plain words (letter-spacing is done in CSS):
  // "T H E  B A R R E N S" → "THE BARRENS", "О Л Д - К Е Й П" → "ОЛД-КЕЙП". A label counts as
  // letter-spaced when every single-space token is one character; double spaces mark word breaks.
  const spaced = (t) => (/^\S( {1,2}\S)+$/.test(t) && t.split(/ {2,}/).every((w) => w.split(' ').every((c) => c.length === 1))
    ? t.split(/ {2,}/).map((w) => w.replace(/ /g, '')).join(' ') : t);

  // ---- line ends: nothing long stops in mid-air ------------------------------
  // Ported from production litho.js (extendLines / prepWater) with wider reach.
  // Rivers run out under the frame; roads and rail join the next line or run to
  // the frame edge; a major road that meets water fades out dashed; a rail line
  // with nowhere to go ends in a buffer stop. Brook sources taper (see layer 7).
  function ext(p, atStart, L) {                     // straight run-out along the end tangent
    const a = atStart ? p[0] : p[p.length - 1], b = atStart ? p[Math.min(3, p.length - 1)] : p[Math.max(0, p.length - 4)];
    const dx = a[0] - b[0], dy = a[1] - b[1], n = Math.hypot(dx, dy) || 1, q = [a[0] + dx / n * L, a[1] + dy / n * L];
    return atStart ? [q].concat(p) : p.concat([q]);
  }
  function segDist(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L));
    return Math.hypot(a[0] + t * dx - p[0], a[1] + t * dy - p[1]);
  }
  function rayHit(o, d, segs, maxT) {               // nearest crossing of the ray o + t·d, t in (1, maxT); Infinity if none
    let best = Infinity;
    maxT = maxT || Infinity;
    segs.forEach(([a, b]) => {
      const sx = b[0] - a[0], sy = b[1] - a[1], den = d[0] * sy - d[1] * sx;
      if (Math.abs(den) < 1e-9) return;
      const t = ((a[0] - o[0]) * sy - (a[1] - o[1]) * sx) / den, q = ((a[0] - o[0]) * d[1] - (a[1] - o[1]) * d[0]) / den;
      if (t > 1 && t < maxT && t < best && q >= 0 && q <= 1) best = t;
    });
    return best;
  }
  function prep(geo) {
    const water = geo.water.map((w) => {
      let p = w.p;
      if (w.id === 'penobscot') p = ext(ext(p, true, 1500), false, 3500);
      else if (w.id === 'river' && p[0][0] < -5000) p = ext(p, true, 1500);
      return Object.assign({}, w, { p });
    });
    const valley = geo.valley.map((v) => (v.p[0][0] < -5000 ? Object.assign({}, v, { p: ext(v.p, true, 1500) }) : v));
    const L = geo.roads.map((r) => ({ r, p: r.p.slice(), rail: false })).concat(geo.rail.filter((p) => p.length > 1).map((p) => ({ p: p.slice(), rail: true })));
    const segsOf = (skip, rail) => { const o = []; L.forEach((l) => { if (l !== skip && l.rail === rail) for (let i = 1; i < l.p.length; i++) o.push([l.p[i - 1], l.p[i]]); }); return o; };
    const wseg = [];
    water.forEach((w) => { if (!w.edge) for (let i = 1; i < w.p.length; i++) wseg.push([w.p[i - 1], w.p[i]]); });
    const stops = [], fades = [];
    L.forEach((l) => {
      if (l.r && (l.r.c === 'lane' || l.r.c === 'trackdash')) return;
      const others = segsOf(l, l.rail);
      const major = l.rail || ['primary', 'main', 'highway'].indexOf(l.r.c) > -1;
      [true, false].forEach((atStart) => {
        const p = l.p, e = atStart ? p[0] : p[p.length - 1], b = atStart ? p[Math.min(3, p.length - 1)] : p[Math.max(0, p.length - 4)];
        if (others.some(([a, c]) => segDist(e, a, c) < 60)) return;           // already joined
        const dx = e[0] - b[0], dy = e[1] - b[1], n = Math.hypot(dx, dy) || 1, d = [dx / n, dy / n];
        let tf = 1e9;                                                          // run to the frame
        [[0, FR[0]], [0, FR[2]], [1, FR[1]], [1, FR[3]]].forEach(([k, lim]) => { if (d[k]) { const t = (lim - e[k]) / d[k]; if (t > 0) tf = Math.min(tf, t); } });
        const reach = major ? 2600 : 900;
        const tl = rayHit(e, d, others, Math.min(tf + 60, 1600)), tw = rayHit(e, d, wseg);
        let t = 0, fade = false;
        if (tl < tw && (major || tl < 320)) t = tl + 2;                        // join the next line
        else if (tf < reach && tf < tw) t = tf + 60;                           // out under the frame
        else if (major && !l.rail) { t = Math.min(350, tw - 40); fade = true; } // open country or a bank: dashed run-out
        else if (l.rail) { stops.push([e, Math.atan2(d[1], d[0])]); return; }
        if (t <= 5) return;                                                     // a street that simply ends
        const q = [e[0] + d[0] * t, e[1] + d[1] * t];
        if (fade) fades.push({ p: [e, q], c: l.r.c });
        else if (atStart) l.p.unshift(q); else l.p.push(q);
      });
    });
    return Object.assign({}, geo, {
      water, valley,
      roads: L.filter((l) => !l.rail).map((l) => Object.assign({}, l.r, { p: l.p })),
      rail: L.filter((l) => l.rail).map((l) => l.p),
      stops, fades
    });
  }
  function chunks(p, n) {                           // split a polyline into n runs of equal length
    const acc = [0];
    for (let i = 1; i < p.length; i++) acc.push(acc[i - 1] + Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]));
    const T = acc[acc.length - 1];
    const at = (s) => { let i = 1; while (i < p.length - 1 && acc[i] < s) i++; const f = (s - acc[i - 1]) / ((acc[i] - acc[i - 1]) || 1); return [p[i - 1][0] + (p[i][0] - p[i - 1][0]) * f, p[i - 1][1] + (p[i][1] - p[i - 1][1]) * f]; };
    const out = [];
    for (let c = 0; c < n; c++) {
      const a = T * c / n, b = T * (c + 1) / n, seg = [at(a)];
      for (let i = 1; i < p.length - 1; i++) if (acc[i] > a && acc[i] < b) seg.push(p[i]);
      seg.push(at(b));
      out.push(seg);
    }
    return out;
  }

  // ==========================================================================
  function create(svg, geo, opts) {
    opts = opts || {};
    geo = prep(geo);
    let style = opts.style || 'survey';
    let selected = opts.selected != null ? opts.selected : null;
    let match = opts.match || null;                 // search results: other markers fade, matches get labels
    const hover = opts.hover != null ? opts.hover : null;   // place id whose photo is under the pointer (state sketches)
    const photos = opts.photos || {};
    const photoBase = opts.photoBase || '';
    const view = { cx: 0, cy: 0, k: 0.1, w: 0, h: 0 };

    svg.innerHTML = '';
    svg.classList.add('dm');
    const defs = el('defs', null, svg);
    // Patterns keep a fixed screen size: patternTransform is set in setView.
    const patWood = el('pattern', { id: 'dm-wood', width: 10, height: 10, patternUnits: 'userSpaceOnUse' }, defs);
    el('rect', { width: 10, height: 10, class: 'm-wood' }, patWood);
    el('circle', { cx: 2.5, cy: 2.5, r: 0.9, class: 'm-wood-dot' }, patWood);
    el('circle', { cx: 7.5, cy: 7.2, r: 0.9, class: 'm-wood-dot' }, patWood);
    const patTree = el('pattern', { id: 'dm-tree', width: 16, height: 16, patternUnits: 'userSpaceOnUse' }, defs);
    el('rect', { width: 16, height: 16, class: 'm-wood' }, patTree);
    [[2, 3, 0.8], [7, 1.5, 0.6], [11.5, 5, 0.9], [4.5, 9, 0.6], [9, 11, 0.8], [14, 13.5, 0.6], [1.5, 14, 0.7], [13, 8.5, 0.5]]
      .forEach(([cx, cy, r]) => el('circle', { cx, cy, r, class: 'm-tree' }, patTree));   // engraved stipple
    const patCrown = el('pattern', { id: 'dm-crown', width: 28, height: 28, patternUnits: 'userSpaceOnUse' }, defs);   // near: tree crowns
    [[6, 7, 4.2], [19, 4, 3.4], [14, 17, 4.6], [3, 22, 3.2], [24, 23, 3.8]]
      .forEach(([cx, cy, r]) => el('circle', { cx, cy, r, class: 'm-crown' }, patCrown));
    const patWater = el('pattern', { id: 'dm-water', width: 6, height: 6, patternUnits: 'userSpaceOnUse' }, defs);
    el('rect', { width: 6, height: 6, class: 'm-water-fill' }, patWater);
    el('path', { d: 'M0 3 H6', class: 'm-water-hatch' }, patWater);
    const clip = el('clipPath', { id: 'dm-clip' }, defs);
    el('rect', { x: FR[0], y: FR[1], width: FR[2] - FR[0], height: FR[3] - FR[1] }, clip);

    const back = el('rect', { class: 'm-paper', x: -1e5, y: -1e5, width: 2e5, height: 2e5 }, svg);
    const world = el('g', { class: 'dm-world' }, svg);
    const ov = el('g', { class: 'dm-overlay' }, svg);
    let sheet;

    // ---- BUILD: static world layers (once per style) -------------------------
    function build() {
      world.innerHTML = '';
      svg.classList.remove('dm--survey', 'dm--plate', 'dm--atlas');
      svg.classList.add('dm--' + style);
      const S = STYLE[style];
      const line = S.smooth ? sd : pd;

      sheet = el('g', { 'clip-path': 'url(#dm-clip)' }, world);
      el('rect', { class: 'm-land', x: FR[0], y: FR[1], width: FR[2] - FR[0], height: FR[3] - FR[1] }, sheet);

      // 1. Areas: parks, yards, fields, the clearing
      const ga = el('g', { class: 'L-areas' }, sheet);
      geo.areas.forEach((a) => el('path', { d: pd(a.p, true), class: areaClass(a.fill) }, ga));

      // 2. Valley floor: a wide soft band under the stream
      const gv = el('g', { class: 'L-valley' }, sheet);
      geo.valley.forEach((v) => el('path', { d: line(v.p), class: 'm-valley', style: `stroke-width:${v.w}px` }, gv));

      // 3. Woods: one fill + a screen-scaled pattern
      const gw = el('g', { class: 'L-woods' }, sheet);
      const woodD = geo.forest.map((f) => line(f.p, true)).join('');
      el('path', { d: woodD, class: 'm-wood-area', fill: style === 'plate' ? 'url(#dm-tree)' : 'url(#dm-wood)' }, gw);
      el('path', { d: woodD, class: 'm-wood-crowns lod-near', fill: 'url(#dm-crown)' }, gw);
      el('path', { d: woodD, class: 'm-wood-edge', style: `stroke-width:${px(1)}` }, gw);

      // 4. Relief: only the i===1 contour set (the other is a duplicate)
      const gc = el('g', { class: 'L-relief lod-mid-survey' }, sheet);
      geo.contours.filter((c) => c.i === 1).forEach((c) => {
        const closed = Math.hypot(c.p[0][0] - c.p[c.p.length - 1][0], c.p[0][1] - c.p[c.p.length - 1][1]) < 40;
        el('path', { d: line(c.p, closed), class: 'm-contour' + (closed ? ' is-closed' : ''), style: `stroke-width:${px(0.8)}` }, gc);
      });

      // 5. Wet-ground ticks (short marks) from mid zoom
      const gt = el('g', { class: 'L-veg lod-mid' }, sheet);
      el('path', { d: geo.veg.map((v) => pd(v.p)).join(''), class: 'm-veg', style: `stroke-width:${px(1)}` }, gt);

      // 6. Built-up area (below k 0.8): one solid tint. Every building is joined to EVERY neighbour
      //    within 95 m and the joins are stroked 2R wide with round caps and joins, so a street of
      //    houses becomes one smooth continuous band under the road (no beads, no dashes, no
      //    scalloped circle edges). From k 0.8 it gives way to the real footprints (layer 8).
      if (S.builtR) {
        const B = geo.buildings, cell = 95, grid = new Map();
        B.forEach((b, i) => { const k = Math.floor(b[0] / cell) + ':' + Math.floor(b[1] / cell); (grid.get(k) || grid.set(k, []).get(k)).push(i); });
        let d = '';
        B.forEach((b, i) => {
          const gx = Math.floor(b[0] / cell), gy = Math.floor(b[1] / cell);
          d += `M${r1(b[0])} ${r1(b[1])}h0`;                                   // a lone house still gets a dot
          for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++) (grid.get((gx + ox) + ':' + (gy + oy)) || []).forEach((j) => {
            if (j > i && (B[j][0] - b[0]) ** 2 + (B[j][1] - b[1]) ** 2 < cell * cell) d += `M${r1(b[0])} ${r1(b[1])}L${r1(B[j][0])} ${r1(B[j][1])}`;
          });
        });
        el('path', { d, class: 'm-builtup lod-massing', style: `stroke-width:${2 * S.builtR}px` }, el('g', { class: 'L-builtup' }, sheet));
      }

      // 7. Water: banks under fills; streams taper by width; canal walls in ink
      const gwa = el('g', { class: 'L-water' }, sheet);
      const flows = geo.water.filter((w) => w.id !== 'trib');
      const cut = (w) => (w.id.indexOf('canal') === 0 || w.id === 'outlet' ? 'is-canal' : '');
      flows.forEach((w) => el('path', { d: line(w.p), class: 'm-water-edge ' + cut(w), style: `stroke-width:calc(${w.w}px + var(--u)*2.4)` }, gwa));
      // Brooks run from a spring: 6 runs widening from a fifth of the width at the source to full at the mouth.
      const tribs = geo.water.filter((w) => w.id === 'trib').map((w) => chunks(w.p, 6).map((c, i) => [c, w.w * (0.2 + 0.8 * (i + 1) / 6), (i + 1) / 6]));
      tribs.forEach((runs) => runs.forEach(([c, w, f]) => el('path', { d: pd(c), class: 'm-water-edge is-trib', style: `stroke-width:calc(${r1(w)}px + var(--u)*${r1(0.8 + 1.6 * f)})` }, gwa)));
      tribs.forEach((runs) => runs.forEach(([c, w, f]) => el('path', { d: pd(c), class: 'm-water is-trib', style: `stroke-width:${wpx(r1(w), r1(0.3 + 0.9 * f))}` }, gwa)));
      flows.forEach((w) => el('path', { d: line(w.p), class: 'm-water ' + cut(w), style: `stroke-width:${wpx(w.w, 2)}` }, gwa));
      // near only: a broken white centre line suggests current (no patterns in strokes: they hang browsers)
      geo.water.filter((w) => w.w >= 20 && w.id !== 'canal').forEach((w) =>
        el('path', { d: line(w.p), class: 'm-ripple lod-near', style: `stroke-width:${px(1)};stroke-dasharray:${px(14)} ${px(10)}` }, gwa));

      // 8. Buildings. Below k 0.8 the tint (layer 6) stands for them (massW = 0 in survey);
      //    "massing" (atlas style only): footprints with a fat round-joined stroke of one colour,
      //                so neighbours fuse into street-frontage blocks (no confetti, no staircase);
      //    from k 0.8 (lod-plan): true footprints at real size with a hairline edge.
      //    Landmark buildings (cls 1/2) are drawn darker at every zoom.
      const gb = el('g', { class: 'L-buildings' }, sheet);
      let dB = '', dK = '';
      geo.buildings.forEach((b) => {
        const [x, y, w, h, ang, cls] = b;
        const a = (ang || 0) * Math.PI / 180, c = Math.cos(a), si = Math.sin(a);
        const hw = w / 2, hh = h / 2;
        const pts = [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]].map(([u, v]) => [x + u * c - v * si, y + u * si + v * c]);
        const d = pd(pts, true);
        if (cls) dK += d; else dB += d;
      });
      if (S.massW) {
        // Join every house to its nearest neighbour within 60 m: rows of houses fuse into
        // continuous frontage ribbons instead of a string of beads. Grid buckets keep it O(n).
        const B = geo.buildings, cell = 60, grid = new Map();
        B.forEach((b, i) => { const k = Math.floor(b[0] / cell) + ':' + Math.floor(b[1] / cell); (grid.get(k) || grid.set(k, []).get(k)).push(i); });
        let dL = '';
        B.forEach((b, i) => {
          const gx = Math.floor(b[0] / cell), gy = Math.floor(b[1] / cell);
          let best = -1, bd = 60 * 60;
          for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++) (grid.get((gx + ox) + ':' + (gy + oy)) || []).forEach((j) => {
            if (j === i) return;
            const d2 = (B[j][0] - b[0]) ** 2 + (B[j][1] - b[1]) ** 2;
            if (d2 < bd) { bd = d2; best = j; }
          });
          if (best > -1) dL += `M${r1(b[0])} ${r1(b[1])}L${r1(B[best][0])} ${r1(B[best][1])}`;
        });
        el('path', { d: dL, class: 'm-bld-link lod-massing', style: `stroke-width:${S.massW}px` }, gb);
        el('path', { d: dB, class: 'm-bld-mass lod-massing', style: `stroke-width:${Math.round(S.massW * 0.6)}px` }, gb);
      }
      el('path', { d: dB, class: 'm-bld lod-plan', style: `stroke-width:${px(0.7)}` }, gb);
      el('path', { d: dK, class: 'm-bld-key', style: `stroke-width:max(${px(0.8)}, ${S.massW || S.builtR ? 4 : 0}px)` }, gb);

      // 9. Roads: casings first (all classes), then fills, minor to major
      const gr = el('g', { class: 'L-roads' }, sheet);
      const order = Object.keys(ROADS);
      order.forEach((c) => geo.roads.filter((r) => r.c === c).forEach((r) => {
        const [w, m] = ROADS[c];
        if (c === 'track' || c === 'trackdash' || c === 'lane') return;
        el('path', { d: line(r.p), class: 'm-road-cas', style: `stroke-width:max(calc(var(--u)*${m + 1.6}), calc(${w}px + var(--u)*1.6))` }, gr);
      }));
      order.forEach((c) => geo.roads.filter((r) => r.c === c).forEach((r) => {
        const [w, m] = ROADS[c];
        const minor = c === 'track' || c === 'trackdash' || c === 'lane';
        el('path', {
          d: line(r.p), class: 'm-road m-road--' + c,
          style: minor ? `stroke-width:${px(1.1)};stroke-dasharray:${c === 'lane' ? 'none' : px(5) + ' ' + px(3)}` : `stroke-width:${wpx(w, m)}`
        }, gr);
      }));
      // A major road that runs into water with no bridge: a short dashed run-out, not a cut end.
      geo.fades.forEach((f) => el('path', { d: pd(f.p), class: 'm-road-fade', style: `stroke-width:${wpx(ROADS[f.c][0] * 0.5, 1.4)};stroke-dasharray:${px(5)} ${px(4)}` }, gr));
      geo.paths.forEach((p) => el('path', { d: line(p), class: 'm-path lod-mid', style: `stroke-width:${px(1)};stroke-dasharray:${px(2)} ${px(3)}` }, gr));

      // 10. Covered canal (after roads), bridges, rail
      geo.covered.forEach((c) => el('path', { d: pd(c.p), class: 'm-covered', style: `stroke-width:${wpx(c.w, 2)};stroke-dasharray:${px(4)} ${px(3)}` }, gr));
      geo.bridges.forEach((b) => el('path', { d: pd(b.p), class: 'm-bridge', style: `stroke-width:${wpx(b.w * 0.4, 2)}` }, gr));
      const grl = el('g', { class: 'L-rail' }, sheet);
      geo.rail.forEach((r) => el('path', { d: pd(r), class: 'm-rail', style: `stroke-width:${px(1.6)}` }, grl));
      el('path', { d: geo.ties.map((t) => pd(t)).join(''), class: 'm-tie lod-mid', style: `stroke-width:${px(1.2)}` }, grl);
      // Terminus: a buffer-stop bar across the track, so the line reads as ending on purpose.
      geo.stops.forEach(([e, a]) => {
        const nx = -Math.sin(a), ny = Math.cos(a);
        el('path', { d: `M${r1(e[0] - nx * 40)} ${r1(e[1] - ny * 40)}L${r1(e[0] + nx * 40)} ${r1(e[1] + ny * 40)}`, class: 'm-rail-stop', style: `stroke-width:max(10px, ${px(2.6)})` }, grl);
      });
      geo.dots.forEach((d) => el('circle', { cx: d.x, cy: d.y, r: d.r, class: 'm-dot', style: `stroke-width:${px(1)}` }, grl));

      // 11. Frame and 1 km grid
      if (S.frame !== 'none') {
        const gf = el('g', { class: 'L-frame' }, world);
        const gg = el('g', { class: 'L-grid' }, sheet);
        let d = '';
        for (let x = -6000; x <= FR[2]; x += 1000) d += `M${x} ${FR[1]}V${FR[3]}`;
        for (let y = -3000; y <= FR[3]; y += 1000) d += `M${FR[0]} ${y}H${FR[2]}`;
        el('path', { d, class: 'm-grid', style: `stroke-width:${px(0.6)}` }, gg);
        el('rect', { x: FR[0], y: FR[1], width: FR[2] - FR[0], height: FR[3] - FR[1], class: 'm-frame', style: `stroke-width:${px(1.4)}` }, gf);
        if (S.frame === 'plate') {
          const o = 140;
          el('rect', { x: FR[0] - o, y: FR[1] - o, width: FR[2] - FR[0] + 2 * o, height: FR[3] - FR[1] + 2 * o, class: 'm-frame', style: `stroke-width:${px(2.4)}` }, gf);
          let bars = '';
          for (let x = FR[0]; x < FR[2]; x += 1000) bars += `M${x} ${FR[1] - o / 2}H${Math.min(x + 500, FR[2])}M${x} ${FR[3] + o / 2}H${Math.min(x + 500, FR[2])}`;
          for (let y = FR[1]; y < FR[3]; y += 1000) bars += `M${FR[0] - o / 2} ${y}V${Math.min(y + 500, FR[3])}M${FR[2] + o / 2} ${y}V${Math.min(y + 500, FR[3])}`;
          el('path', { d: bars, class: 'm-frame-bars', style: `stroke-width:${o * 0.5}px` }, gf);
        }
      }
    }

    // ---- OVERLAY: screen-space labels, markers, photos (rebuilt per view) ----
    const sx = (x) => (x - view.cx) * view.k + view.w / 2;
    const sy = (y) => (y - view.cy) * view.k + view.h / 2;
    function lod() { return view.k < LOD.far ? 'far' : view.k < LOD.mid ? 'mid' : 'near'; }

    function overlay() {
      ov.innerHTML = '';
      const z = lod();
      const occ = [];                                   // occupied screen boxes for label collision
      const hit = (b) => occ.some((o) => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]);
      const inView = (x, y, m) => x > -m && y > -m && x < view.w + m && y < view.h + m;

      // Grid refs A–J / 1–8, stuck to the screen edges (survey + plate)
      if (STYLE[style].frame !== 'none') {
        const gref = el('g', { class: 'ov-grid' }, ov);
        for (let i = 0; i < 10; i++) {
          const x = sx(-6000 + i * 1000 + 500);
          if (x < 20 || x > view.w - 20) continue;
          el('text', { x, y: Math.max(14, sy(FR[1]) - 8), class: 'gref' }, gref).textContent = 'ABCDEFGHIJ'[i];
        }
        for (let j = 0; j < 8; j++) {
          const y = sy(-3000 + j * 1000 + 500);
          if (y < 20 || y > view.h - 20) continue;
          el('text', { x: Math.max(12, sx(FR[0]) - 10), y: y + 4, class: 'gref' }, gref).textContent = String(j + 1);
        }
      }

      // Area, water and land labels from the data
      const gl = el('g', { class: 'ov-labels' }, ov);
      geo.labels.forEach((l) => {
        if (l.k === 'road' && z === 'far') return;
        if (l.k === 'land' && z !== 'near') return;
        if (l.k === 'water' && l.s <= 10 && z !== 'near') return;   // brooks and arms: near only
        if (l.k === 'water' && l.s === 11 && z === 'far') return;   // canal names: mid and near
        const x = sx(l.x), y = sy(l.y);
        if (!inView(x, y, 80)) return;
        const t = el('text', { x: 0, y: 0, transform: `translate(${r1(x)} ${r1(y)}) rotate(${-l.a})`, class: 'lbl lbl--' + l.k, 'text-anchor': 'middle' }, gl);
        t.textContent = l.k === 'region' ? spaced(l.t) : l.k === 'road' ? l.t.toUpperCase() : l.t;
        const half = (t.textContent.length * (l.k === 'region' ? 11 : 6)) / 2;
        if (l.k === 'region' || l.k === 'water') occ.push([x - half, y - 10, x + half, y + 6]);
      });

      // Markers
      const gm = el('g', { class: 'ov-markers' }, ov);
      const sites = geo.sites.slice().sort((a, b) => (a.id === selected) - (b.id === selected));
      const placed = [], prints = [], pops = [];
      sites.forEach((s) => {
        const x = sx(s.x), y = sy(s.y);
        if (!inView(x, y, 30)) return;
        const isSel = s.id === selected;
        const dim = match && match.indexOf(s.id) < 0;
        const g = el('g', {
          class: `mk mk--${s.c.toLowerCase()} mk--${s.k.toLowerCase()}${isSel ? ' is-selected' : ''}${dim ? ' is-dim' : ''}${match && !dim ? ' is-match' : ''}`,
          transform: `translate(${r1(x)} ${r1(y)})`, tabindex: 0, role: 'button', 'data-id': s.id,
          'aria-label': `${s.id} ${s.n}, ${s.k}, confidence ${s.c}`
        }, gm);
        if (z === 'far' && !isSel && !(match && !dim)) {
          el('circle', { class: 'mk__dot', r: 5 }, g);
          occ.push([x - 6, y - 6, x + 6, y + 6]);
        } else {
          if (isSel || (match && !dim)) el('circle', { class: 'mk__ring', r: 18 }, g);
          if (s.c !== 'A') el('circle', { class: 'mk__halo', r: 15 }, g);
          el('circle', { class: 'mk__disc', r: isSel ? 13 : 12 }, g);
          el('text', { class: 'mk__num' }, g).textContent = String(s.id).padStart(2, '0');
          occ.push([x - 16, y - 16, x + 16, y + 16]);
          if (!dim) placed.push(s);
        }
        // photo pins
        const ph = photos[s.id];
        if (ph && ph.length && !dim) {
          if (z === 'far') el('circle', { class: 'ph-dot', cx: x + 6, cy: y - 6, r: 2.6 }, gm);
          else if (z === 'mid') {
            const pg = el('g', { class: 'ph-medal', transform: `translate(${r1(x + 17)} ${r1(y - 17)})` }, gm);
            const cid = 'ph-c-' + s.id;
            el('circle', { r: 11, class: 'ph-medal__ring' }, pg);
            el('clipPath', { id: cid }, pg).appendChild(el('circle', { r: 9 }));
            el('image', { href: photoBase + ph[0], x: -9, y: -9, width: 18, height: 18, preserveAspectRatio: 'xMidYMid slice', 'clip-path': `url(#${cid})` }, pg);
            if (ph.length > 1) el('text', { class: 'ph-count', x: 9, y: -7 }, pg).textContent = '×' + ph.length;
            if (s.id === hover) pops.push([x + 17, y - 17, ph, s]);   // hover pops the polaroid out of the medallion
          } else prints.push([s, x, y, ph]);            // near: placed after all markers (below)
        }
      });

      // Near-zoom polaroids (as in production map.js): a white print with a square photo and a
      // handwritten-style caption, a fixed per-place tilt, pinned to the marker by a thin leader.
      // Positions are tried in a ring round the marker, after all markers, so a print never
      // covers one. The shadow is an offset translucent card, not a filter (cheap on phones).
      const PW = 50, PH = 62, PI = 42;
      // One print: used for the near-zoom polaroids and for the hover pop-up (straight, scaled, on top).
      function print(parent, cx, cy, ph, s, tilt, scale, cls) {
        const pg = el('g', { class: 'ph-print' + (cls ? ' ' + cls : ''), transform: `translate(${r1(cx)} ${r1(cy)}) rotate(${tilt})${scale !== 1 ? ` scale(${scale})` : ''}`, tabindex: 0, role: 'button', 'aria-label': `Photographs · ${s.n}` }, parent);
        el('rect', { class: 'ph-print__shadow', x: -PW / 2 + 1, y: -PH / 2 + 2, width: PW, height: PH }, pg);
        el('rect', { class: 'ph-print__card', x: -PW / 2, y: -PH / 2, width: PW, height: PH }, pg);
        el('image', { href: photoBase + ph[0], x: -PI / 2, y: -PH / 2 + 4, width: PI, height: PI, preserveAspectRatio: 'xMidYMid slice' }, pg);
        el('text', { class: 'ph-print__cap', x: 0, y: PH / 2 - 5, 'text-anchor': 'middle' }, pg).textContent = '1958' + (ph.length > 1 ? ' · ×' + ph.length : '');
        return pg;
      }
      const hoverPrints = [];
      prints.forEach(([s, x, y, ph]) => {
        const offs = [[0, -60], [44, -44], [-44, -44], [54, 0], [-54, 0], [0, 60], [44, 46], [-44, 46]];
        const box = ([dx, dy]) => [x + dx - PW / 2 - 2, y + dy - PH / 2 - 2, x + dx + PW / 2 + 2, y + dy + PH / 2 + 2];
        let off = offs.find((o) => !hit(box(o)));
        if (!off && s.id === selected) off = offs[0];
        if (!off) return;
        const px0 = x + off[0], py0 = y + off[1];
        let h = 0;
        for (const ch of String(s.id)) h = (h * 31 + ch.charCodeAt(0)) % 997;
        const tilt = (h % 7) - 3;
        const k = Math.hypot(off[0], off[1]) || 1;                  // leader from the marker edge
        el('path', { class: 'ph-leader', d: `M${r1(x + off[0] / k * 14)} ${r1(y + off[1] / k * 14)}L${r1(px0)} ${r1(py0)}` }, gm);
        // hover (as on the live site): the print straightens and grows; drawn last so it sits on top
        if (s.id === hover) hoverPrints.push([px0, py0, ph, s]);
        else print(gm, px0, py0, ph, s, tilt, 1);
        occ.push(box(off));
      });

      // Place labels: greedy collision, selected first, then A → B → C
      if (z !== 'far' || selected != null || match) {
        const rank = { A: 0, B: 1, C: 2 };
        const cand = placed.slice().sort((a, b) => (b.id === selected) - (a.id === selected) || rank[a.c] - rank[b.c] || a.id - b.id);
        cand.forEach((s) => {
          if (z === 'mid' && s.c === 'C' && s.id !== selected && !match) return;
          const x = sx(s.x), y = sy(s.y);
          const w = s.n.length * 6.6 + 4;
          const right = [x + 18, y - 9, x + 18 + w, y + 7];
          const left = [x - 18 - w, y - 9, x - 18, y + 7];
          const box = !hit(right) ? right : !hit(left) ? left : null;
          if (!box && s.id !== selected) return;
          const b = box || right;
          occ.push(b);
          const t = el('text', { x: r1(b[0] + (b === left ? w : 0)), y: r1(y + 4.5), class: 'lbl lbl--place' + (s.id === selected ? ' is-selected' : ''), 'text-anchor': b === left ? 'end' : 'start' }, gl);
          t.textContent = s.n;
        });
      }
      // Hover states on top of everything: near prints grow 1.6×, mid medallions pop a 1.9× polaroid.
      const gTop = el('g', { class: 'ov-top' }, ov);
      hoverPrints.forEach(([px0, py0, ph, s]) => print(gTop, px0, py0, ph, s, 0, 1.6, 'is-hover'));
      pops.forEach(([cx, cy, ph, s]) => print(gTop, cx, cy - 58, ph, s, 0, 1.9, 'is-hover'));
    }

    // ---- VIEW ------------------------------------------------------------------
    function setView(cx, cy, k) {
      const r = svg.getBoundingClientRect();
      view.w = r.width; view.h = r.height; view.cx = cx; view.cy = cy; view.k = k;
      world.setAttribute('transform', `translate(${r1(view.w / 2 - cx * k)} ${r1(view.h / 2 - cy * k)}) scale(${k})`);
      svg.style.setProperty('--u', (1 / k) + 'px');
      svg.setAttribute('data-z', lod());
      svg.setAttribute('data-bld', view.k < LOD.plan ? 'tint' : 'plan');   // houses: tint until each is ~10 px
      const pk = `scale(${1 / k})`;
      patWood.setAttribute('patternTransform', pk);
      patTree.setAttribute('patternTransform', pk);
      patWater.setAttribute('patternTransform', pk);
      patCrown.setAttribute('patternTransform', pk);
      overlay();
    }
    function fit(b, pad) {
      const r = svg.getBoundingClientRect();
      pad = pad == null ? 24 : pad;
      const k = Math.min((r.width - 2 * pad) / (b[2] - b[0]), (r.height - 2 * pad) / (b[3] - b[1]));
      setView((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, k);
    }

    build();
    return {
      setView, fit, view,
      select(id) { selected = id; overlay(); },
      setMatch(ids) { match = ids && ids.length ? ids : null; overlay(); },
      setStyle(s) { style = s; build(); setView(view.cx, view.cy, view.k); },
      screen: (x, y) => [sx(x), sy(y)],
      site: (id) => geo.sites.find((s) => s.id === id),
      lod
    };
  }

  global.DerryMap = { create, prep, FR, LOD };
})(window);
