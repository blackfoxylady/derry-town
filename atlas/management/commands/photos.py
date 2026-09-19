import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from atlas import photos
from atlas.models import Photo


def describe(photo):
    marks = [f'#{photo.id}', photo.original_name, f'sha256={photo.sha256[:12]}…']
    if photo.feature_key:
        marks.append(f'feature={photo.feature_key}')
    if photo.year:
        marks.append(str(photo.year))
    people = ','.join(photo.characters.values_list('slug', flat=True))
    tags = ','.join(photo.tags.values_list('slug', flat=True))
    if people:
        marks.append(f'characters={people}')
    if tags:
        marks.append(f'tags={tags}')
    if photo.order:
        marks.append(f'order={photo.order}')
    return '\t'.join(marks) + ('\n\t' + photo.caption if photo.caption else '')


class Command(BaseCommand):
    help = 'Photo storage operations: files in media plus DB records, outside atlas revisions.'

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        p = sub.add_parser('add', help='Import one photo file.')
        p.add_argument('file')
        p.add_argument('--caption', default='')
        p.add_argument('--feature', default='')
        p.add_argument('--year', type=int)
        p.add_argument('--character', action='append', default=[], dest='characters')
        p.add_argument('--tag', action='append', default=[], dest='tags')
        p.add_argument('--order', type=int, default=0)
        p = sub.add_parser('import', help='Import a directory using a JSON manifest (all or nothing).')
        p.add_argument('directory')
        p.add_argument('--manifest', help='Manifest path; default <directory>/manifest.json.')
        p = sub.add_parser('edit', help='Change attributes of one photo; files stay as imported.')
        p.add_argument('id', type=int)
        p.add_argument('--caption')
        p.add_argument('--feature', help="Feature key; '' detaches the photo.")
        p.add_argument('--year', type=int)
        p.add_argument('--character', action='append', dest='characters',
                       help="Repeatable; replaces the whole set. Use --no-characters to clear.")
        p.add_argument('--tag', action='append', dest='tags',
                       help="Repeatable; replaces the whole set. Use --no-tags to clear.")
        p.add_argument('--no-characters', action='store_true')
        p.add_argument('--no-tags', action='store_true')
        p.add_argument('--order', type=int)
        p = sub.add_parser('remove', help='Delete one photo record and its files.')
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
            photo = photos.add(o['file'], caption=o['caption'], feature=o['feature'], year=o['year'],
                               characters=o['characters'], tags=o['tags'], order=o['order'])
            self.stdout.write('Added ' + describe(photo))
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
            imported = photos.add_many(entries)
            for photo in imported:
                self.stdout.write('Added ' + describe(photo))
            self.stdout.write(f'Imported {len(imported)} photos.')
        elif action == 'edit':
            changes = {k: o[k] for k in ('caption', 'feature', 'year', 'characters', 'tags', 'order')
                       if o[k] is not None}
            if o['no_characters']:
                changes['characters'] = []
            if o['no_tags']:
                changes['tags'] = []
            if not changes:
                raise ValueError('Nothing to change.')
            self.stdout.write('Updated ' + describe(photos.edit(o['id'], **changes)))
        elif action == 'remove':
            photos.remove(o['id'])
            self.stdout.write(f'Removed photo {o["id"]} and its files.')
        elif action == 'show':
            try:
                photo = Photo.objects.get(pk=o['id'])
            except Photo.DoesNotExist:
                raise ValueError(f'Photo {o["id"]} does not exist.') from None
            self.stdout.write(describe(photo))
            for kind, rel in photos.relative_paths(photo.sha256, photo.ext).items():
                self.stdout.write(f'\t{kind}: /media/{rel}')
        elif action == 'list':
            queryset = Photo.objects.prefetch_related('characters', 'tags')
            for photo in queryset:
                self.stdout.write(describe(photo))
            self.stdout.write(f'{queryset.count()} photos.')
        elif action == 'check':
            problems = photos.check()
            for line in problems:
                self.stdout.write(line)
            if problems:
                raise ValueError(f'{len(problems)} problems found.')
            self.stdout.write('Photo storage is consistent.')
