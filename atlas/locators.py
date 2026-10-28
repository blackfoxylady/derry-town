"""Локаторы (редизайн, блок 04): статичные кадры карты вокруг места.

Кадры рисует эталонный рендерер Design (tools/locators/renderer) в headless-браузере
на ПК разработчика, WebP-файлы лежат в git (atlas/static/atlas/locators/), образ и
VPS не меняются. Цепочка (решение 23.10, трекер §3):

  1. manage.py render_locators export --out build/locators   — в контейнере с живой БД:
     геометрия для рендерера из текущего payload (EN и RU) и список кадров;
  2. node tools/locators/shoot.cjs build/locators            — на ПК, Playwright → PNG;
  3. manage.py render_locators pack --src build/locators     — Pillow → WebP + manifest.json.

manifest.json хранит digest геометрии: `render_locators check` и тест сверяют его с
текущими данными, чтобы кадры не отстали от карты.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

from .localized_names import localize_map_payload

# Bump when the renderer, the presets or the conversion below change: old frames go stale.
LOCATOR_VERSION = '1'
OUTPUT_DIR = Path(settings.BASE_DIR) / 'atlas' / 'static' / 'atlas' / 'locators'
STATIC_PREFIX = 'atlas/locators/'

# Per-place presets: CSS size and zoom k (screen px per metre), rendered at 2× density.
PRESETS = {
    'panel': (380, 270, 0.5),   # place page fact panel
    'card': (270, 120, 0.6),    # related-place cards
    'tile': (480, 360, 0.6),    # place index tile without cover or photo
}
EXAMPLE = (220, 110, 0.6)       # method matrix: one example per confidence level
EXAMPLES = ('12', '6', '8')     # A, B, C
# The "Open the map of Derry" card: one fixed frame on the Barrens, the Kenduskeag and
# the edge of the centre (screen orientation, metres).
MAPCARD = {'w': 400, 'h': 140, 'cx': -1650, 'cy': 300, 'k': 0.1}
# The whole-town inset: one frame per language that holds every place; the red frame of
# the panel crop is drawn over it in CSS. Rendered at 448 × 320 and stored at half size
# (224 × 160, the 2× of its 112 × 80 slot), so markers turn into dots.
TOWN = {'w': 448, 'h': 320, 'margin': 350}
TOWN_STORED = (224, 160)
LANGS = ('en', 'ru')
WEBP_QUALITY = 80


# ---- geometry: live payload → the renderer's map-geometry.json --------------------------
def _r(value):
    return round(float(value), 1) + 0.0  # + 0.0: no "-0.0" in the JSON


def _simplify(points, tolerance=1.0):
    """Ramer–Douglas–Peucker, iterative. Payload lines are densely sampled; at locator
    zooms (k ≤ 0.6) a metre is under a screen pixel."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (ax, ay), (bx, by) = points[first], points[last]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5
        best, index = 0.0, None
        for i in range(first + 1, last):
            px, py = points[i]
            dist = (abs(dy * px - dx * py + bx * ay - by * ax) / norm if norm
                    else ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5)
            if dist > best:
                best, index = dist, i
        if index is not None and best > tolerance:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [p for p, k in zip(points, keep) if k]


def _line(points):
    """Payload points (map y up) → screen orientation (y down), simplified and rounded."""
    return [[_r(x), _r(-y)] for x, y in _simplify([(float(x), float(y)) for x, y in points])]


