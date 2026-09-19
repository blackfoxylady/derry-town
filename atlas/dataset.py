"""Versioned interchange, validation and atomic developer-only editing.

All supported writes pass through commit(). Revision snapshots deliberately include
the complete small atlas: rollback includes styles, sources and terrain, not just pins.
"""
import copy
import hashlib
import json
import math
import re
from django.core.exceptions import ValidationError
from django.db import transaction
from . import models as m

TABLES = {'settings': m.Setting, 'geometry': m.Geometry, 'feature': m.Feature,
          'style': m.Style, 'component': m.Component, 'label': m.Label,
          'source': m.Source, 'evidence': m.Evidence, 'view': m.MapView}
ORDER = ['settings', 'geometry', 'style', 'source', 'feature', 'component', 'label', 'evidence', 'view']
FORMAT = 'derry.dataset.v1'


def canonical(doc):
    result = copy.deepcopy(doc)
    for rows in result['tables'].values():
        rows.sort(key=lambda r: r['key'])
    def numbers(value):
        if isinstance(value, dict): return {k:numbers(v) for k,v in value.items()}
        if isinstance(value, list): return [numbers(v) for v in value]
        if isinstance(value, float) and value.is_integer(): return int(value)
        return value
    return numbers(result)


def dumps(doc):
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(doc):
    return hashlib.sha256(dumps(canonical(doc)).encode()).hexdigest()


def empty():
    return {'format': FORMAT, 'tables': {k: [] for k in TABLES}}


def snapshot():
    return {'format': FORMAT, 'tables': {k: list(model.objects.order_by('key').values()) for k, model in TABLES.items()}}


def read_current():
    with transaction.atomic():
        state = m.MapState.objects.select_for_update().get(pk=1)
        if not state.initialized:
            raise ValueError('Atlas is not initialized. Run atlas seed.')
        return snapshot(), state.revision_id


def number(v, limit=1_000_000):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > limit:
        raise ValueError(f'Invalid finite metric number: {v!r}')


def point(p):
    if not isinstance(p, list) or len(p) != 2:
        raise ValueError('A coordinate is [x, y] in local metres.')
    for v in p:
        number(v)


def shape_check(s):
    t = s.get('type')
    fields = {'point': {'type', 'x', 'y'}, 'line': {'type', 'points'}, 'poly': {'type', 'points'},
              'circle': {'type', 'x', 'y', 'r'}, 'rect': {'type', 'x', 'y', 'w', 'h', 'angle'}}
    if t not in fields or set(s) != fields[t]:
        raise ValueError(f'Invalid shape fields: {s.keys()}')
    if t in ('line', 'poly'):
        if not isinstance(s['points'], list) or len(s['points']) < (3 if t == 'poly' else 2):
            raise ValueError('Not enough geometry vertices.')
        for p in s['points']:
            point(p)
    else:
        for k, v in s.items():
            if k != 'type':
                number(v)
        for k in ('w', 'h', 'r'):
            if k in s and s[k] <= 0:
                raise ValueError('Shape dimensions must be positive.')


def anchor(shape):
    if 'points' in shape:
        return shape['points'][0]
    return [shape['x'], shape['y']]


