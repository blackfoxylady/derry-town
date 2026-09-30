import json
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.test import TestCase

from atlas import dataset as ds
from atlas import editorial
from atlas.models import Feature, MapState


class EditorialWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        MapState.objects.get_or_create(pk=1)
        seed = json.loads((settings.BASE_DIR / 'data/initial.json').read_text(encoding='utf-8'))
        ds.commit(lambda _: seed, 'test', 'seed', seed=True)

    def test_tracked_corpus_syncs_in_one_revision_and_preserves_other_metadata(self):
        feature = Feature.objects.get(pk='3')
        feature.metadata = {'source_marker': 'keep', 'ru': {'evidence': {'e:3:0': 'Перевод.'}}}
        feature.save(update_fields=['metadata'])

        before = MapState.objects.get(pk=1).revision_id
        revision, result = ds.commit(editorial.sync_document, 'test', 'editorial sync')

        self.assertEqual(result, 'committed')
        self.assertNotEqual(revision, before)
        feature.refresh_from_db()
        self.assertEqual(feature.metadata['source_marker'], 'keep')
        self.assertEqual(feature.metadata['ru']['evidence'], {'e:3:0': 'Перевод.'})
        self.assertIn('Её часы', feature.metadata['ru']['note'])
        self.assertIn('Баптистская церковь «Благодать»', feature.metadata['ru']['about'])

        same_revision, result = ds.commit(editorial.sync_document, 'test', 'repeat sync')
        self.assertEqual((same_revision, result), (revision, 'no changes'))

    def test_fixed_examples_and_titles_pass_editorial_checks(self):
        corpus = editorial.load_corpus()['places']
        for key in ('3', 'U9'):
            entry = corpus[key]
            self.assertEqual(
                editorial.diagnostics(entry['name_ru'], entry['note_ru'], entry['about_ru'],
                                      entry['confidence_explanation_ru']), '')
        self.assertIn('Денниса Торрио', corpus['U9']['about_ru'])
        self.assertIn('Джорджи', corpus['U9']['about_ru'])
        self.assertIn('Майк', corpus['U9']['about_ru'])
        self.assertIn('U5', corpus)  # опубликованная БД
        self.assertIn('84', corpus)  # свежая установка из initial.json
        self.assertFalse(any(value['name_ru'][:1].islower() for value in corpus.values()))

    def test_every_tracked_place_passes_editorial_checks(self):
        corpus = editorial.load_corpus()['places']
        issues = {
            key: editorial.diagnostics(
                entry['name_ru'], entry['note_ru'], entry['about_ru'],
                entry['confidence_explanation_ru'],
            )
            for key, entry in corpus.items()
        }
        self.assertEqual({key: issue for key, issue in issues.items() if issue}, {})

    def test_sync_accepts_published_legacy_cycle_shoppe_key(self):
        document = {'tables': {'feature': [{
            'key': 'U5', 'object_type': 'unplaced', 'about': '',
            'confidence_explanation': '', 'metadata': {},
        }]}}
        editorial.sync_document(document)
        feature = document['tables']['feature'][0]
        self.assertTrue(feature['about'].startswith('The Bike and Cycle Shoppe'))
        self.assertEqual(feature['metadata']['ru']['note'][:5], 'Здесь')
        self.assertNotRegex(feature['metadata']['ru']['about'], r'[A-Za-z]{2,}')

    def test_xlsx_round_trip_selects_only_ready_rows(self):
        doc, revision = ds.read_current()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'places.xlsx'
            self.assertEqual(editorial.export_xlsx(path, doc, revision), 92)
            rows = editorial.read_xlsx_rows(path)
            self.assertEqual(len(rows), 92)
            self.assertEqual(rows[2]['ID'], '3')
            self.assertEqual(rows[2]['Название RU'], 'Баптистская церковь «Благодать»')

            rewritten = Path(temporary) / 'ready.xlsx'
            with ZipFile(path) as source, ZipFile(rewritten, 'w', ZIP_DEFLATED) as target:
                for item in source.infolist():
                    payload = source.read(item.filename)
                    if item.filename == 'xl/worksheets/sheet2.xml':
                        text = payload.decode('utf-8')
                        marker = '<c r="K4" t="inlineStr" s="3"><is><t>черновик</t></is></c>'
                        self.assertIn(marker, text)
                        payload = text.replace(marker, marker.replace('черновик', 'готово')).encode()
                    target.writestr(item, payload)
            self.assertEqual(editorial.import_xlsx(rewritten, write=False), ['3'])

    def test_diagnostics_reject_lowercase_and_latin_words(self):
        issue = editorial.diagnostics('дом', 'Здесь Bill.', 'Текст.', 'Уровень A.')
        self.assertIn('строчной', issue)
        self.assertIn('Bill', issue)
