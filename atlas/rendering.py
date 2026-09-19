"""Pure dataset -> original SVG display list; no map coordinates in Python.

Procedural relief is derived from DB parameters and water geometry. The historic
vegetation/building texture is preserved as editable vector geometry in the DB.
"""
import base64
import copy
import fcntl
import io
import json
import math
import os
import tempfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
from django.conf import settings
from . import dataset as ds
from .models import MapState

RENDER_VERSION = '1'


def smooth(pts, n=10):
    ps = np.array([pts[0]] + pts + [pts[-1]], float)
    res = []
    for i in range(1, len(ps)-2):
        a, b, c, d = ps[i-1:i+3]
        for t in np.linspace(0, 1, n, endpoint=False):
            res.append((.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t)).tolist())
    return res + [list(pts[-1])]


def distance(xs, ys, pts):
    best = np.full(xs.shape, 1.e9)
    for a, b in zip(pts, pts[1:]):
        a = np.array(a, float); v = np.array(b, float)-a
        if v@v == 0: continue
        t = np.clip(((xs-a[0])*v[0]+(ys-a[1])*v[1])/(v@v), 0, 1)
        best = np.minimum(best, np.hypot(xs-a[0]-t*v[0], ys-a[1]-t*v[1]))
    return best


def terrain(config, features, geometry):
    ex = config['extent']; nx, ny = config['grid']; p = config['parameters']
    xx = np.linspace(ex[0], ex[2], nx); yy = np.linspace(ex[1], ex[3], ny)
    X, Y = np.meshgrid(xx, yy)
    line = lambda key: geometry[features[key]['geometry_id']]['shape']['points']
    stream = [pt for key in config['river_keys'] for pt in line(key)]
    dist = distance(X, Y, stream); dp = distance(X, Y, line(config['penobscot_key']))
    Z = p['baseline'] + p['west_slope']*(-X) + p['river_height']*(1-np.exp(-(dist/p['river_sigma'])**2))
    for x, y, a, sx, sy in config['hills']:
        Z += a*np.exp(-.5*(((X-x)/sx)**2+((Y-y)/sy)**2))
    Z += p['wave_height']*np.sin(X/p['wave_x'])*np.sin(Y/p['wave_y'])
    Z -= p['penobscot_depth']*np.exp(-(dp/p['penobscot_sigma'])**2)
    dy, dx = np.gradient(Z, yy[1]-yy[0], xx[1]-xx[0])
    shade = np.clip(p['shade_base']+p['shade_dx']*dx+p['shade_dy']*dy, p['shade_min'], p['shade_max'])
    rgb = np.clip(np.array(p['rgb'], float)[None,None,:]*(p['tint_base']+p['tint_strength']*(shade-p['shade_min'])/p['shade_span'])[:,:,None], 0, 255).astype('uint8')
    im = Image.fromarray(np.flipud(rgb)).resize(tuple(config['output']), Image.Resampling.BICUBIC)
    out = io.BytesIO(); im.save(out, format='PNG', optimize=True)
    fig, ax = plt.subplots()
    cs = ax.contour(X, Y, Z, levels=np.arange(*config['contours']))
    contours = [smooth(seg.tolist(), 2) for segs in cs.allsegs for seg in segs if len(seg)>18]
    plt.close(fig)
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode(), contours


def translate(shape, x, y):
    shape = copy.deepcopy(shape)
    if 'points' in shape:
        shape['points'] = [[a+x,b+y] for a,b in shape['points']]
    else:
        shape['x'] += x; shape['y'] += y
    return shape


