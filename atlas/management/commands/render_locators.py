import json
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from atlas import locators
from atlas.rendering import current_payload


class Command(BaseCommand):
    help = ('Static map crops (locators) for place pages, the place index and editorial pages. '
            'export (live DB) → node tools/locators/shoot.cjs (PC) → pack; check compares the '
            'committed frames with the current map data.')

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        p = sub.add_parser('export', help='Write renderer geometry (EN, RU) and the frame list.')
        p.add_argument('--out', default='build/locators')
        p = sub.add_parser('pack', help='Turn rendered PNG frames into WebP + manifest.json.')
        p.add_argument('--src', default='build/locators')
        sub.add_parser('check', help='Exit 1 when the frames are missing or older than the map data.')

    def handle(self, *args, **o):
        action = o['action']
        if action == 'export':
            out = Path(o['out'])
            out.mkdir(parents=True, exist_ok=True)
            # Frames of an earlier export must not slip into this one (pack also checks dates).
            shutil.rmtree(out / 'png', ignore_errors=True)
            payload, _ = current_payload()
            geos, jobs, manifest = locators.plan(payload, payload.get('revision'))
            for lang, geo in geos.items():
                (out / f'geometry-{lang}.json').write_text(
                    json.dumps(geo, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            (out / 'jobs.json').write_text(
                json.dumps({'jobs': jobs, 'manifest': manifest}, ensure_ascii=False, indent=1),
                encoding='utf-8')
            self.stdout.write(f'{len(jobs)} frames planned in {out}; next: node tools/locators/shoot.cjs {out}')
        elif action == 'pack':
            src = Path(o['src'])
            plan = json.loads((src / 'jobs.json').read_text(encoding='utf-8'))
            try:
                names = locators.pack(src, plan['jobs'], plan['manifest'])
            except FileNotFoundError as error:
                raise CommandError(str(error))
            self.stdout.write(f'{len(names)} frames written to {locators.OUTPUT_DIR}')
        else:
            data = locators.manifest()
            if not data:
                raise CommandError('No locators: atlas/static/atlas/locators/manifest.json is missing.')
            payload, _ = current_payload()
            current = locators.digest(locators.geometries(payload))
            if data['digest'] != current:
                raise CommandError(
                    f"Locators are stale (rendered for revision {data.get('revision')}); "
                    'rebuild them: render_locators export → shoot.cjs → pack.')
            self.stdout.write(f"Locators match the map data ({len(data['files'])} frames).")
