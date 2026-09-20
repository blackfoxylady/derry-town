import json
import os
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from atlas import dataset as ds
from atlas.models import Revision


def read_json(path):
    p = Path(path)
    if p.stat().st_size > 25_000_000:
        raise ValueError('Import exceeds 25 MB.')
    return json.loads(p.read_text(encoding='utf-8'))


def write_json(path, value):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=p.parent, delete=False, encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    os.replace(f.name, p)


class Command(BaseCommand):
    help = 'Versioned map data operations. No public write API.'

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        for action in ['seed', 'edit', 'delete', 'apply', 'import', 'rollback']:
            p = sub.add_parser(action)
            p.add_argument('--author', default='bootstrap' if action == 'seed' else None, required=action != 'seed')
            p.add_argument('--reason', default='Initial preserved atlas' if action == 'seed' else None, required=action != 'seed')
            p.add_argument('--expected-revision', type=int)
            p.add_argument('--dry-run', action='store_true')
            if action in ['apply', 'import']:
                p.add_argument('file')
            if action == 'rollback':
                p.add_argument('revision', type=int)
            if action in ['edit', 'delete']:
                p.add_argument('id')
            if action == 'edit':
                for field in ['name', 'short', 'description', 'period', 'confidence', 'geometry', 'sources']:
                    p.add_argument('--' + field)
                p.add_argument('--description-ru', dest='description_ru',
                               help="Russian description (metadata['ru']['note']); '' clears it.")
                p.add_argument('--x', type=float)
                p.add_argument('--y', type=float)
        p = sub.add_parser('export'); p.add_argument('file')
        p = sub.add_parser('validate'); p.add_argument('file', nargs='?')
        p = sub.add_parser('show'); p.add_argument('table', choices=ds.TABLES); p.add_argument('key')
        p = sub.add_parser('history'); p.add_argument('--limit', type=int, default=20)
        p = sub.add_parser('render'); p.add_argument('--output', required=True)
        p.add_argument('--format', choices=['all', 'pdf', 'svg'], default='all')
        sub.add_parser('rebuild')

    def handle(self, *args, **o):
        try:
            self.run(o)
        except (ValueError, KeyError, TypeError, OSError, ValidationError, Revision.DoesNotExist) as e:
            raise CommandError(str(e)) from e

    def run(self, o):
        action = o['action']
        if action == 'history':
            for r in Revision.objects.order_by('-id')[:max(1, min(o['limit'], 1000))]:
                self.stdout.write(f'{r.id}\t{r.created.isoformat()}\t{r.author}\t{r.reason}')
            return
        if action == 'validate':
            doc = read_json(o['file']) if o['file'] else ds.read_current()[0]
            ds.validate(doc)
            self.stdout.write('Valid: ' + ds.digest(doc))
            return
        if action == 'export':
            doc, rev = ds.read_current(); write_json(o['file'], doc)
            self.stdout.write(f'Exported revision {rev}: {o["file"]}')
            return
        if action == 'show':
            doc, _ = ds.read_current()
            found = next((r for r in doc['tables'][o['table']] if r['key'] == o['key']), None)
            if found is None: raise ValueError('Object not found.')
            self.stdout.write(json.dumps(found, ensure_ascii=False, indent=2))
            return
        if action in ('render', 'rebuild'):
            from atlas.rendering import current_payload, render_atlas
            payload, _ = current_payload(force=action == 'rebuild')
            if action == 'render':
                render_atlas(payload, Path(o['output']), o['format'])
            self.stdout.write(f'{action}: revision {payload["revision"]}, {len(payload["base"])} scene elements')
            return
        transform = lambda doc: doc
        if action in ('seed', 'import'):
            doc = read_json(settings.BASE_DIR / 'data' / 'initial.json' if action == 'seed' else o['file'])
            transform = lambda _: doc
        elif action == 'apply':
            changes = read_json(o['file'])
            transform = lambda doc: ds.patch(doc, changes)
        elif action == 'delete':
            transform = lambda doc: ds.patch(doc, [{'op': 'delete', 'table': 'feature', 'key': o['id']}])
        elif action == 'rollback':
            target = Revision.objects.get(pk=o['revision'])
            transform = lambda _: target.after
            o['reason'] = f'Rollback to {target.id}: ' + o['reason']
        elif action == 'edit':
            transform = lambda doc: self.edit(doc, o)
        rev, result = ds.commit(transform, o['author'], o['reason'], o['expected_revision'], o['dry_run'], action == 'seed')
        self.stdout.write(f'Revision {rev}: {result}')

    def edit(self, doc, o):
        t = doc['tables']
        f = next((r for r in t['feature'] if r['key'] == o['id']), None)
        if f is None: raise ValueError('Feature not found.')
        for field in ['name', 'short', 'period', 'confidence']:
            if o[field] is not None: f[field] = o[field]
        if o['name'] is not None:
            if o['short'] is None: f['short'] = o['name']
            for l in t['label']:
                if l['feature_id'] == f['key'] and l['spec'].get('follow_name'):
                    l['text'] = o['name']
        if o['description'] is not None: f['note'] = o['description']
        if o['description_ru'] is not None:
            # Русский текст живёт в metadata['ru'] — canonical-поля и снапшоты не меняются.
            meta = dict(f['metadata'] or {})
            ru = dict(meta.get('ru') or {})
            if o['description_ru']:
                ru['note'] = o['description_ru']
            else:
                ru.pop('note', None)
            if ru:
                meta['ru'] = ru
            else:
                meta.pop('ru', None)
            f['metadata'] = meta
        if (o['x'] is None) != (o['y'] is None):
            raise ValueError('Supply both --x and --y.')
        if o['geometry'] or o['x'] is not None:
            if f['geometry_id'] is None:
                raise ValueError('Use a transactional patch to locate an unplaced feature.')
            g = next(r for r in t['geometry'] if r['key'] == f['geometry_id'])
            if o['geometry'] and o['x'] is not None:
                raise ValueError('Use either --geometry or --x/--y.')
            if o['geometry']:
                g['shape'] = read_json(o['geometry'])
            else:
                if g['shape']['type'] != 'point':
                    raise ValueError('--x/--y edits a point; use --geometry for a road/area.')
                g['shape'].update(x=o['x'], y=o['y'])
        if o['sources']:
            refs = read_json(o['sources'])
            if not isinstance(refs, list): raise ValueError('Sources must be a list.')
            t['evidence'] = [r for r in t['evidence'] if r['feature_id'] != f['key']]
            for i, ref in enumerate(refs):
                t['evidence'].append({'key': f'e:{f["key"]}:{i}', 'feature_id': f['key'],
                    'source_id': ref['source_id'],
                    'reference': ref['reference'], 'note': ref.get('note', ''), 'order': i})
        return doc