def compile_payload(doc, revision):
    tables = doc['tables']
    indexed = {k:{r['key']:r for r in rows} for k,rows in tables.items()}
    cfg = {k:r['value'] for k,r in indexed['settings'].items()}
    features = indexed['feature']; geometry = indexed['geometry']
    relief, contours = terrain(cfg['terrain'], features, geometry)
    base = []
    for c in sorted(tables['component'], key=lambda c:(c['z'],c['key'])):
        style = indexed['style'][c['style_id']]['value']; recipe = c['recipe']
        generator = recipe.get('generator', 'shape')
        if generator == 'terrain':
            base.extend({'type':'line','points':pts,**style,'component_id':c['key']} for pts in contours)
            continue
        f = features.get(c['feature_id'])
        shape = copy.deepcopy(geometry[c['geometry_id'] or f['geometry_id']]['shape'])
        if 'slice' in recipe:
            shape['points'] = shape['points'][slice(*recipe['slice'])]
        if recipe.get('smooth'):
            shape['points'] = smooth(shape['points'], recipe['smooth'])
        if recipe.get('relative'):
            shape = translate(shape, *ds.anchor(geometry[f['geometry_id']]['shape']))
        if generator == 'rail_ties':
            acc = 0
            for a,b in zip(shape['points'],shape['points'][1:]):
                acc += math.dist(a,b)
                if acc > recipe['spacing']:
                    ang = math.atan2(b[1]-a[1],b[0]-a[0])+math.pi/2
                    length = recipe['half_length']
                    pts = [[b[0]-length*math.cos(ang),b[1]-length*math.sin(ang)], [b[0]+length*math.cos(ang),b[1]+length*math.sin(ang)]]
                    base.append({'type':'line','points':pts,**style,'feature_id':c['feature_id'],'component_id':c['key']})
                    acc = 0
        else:
            base.append({**shape, **style, 'feature_id':c['feature_id'], 'component_id':c['key']})
    for o in base:
        if 'points' in o:
            o['points'] = [[round(x,2),round(y,2)] for x,y in o['points']]
    evidence = {}
    for e in sorted(tables['evidence'], key=lambda e:(e['order'],e['key'])):
        evidence.setdefault(e['feature_id'], []).append(e)
    data = copy.deepcopy(cfg['atlas']); data['sites'] = []; data['unplaced'] = []
    for f in features.values():
        if f['object_type'] not in ('site', 'unplaced'): continue
        refs = evidence.get(f['key'], [])
        common = {k:f[k] for k in ('name','period','note')}
        common['sources'] = [{'reference':e['reference'],'paragraph':e['paragraph'],
                              'source_id':e['source_id'],'note':e['note']} for e in refs]
        if f['object_type'] == 'site':
            s = geometry[f['geometry_id']]['shape']
            data['sites'].append(dict(id=int(f['key']),x=s['x'],y=s['y'],
                **common, **{k:f[k] for k in ('short','kind','confidence','rank')}))
        else:
            data['unplaced'].append(dict(id=f['key'],reference='; '.join(e['reference'] for e in refs),**common))
    data['sites'].sort(key=lambda s:s['id']); data['unplaced'].sort(key=lambda s:int(s['id'][1:]))
    data['web_sources'] = [dict(id=s['key'],**{k:s[k] for k in ('title','url','role')}) for s in tables['source'] if s['kind']=='web']
    labels = []
    for l in sorted(tables['label'], key=lambda l:l['key']):
        x, y = (0,0)
        if l['feature_id']:
            f = features[l['feature_id']]; x,y = ds.anchor(geometry[f['geometry_id']]['shape'])
        labels.append(dict(text=l['text'] or features[l['feature_id']]['name'],x=x+l['dx'],y=y+l['dy'],**l['spec']))
    views = [dict(id=key,**{k:v for k,v in indexed['view'][key].items() if k!='key'}) for key in ['city','central','barrens','camp']]
    return {'data':data,'base':base,'labels':labels,'views':views,'palette':cfg['palette'],
            'colors':cfg['categories'],'relief':relief,'extent':cfg['terrain']['extent'],
            'print':cfg['print'],'revision':revision,'schema_version':1,'digest':ds.digest(doc)}


def current_payload(force=False):
    state = MapState.objects.select_related('revision').only('initialized','revision_id','revision__digest','revision__id').get(pk=1)
    if not state.initialized:
        raise ValueError('Atlas is not initialized.')
    key = state.revision.digest+'-r'+str(state.revision_id)+'-v'+RENDER_VERSION
    cache = settings.ARTIFACT_ROOT/'cache'; cache.mkdir(parents=True, exist_ok=True)
    path = cache/(key+'.json')
    with (cache/(key+'.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists() and not force:
            return json.loads(path.read_text()), key
        # Each revision is an immutable complete snapshot, also after backup restore.
        payload = compile_payload(state.revision.after, state.revision_id)
        with tempfile.NamedTemporaryFile('w', dir=cache, delete=False, encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        os.replace(f.name, path)
    return payload, key


def render_atlas(payload, outdir, fmt='all'):
    from .print_engine import render
    outdir.mkdir(parents=True, exist_ok=True)
    render(payload, outdir, fmt)
