import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from atlas import covers
from atlas.models import PlaceCover


def describe(cover):
    marks = [f'#{cover.id}', cover.original_name, f'sha256={cover.sha256[:12]}…',
             f'feature={cover.feature_key}', str(cover.year)]
    text = '\t'.join(marks) + '\n\t' + cover.alt
    return text + ('\n\t[ru] ' + cover.alt_ru if cover.alt_ru else '')


class Command(BaseCommand):
    help = 'Place cover photos: files in media/covers plus DB records, outside atlas revisions.'

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        p = sub.add_parser('add', help='Import one cover photo for a place.')
        p.add_argument('file')
        p.add_argument('--feature', required=True)
        p.add_argument('--year', type=int, required=True)
        p.add_argument('--alt', required=True)
        p.add_argument('--alt-ru', default='', dest='alt_ru')
        p = sub.add_parser('import', help='Import a directory using a JSON manifest (all or nothing).')
        p.add_argument('directory')
        p.add_argument('--manifest', help='Manifest path; default <directory>/manifest.json.')
        p = sub.add_parser('edit', help='Change attributes of one cover; files stay as imported.')
        p.add_argument('id', type=int)
        p.add_argument('--feature')
        p.add_argument('--year', type=int)
        p.add_argument('--alt')
        p.add_argument('--alt-ru', dest='alt_ru', help="Russian alt text; '' clears it.")
        p = sub.add_parser('remove', help='Delete one cover record and its files.')
        p.add_argument('id', type=int)
        p = sub.add_parser('show')
        p.add_argument('id', type=int)
        sub.add_parser('list')
        sub.add_parser('check', help='Verify files, feature bindings and orphan media files.')

    def handle(self, *args, **o):
        try:
            self.run(o)
        except (ValueError, KeyError, TypeError, OSError, ValidationError) as e:
            raise CommandError(str(e)) from e

    def run(self, o):
        action = o['action']
        if action == 'add':
            cover = covers.add(o['file'], feature=o['feature'], year=o['year'],
                               alt=o['alt'], alt_ru=o['alt_ru'])
            self.stdout.write('Added ' + describe(cover))
        elif action == 'import':
            directory = Path(o['directory'])
            manifest = Path(o['manifest']) if o['manifest'] else directory / 'manifest.json'
            entries = json.loads(manifest.read_text(encoding='utf-8'))
            if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
                raise ValueError('Manifest must be a JSON list of objects.')
            for entry in entries:
                if 'file' not in entry:
                    raise ValueError('Each manifest entry needs a "file".')
                entry['file'] = directory / entry['file']
            imported = covers.add_many(entries)
            for cover in imported:
                self.stdout.write('Added ' + describe(cover))
            self.stdout.write(f'Imported {len(imported)} covers.')
        elif action == 'edit':
            changes = {k: o[k] for k in ('feature', 'year', 'alt', 'alt_ru') if o[k] is not None}
            if not changes:
                raise ValueError('Nothing to change.')
            self.stdout.write('Updated ' + describe(covers.edit(o['id'], **changes)))
        elif action == 'remove':
            covers.remove(o['id'])
            self.stdout.write(f'Removed cover {o["id"]} and its files.')
        elif action == 'show':
            try:
                cover = PlaceCover.objects.get(pk=o['id'])
            except PlaceCover.DoesNotExist:
                raise ValueError(f'Cover {o["id"]} does not exist.') from None
            self.stdout.write(describe(cover))
            for kind, rel in covers.relative_paths(cover.sha256, cover.ext).items():
                self.stdout.write(f'\t{kind}: /media/{rel}')
        elif action == 'list':
            queryset = PlaceCover.objects.all()
            for cover in queryset:
                self.stdout.write(describe(cover))
            self.stdout.write(f'{queryset.count()} covers.')
        elif action == 'check':
            problems = covers.check()
            for line in problems:
                self.stdout.write(line)
            if problems:
                raise ValueError(f'{len(problems)} problems found.')
            self.stdout.write('Cover storage is consistent.')