def renderer_geometry(payload):
    """The shape the reference renderer reads (blocks/12-cartography/renderer/data/
    map-geometry.json): litho.js adapt() layer split, y flipped to the screen."""
    g = {key: [] for key in ('contours', 'forest', 'areas', 'veg', 'valley', 'water', 'covered',
                             'rail', 'ties', 'roads', 'paths', 'bridges', 'misc', 'buildings', 'dots')}
    for o in payload['base']:
        cls, fid = o.get('cls') or 'misc', o.get('feature_id') or ''
        kind = o.get('type')
        if cls in ('water-core', 'rail-fill', 'bridge-fill') or (
                cls.startswith('road-') and cls.endswith('-fill')):
            continue  # the renderer rebuilds fills from widths
        if kind == 'rect':
            plain = o.get('fill') == '#c7beb0' and not o.get('stroke')
            g['buildings'].append([_r(o['x']), _r(-o['y']), _r(o['w']), _r(o['h']),
                                   _r(-(o.get('angle') or 0)), 0 if plain else 1,
                                   o.get('fill'), o.get('stroke') or 0])
            continue
        if kind == 'circle':
            g['dots'].append({'x': _r(o['x']), 'y': _r(-o['y']), 'r': o['r'], 'fill': o.get('fill'),
                              'stroke': o.get('stroke'), 'w': o.get('width'), 'fid': fid})
            continue
        if not o.get('points'):
            continue
        p = _line(o['points'])
        if cls == 'valley':
            g['valley'].append({'p': p, 'w': o['width']})
        elif cls == 'water-edge':
            g['water'].append({'id': fid[6:] if fid.startswith('water:') else 'trib', 'p': p,
                               'w': o['width'], 'edge': o.get('stroke') == '#8b968e'})
        elif cls == 'covered':
            g['covered'].append({'p': p, 'w': o['width']})
        elif cls == 'rail':
            g['rail'].append(p)
        elif cls == 'rail-ties':
            g['ties'].append(p)
        elif cls == 'path':
            g['paths'].append(p)
        elif cls == 'contour':
            g['contours'].append({'i': 1 if (o.get('width') or 0) >= 1.4 else 0, 'p': p})
        elif cls.startswith('road-'):
            g['roads'].append({'id': fid, 'c': cls[5:].removesuffix('-casing'), 'p': p})
        elif cls == 'barrens':
            g['forest'].append({'t': 'barrens', 'p': p})
        elif cls in ('forest', 'forest-light'):
            g['forest'].append({'t': o.get('fill'), 'p': p})
        elif cls in ('park', 'lot') or kind == 'poly':
            g['areas'].append({'p': p, 'fill': o.get('fill'), 'stroke': o.get('stroke'),
                               'w': o.get('width'), 'fid': fid})
        elif cls == 'veg':
            g['veg'].append({'t': 1 if o.get('stroke') == '#879674' else 0, 'p': p})
        elif cls == 'bridge':
            g['bridges'].append({'p': p, 'w': o['width'], 'fid': fid})
        else:
            g['misc'].append({'p': p, 's': o.get('stroke'), 'w': o.get('width'),
                              'dash': o.get('dash'), 'fid': fid})
    labels = []
    for label in payload.get('labels', []):
        ox, oy = label.get('web_offset') or (0, 0)
        labels.append({'t': label['text'], 'x': _r(label['x'] + ox), 'y': _r(-(label['y'] + oy)),
                       's': label.get('size'), 'a': label.get('angle') or 0, 'f': label.get('font'),
                       'k': label.get('kind'), 'v': label.get('views') or []})
    g['labels'] = labels
    g['sites'] = [{'id': s['id'], 'x': _r(s['x']), 'y': _r(-s['y']), 'n': s.get('short') or s['name'],
                   'k': s['kind'], 'c': s['confidence']} for s in payload['data']['sites']]
    g['views'] = [{'id': v['id'], 't': v.get('title'),
                   'b': [v['bounds'][0], -v['bounds'][3], v['bounds'][2], -v['bounds'][1]]}
                  for v in payload.get('views', [])]
    # No colours: the renderer takes them from the site tokens (--cat-*, --map-*), so a
    # palette change in the data leaves every frame as it is.
    g['flow'] = [[x, -y, a] for x, y, a in (payload.get('print') or {}).get('flow_arrows', [])]
    return g


def geometries(payload):
    """EN and RU geometry: RU swaps place names and map labels (localize_map_payload)."""
    return {'en': renderer_geometry(payload), 'ru': renderer_geometry(localize_map_payload(payload))}