def validate(doc):
    if set(doc) != {'format', 'tables'} or doc['format'] != FORMAT or set(doc['tables']) != set(TABLES):
        raise ValueError('Expected complete derry.dataset.v1 document.')
    tables = doc['tables']
    indexed = {}
    for name, model in TABLES.items():
        rows = tables[name]
        if not isinstance(rows, list):
            raise ValueError(f'{name}: expected a list')
        indexed[name] = {}
        fields = {f.attname for f in model._meta.fields}
        for r in rows:
            if not isinstance(r, dict) or set(r) != fields:
                raise ValueError(f'{name}: exact fields required: {sorted(fields)}')
            key = r['key']
            if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', key) or key in indexed[name]:
                raise ValueError(f'{name}: invalid/duplicate key {key!r}')
            indexed[name][key] = r
            obj = model(**r)
            # JSON empty dictionaries are meaningful; relationships validated below
            excluded = [f.name for f in model._meta.fields if f.is_relation or isinstance(f, m.models.JSONField)]
            obj.full_clean(exclude=excluded, validate_unique=False, validate_constraints=False)
    for name, model in TABLES.items():
        for f in model._meta.fields:
            if not f.is_relation:
                continue
            target = next(k for k, v in TABLES.items() if v == f.related_model)
            for r in tables[name]:
                v = r[f.attname]
                if v is None and f.null:
                    continue
                if v not in indexed[target]:
                    raise ValueError(f'{name}/{r["key"]}: missing {target}/{v}')
    for r in tables['geometry']:
        shape_check(r['shape'])
    features = indexed['feature']
    geometries = indexed['geometry']
    kinds = {'Homes', 'Civic', 'Encounters', 'Historical', 'Barrens', 'Outlying'}
    for f in features.values():
        if f['object_type'] not in ('site', 'unplaced', 'road', 'water', 'area', 'path', 'rail', 'landmark', 'decoration'):
            raise ValueError('Unknown object_type.')
        if f['rank'] not in (1, 2, 3) or f['confidence'] not in ('', 'A', 'B', 'C', 'U'):
            raise ValueError('Invalid rank/confidence.')
        if f['object_type'] == 'unplaced':
            if f['geometry_id'] is not None or f['confidence'] != 'U' or not re.fullmatch(r'U[1-9][0-9]*', f['key']):
                raise ValueError('Unplaced features use U identifiers, U confidence and no geometry.')
        elif f['geometry_id'] is None:
            raise ValueError('Located features need geometry.')
        if f['object_type'] == 'site':
            if not f['name'].strip():
                raise ValueError('A mapped site needs a name.')
            if not re.fullmatch(r'[1-9][0-9]*', f['key']) or f['kind'] not in kinds or f['confidence'] not in ('A', 'B', 'C'):
                raise ValueError('Mapped sites require numeric IDs, category and A/B/C confidence.')
            if geometries[f['geometry_id']]['shape']['type'] != 'point':
                raise ValueError('A site anchor must be a point; footprints belong in components.')
    for s in tables['style']:
        v = s['value']
        if not isinstance(v, dict) or set(v) - {'fill', 'stroke', 'width', 'dash', 'layer'}:
            raise ValueError('Invalid style fields.')
        for k in ('fill', 'stroke'):
            if v.get(k) is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}', v[k]):
                raise ValueError('Colours must be #RRGGBB or null.')
        number(v.get('width', 1), 1000)
        if v.get('width', 1) < 0 or v.get('layer', 'base') not in ('base', 'relief', 'buildings'):
            raise ValueError('Invalid style width/layer.')
        if v.get('dash') is not None:
            for x in v['dash']:
                number(x, 1000)
                if x <= 0:
                    raise ValueError('Dash lengths must be positive.')
    for c in tables['component']:
        recipe = c['recipe']
        if not isinstance(recipe, dict) or set(recipe) - {'generator', 'relative', 'smooth', 'slice', 'spacing', 'half_length'}:
            raise ValueError('Invalid recipe fields.')
        if recipe.get('generator', 'shape') not in ('shape', 'terrain', 'rail_ties'):
            raise ValueError('Unknown component generator.')
        if recipe.get('generator', 'shape') != 'terrain':
            f = features.get(c['feature_id'])
            g = geometries.get(c['geometry_id'] or (f and f['geometry_id']))
            if not g:
                raise ValueError('Component needs its own or its feature geometry.')
            if recipe.get('relative') and (not f or f['geometry_id'] is None):
                raise ValueError('Relative component needs a located feature.')
            if g['shape']['type'] == 'point':
                raise ValueError('A point anchor cannot be drawn directly; use circle/rect geometry.')
        if not isinstance(recipe.get('smooth', 0), int) or not 0 <= recipe.get('smooth', 0) <= 20:
            raise ValueError('smooth must be 0..20.')
        if recipe.get('smooth') and g['shape']['type'] not in ('line', 'poly'):
            raise ValueError('Only paths can be smoothed.')
        if recipe.get('generator') == 'rail_ties':
            if g['shape']['type'] != 'line': raise ValueError('Rail ties require a line.')
            for key in ('spacing', 'half_length'):
                number(recipe[key], 1000)
                if recipe[key] < 1: raise ValueError('Rail dimensions must be at least 1 metre.')
        if 'slice' in recipe:
            sl = recipe['slice']
            if not isinstance(sl, list) or len(sl) != 2 or any(v is not None and (type(v) is not int or v < 0) for v in sl):
                raise ValueError('slice is [start, stop], with null allowed.')
            if g['shape']['type'] not in ('line', 'poly') or len(g['shape']['points'][slice(*sl)]) < 2:
                raise ValueError('Slice leaves too few vertices.')
    for l in tables['label']:
        number(l['dx']); number(l['dy'])
        spec = l['spec']
        if set(spec) - {'size', 'angle', 'font', 'kind', 'views', 'web_offset', 'follow_name'}:
            raise ValueError('Invalid label fields.')
        if spec.get('font') not in ('Sans', 'SansBold', 'Serif', 'SerifBold', 'Italic') or spec.get('kind') not in ('road', 'region', 'water', 'land'):
            raise ValueError('Invalid label font/kind.')
        number(spec['size'], 100); number(spec['angle'], 360)
        if spec['size'] <= 0 or not set(spec['views']) <= set(indexed['view']):
            raise ValueError('Invalid label size/views.')
        if 'web_offset' in spec:
            point(spec['web_offset'])
        if l['feature_id'] and features[l['feature_id']]['geometry_id'] is None:
            raise ValueError('Label needs a located feature.')
    for v in tables['view']:
        if len(v['bounds']) != 4:
            raise ValueError('View bounds are [xmin,ymin,xmax,ymax].')
        for x in v['bounds']:
            number(x)
        a, b, c, d = v['bounds']
        if a >= c or b >= d or v['scale'] <= 0:
            raise ValueError('Invalid view bounds/scale.')
        if abs((c-a)/(d-b) - 440/350) > .015:
            raise ValueError('Print view must keep 440:350 aspect ratio.')
        if abs((c-a)/.440-v['scale']) > 2:
            raise ValueError('View scale must match A2 frame width (440 mm).')
    if set(indexed['view']) != {'city', 'central', 'barrens', 'camp'}:
        raise ValueError('Keep the four existing atlas views.')
    cfg = indexed['settings']
    if not {'atlas', 'terrain', 'print', 'palette', 'categories'} <= set(cfg):
        raise ValueError('Missing required settings.')
    terrain = cfg['terrain']['value']
    for setting in ('palette', 'categories'):
        for colour in cfg[setting]['value'].values():
            if not isinstance(colour, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
                raise ValueError('Palette colours must be #RRGGBB.')
    if set(cfg['categories']['value']) != kinds:
        raise ValueError('Keep the six existing map categories.')
    if not {'paper','ink','muted','forest','park','water','waterline','line'} <= set(cfg['palette']['value']):
        raise ValueError('Incomplete palette.')
    if not {'flow_arrows','scale_bars','source_note','intro','local_relationships'} <= set(cfg['print']['value']):
        raise ValueError('Incomplete print settings.')
    for arrow in cfg['print']['value']['flow_arrows']:
        if len(arrow) != 3: raise ValueError('Flow arrow = [x,y,angle].')
        for n in arrow: number(n)
    for key in indexed['view']:
        value = cfg['print']['value']['scale_bars'][key]
        number(value)
        if value <= 0: raise ValueError('Scale bar must be positive.')
        if not isinstance(cfg['print']['value']['intro'][key], str): raise ValueError('Invalid print introduction.')
    if not {'extent', 'grid', 'output', 'hills', 'parameters', 'contours', 'river_keys', 'penobscot_key'} <= set(terrain):
        raise ValueError('Incomplete terrain settings.')
    for f in terrain['river_keys'] + [terrain['penobscot_key']]:
        if f not in features or geometries[features[f]['geometry_id']]['shape']['type'] != 'line':
            raise ValueError('Terrain requires existing river polylines.')
    for dim in ('grid', 'output'):
        if len(terrain[dim]) != 2 or any(type(n) is not int or not 16 <= n <= 2400 for n in terrain[dim]):
            raise ValueError('Terrain dimensions must be 16..2400 pixels.')
    for hill in terrain['hills']:
        if len(hill) != 5:
            raise ValueError('Hill = [x,y,amplitude,sigma_x,sigma_y].')
        for n in hill:
            number(n)
        if min(hill[3:]) <= 0:
            raise ValueError('Hill sigmas must be positive.')
    for n in terrain['parameters'].values():
        if isinstance(n, list):
            for x in n: number(x)
        else: number(n)
    for key in ('river_sigma', 'penobscot_sigma', 'wave_x', 'wave_y', 'shade_span'):
        if terrain['parameters'][key] <= 0:
            raise ValueError(f'{key} must be positive.')
    if len(terrain['extent']) != 4 or terrain['extent'][0] >= terrain['extent'][2] or terrain['extent'][1] >= terrain['extent'][3]:
        raise ValueError('Invalid terrain extent.')
    for n in terrain['extent'] + terrain['contours']:
        number(n)
    if len(terrain['contours']) != 3 or terrain['contours'][2] <= 0 or not 1 <= (terrain['contours'][1]-terrain['contours'][0])/terrain['contours'][2] <= 100:
        raise ValueError('Invalid contour levels.')
    for r in tables['source']:
        if r['url'] and not r['url'].startswith(('https://', 'http://')):
            raise ValueError('Source URLs must be HTTP(S).')
    # Reject NaN/Infinity anywhere, including extension metadata.
    dumps(doc)
    return canonical(doc)


def replace_tables(doc):
    for k in reversed(ORDER):
        TABLES[k].objects.all().delete()
    for k in ORDER:
        TABLES[k].objects.bulk_create([TABLES[k](**r) for r in doc['tables'][k]], batch_size=400)


def commit(transform, author, reason, expected=None, dry_run=False, seed=False):
    if not author.strip() or not reason.strip():
        raise ValueError('Author and reason are required.')
    with transaction.atomic():
        state = m.MapState.objects.select_for_update().get(pk=1)
        if seed and state.initialized:
            return state.revision_id, 'already initialized; unchanged'
        if not seed and not state.initialized:
            raise ValueError('Run atlas seed first.')
        before = snapshot()
        if seed and any(before['tables'].values()):
            raise ValueError('Refusing to seed a nonempty uninitialized atlas.')
        if expected is not None and state.revision_id != expected:
            raise ValueError(f'Revision conflict: current={state.revision_id}, expected={expected}.')
        # Complete imports and rollbacks must preserve every supplied field exactly.
        after = validate(transform(copy.deepcopy(before)))
        if canonical(before) == after:
            return state.revision_id, 'no changes'
        if dry_run:
            return state.revision_id, 'valid; dry run, no writes'
        replace_tables(after)
        rev = m.Revision.objects.create(author=author, reason=reason, before=before, after=after, digest=digest(after))
        state.initialized = True
        state.revision = rev
        state.save(update_fields=['initialized', 'revision'])
        return rev.pk, 'committed'


def patch(doc, changes):
    if not isinstance(changes, list):
        raise ValueError('Patch is a list of {op,table,key,values}.')
    explicit_labels = {str(c['key']) for c in changes if c.get('table') == 'label'
                       and 'text' in c.get('values', {})}
    for change in changes:
        op, table, key = change['op'], change['table'], str(change['key'])
        if table not in TABLES or op not in ('add', 'update', 'delete'):
            raise ValueError('Invalid patch operation/table.')
        rows = doc['tables'][table]
        current = next((r for r in rows if r['key'] == key), None)
        if op == 'add':
            if current:
                raise ValueError(f'{table}/{key} already exists.')
            obj = TABLES[table](key=key, **change.get('values', {}))
            rows.append({f.attname: getattr(obj, f.attname) for f in obj._meta.fields})
        elif current is None:
            raise ValueError(f'{table}/{key} does not exist.')
        elif op == 'update':
            if 'key' in change['values']:
                raise ValueError('IDs are immutable. Add/delete explicitly instead.')
            values = change['values']
            rename = table == 'feature' and 'name' in values and values['name'] != current['name']
            current.update(values)
            if rename:
                if 'short' not in values: current['short'] = current['name']
                for label in doc['tables']['label']:
                    if label['feature_id'] == key and label['spec'].get('follow_name') and label['key'] not in explicit_labels:
                        label['text'] = current['name']
        else:
            rows.remove(current)
            if table == 'feature':
                for dependent in ('component', 'label', 'evidence'):
                    doc['tables'][dependent] = [r for r in doc['tables'][dependent] if r['feature_id'] != key]
    return doc
