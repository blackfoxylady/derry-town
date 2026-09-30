from django.core.management.base import BaseCommand, CommandError

from atlas import dataset as ds
from atlas import editorial


class Command(BaseCommand):
    help = 'Export, validate and publish the human place-copy spreadsheet.'

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        export = sub.add_parser('export')
        export.add_argument('file')
        export.add_argument('--base-url', default='https://derryfiles.space')
        check = sub.add_parser('check')
        check.add_argument('file')
        apply = sub.add_parser('import')
        apply.add_argument('file')
        sync = sub.add_parser('sync')
        sync.add_argument('--author', default='editorial-corpus')
        sync.add_argument('--reason', default='Synchronize tracked place editorial corpus')
        sync.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        try:
            action = options['action']
            if action == 'export':
                doc, revision = ds.read_current()
                count = editorial.export_xlsx(options['file'], doc, revision,
                                              options['base_url'])
                self.stdout.write(f'Exported {count} places to {options["file"]}')
            elif action in ('check', 'import'):
                keys = editorial.import_xlsx(options['file'], write=action == 'import')
                verb = 'Imported' if action == 'import' else 'Valid'
                self.stdout.write(f'{verb}: {len(keys)} ready rows ({", ".join(keys)})')
            else:
                corpus = editorial.load_corpus()
                revision, result = ds.commit(
                    lambda doc: editorial.sync_document(doc, corpus),
                    options['author'], options['reason'], dry_run=options['dry_run'])
                self.stdout.write(f'Revision {revision}: {result}')
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