def digest(geos):
    text = json.dumps({'v': LOCATOR_VERSION, 'geo': geos}, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def town_frame(sites):
    """One frame for the whole-town inset that holds every place with a margin."""
    xs = [s['x'] for s in sites]
    ys = [s['y'] for s in sites]
    m = TOWN['margin']
    w, h = max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m
    k = round(min(TOWN['w'] / w, TOWN['h'] / h), 4)
    return {'w': TOWN['w'], 'h': TOWN['h'], 'k': k,
            'cx': _r((max(xs) + min(xs)) / 2), 'cy': _r((max(ys) + min(ys)) / 2)}


def plan(payload, revision=None):
    """Everything step 2 and step 3 need: geometry files, frames to render, manifest data."""
    geos = geometries(payload)
    sites = geos['en']['sites']
    town = town_frame(sites)
    jobs = []
    for lang in LANGS:
        suffix = '' if lang == 'en' else '-ru'
        data = f'geometry-{lang}.json'
        for s in sites:
            for preset, (w, h, k) in PRESETS.items():
                jobs.append({'name': f"{s['id']}-{preset}{suffix}", 'w': w, 'h': h, 'dpr': 2, 'k': k,
                             'cx': s['x'], 'cy': s['y'], 'sel': s['id'], 'lang': lang, 'data': data})
        for key in EXAMPLES:
            s = next((s for s in sites if str(s['id']) == key), None)
            if s:
                w, h, k = EXAMPLE
                jobs.append({'name': f'{key}-example{suffix}', 'w': w, 'h': h, 'dpr': 2, 'k': k,
                             'cx': s['x'], 'cy': s['y'], 'sel': s['id'], 'lang': lang, 'data': data})
        jobs.append({'name': f'mapcard{suffix}', 'w': MAPCARD['w'], 'h': MAPCARD['h'], 'dpr': 2,
                     'k': MAPCARD['k'], 'cx': MAPCARD['cx'], 'cy': MAPCARD['cy'], 'sel': None,
                     'lang': lang, 'data': data})
        jobs.append({'name': f'town{suffix}', 'w': town['w'], 'h': town['h'], 'dpr': 1, 'k': town['k'],
                     'cx': town['cx'], 'cy': town['cy'], 'sel': None, 'lang': lang, 'data': data})
    manifest = {
        'version': LOCATOR_VERSION, 'digest': digest(geos), 'revision': revision,
        'presets': {**{name: [w, h] for name, (w, h, _) in PRESETS.items()},
                    'example': list(EXAMPLE[:2]), 'mapcard': [MAPCARD['w'], MAPCARD['h']],
                    'town': list(TOWN_STORED)},
        'town': town,
        'places': {str(s['id']): [s['x'], s['y']] for s in sites},
    }
    return geos, jobs, manifest


def pack(src, jobs, manifest, out=OUTPUT_DIR):
    """PNG frames from step 2 → WebP in atlas/static/atlas/locators + manifest.json.
    Files of places that no longer exist are removed; unchanged frames give identical bytes.
    A frame older than the plan (jobs.json) is refused: it was drawn from older data."""
    from PIL import Image
    src, out = Path(src), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    planned = (src / 'jobs.json').stat().st_mtime if (src / 'jobs.json').exists() else 0
    missing = [j['name'] for j in jobs
               if not (src / 'png' / f"{j['name']}.png").is_file()
               or (src / 'png' / f"{j['name']}.png").stat().st_mtime < planned]
    if missing:
        raise FileNotFoundError(f'{len(missing)} frames are missing or older than jobs.json, '
                                f'e.g. {missing[:5]}: run shoot.cjs again')
    # The renderer page may shift a frame sideways so the selected name fits: the town
    # inset marks the panel crop where it really is.
    views_file = src / 'png' / 'views.json'
    views = json.loads(views_file.read_text(encoding='utf-8')) if views_file.exists() else {}
    places = dict(manifest.get('places', {}))
    for key in places:
        view = views.get(f'{key}-panel')
        if view:
            places[key] = [view['cx'], view['cy']]
    names = []
    for job in jobs:
        with Image.open(src / 'png' / f"{job['name']}.png") as image:
            image = image.convert('RGB')
            if job['name'].startswith('town'):
                image = image.resize(TOWN_STORED, Image.LANCZOS)
            name = f"{job['name']}.webp"
            image.save(out / name, 'WEBP', quality=WEBP_QUALITY, method=6)
            names.append(name)
    for stale in set(p.name for p in out.glob('*.webp')) - set(names):
        (out / stale).unlink()
    manifest = {**manifest, 'places': places, 'files': sorted(names)}
    (out / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    return names


# Unlocated places that lie outside the sheet (K5, решение 23.10): instead of "No point on
# the map" they get "Off the map" with a direction. The others are in town without a point.
OFF_MAP = {
    'U4': {'en': ('Juniper Hill lies near Augusta, outside the sheet. The atlas does not squeeze '
                  'it onto the edge of the town plan.', 'Augusta area, beyond the edge of the map'),
           'ru': ('Джунипер-Хилл находится у Огасты, за пределами листа. Атлас не втискивает его '
                  'на край плана города.', 'окрестности Огасты, за краем карты')},
    'U8': {'en': ('The farm lies just over the Newport line, outside the sheet.',
                  'Newport, beyond the edge of the map'),
           'ru': ('Ферма — сразу за границей Ньюпорта, за пределами листа.',
                  'Ньюпорт, за краем карты')},
}


def off_map(key, language='en'):
    """{'text', 'direction'} for a place outside the sheet, None for anything else.
    The direction is shown after "Derry →" («Дерри →»)."""
    entry = OFF_MAP.get(str(key))
    if not entry:
        return None
    text, direction = entry['ru' if language == 'ru' else 'en']
    return {'text': text, 'direction': direction}


# ---- in the page -------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _manifest_cached(mtime):
    return json.loads((OUTPUT_DIR / 'manifest.json').read_text(encoding='utf-8'))


def manifest():
    path = OUTPUT_DIR / 'manifest.json'
    try:
        return _manifest_cached(path.stat().st_mtime_ns)
    except (FileNotFoundError, ValueError):
        return None


def frame(preset, key=None, language='en'):
    """Static URL and CSS size of one frame, or None when it was never rendered (the page
    then falls back to the hatched "no map" block). Per-place presets take the place id;
    'town' and 'mapcard' take none."""
    data = manifest()
    if not data:
        return None
    name = (f'{key}-{preset}' if key is not None else preset) + ('-ru' if language == 'ru' else '')
    if name + '.webp' not in data['files']:
        return None
    w, h = data['presets'][preset]
    return {'url': static(f'{STATIC_PREFIX}{name}.webp'), 'width': w, 'height': h}


def town_marker(key):
    """Where the panel crop (centred on manifest['places'][key]) sits on the whole-town
    inset, in percent of the inset:
    {'left', 'top', 'width', 'height', 'style'}; None for places without coordinates."""
    data = manifest()
    if not data or str(key) not in data['places']:
        return None
    x, y = data['places'][str(key)]
    t = data['town']
    pw, ph, pk = PRESETS['panel']
    span_x, span_y = t['w'] / t['k'], t['h'] / t['k']
    left = (x - pw / pk / 2 - (t['cx'] - span_x / 2)) / span_x
    top = (y - ph / pk / 2 - (t['cy'] - span_y / 2)) / span_y
    box = {'left': left * 100, 'top': top * 100,
           'width': pw / pk / span_x * 100, 'height': ph / pk / span_y * 100}
    # Ready CSS: a float in a template would be localised ("12,5" on /ru/).
    return {**{k: round(v, 2) for k, v in box.items()},
            'style': ';'.join(f'{k}:{v:.2f}%' for k, v in box.items())}
