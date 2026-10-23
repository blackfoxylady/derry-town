"""Сквозные термины (редизайн, П3): уровни, категории, периоды и главы романа."""
import json
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import translation

from atlas import dataset as ds
from atlas.models import MapState
from atlas.terms import (CHAPTER_TITLES, INTERLUDE_TITLES, chapter_label, confidence_label,
                         kind_label, novel_references, parse_reference, period_label)


def initial_tables():
    return json.loads((settings.BASE_DIR / 'data/initial.json').read_text(encoding='utf-8'))['tables']


def glossary():
    return json.loads((settings.BASE_DIR / 'data/proper_names_ru.json').read_text(encoding='utf-8'))


class ReferenceTests(SimpleTestCase):
    def test_reference_forms(self):
        self.assertEqual(parse_reference('Ch. 4 - Ben Hanscom Takes a Fall / 4'), [(4, '4')])
        self.assertEqual(parse_reference('Ch. 4'), [(4, '')])
        self.assertEqual(parse_reference('Ch. 12; Ch. 19'), [(12, ''), (19, '')])
        self.assertEqual(parse_reference('Ch. 5 - Bill Denbrough Beats the Devil - I / 2'), [(5, '2')])
        self.assertEqual(parse_reference('Third Interlude'), [('Third Interlude', '')])
        # Позиции в тексте и неизвестные главы ссылками на главы не считаются.
        self.assertEqual(parse_reference('[1598, 1775, 2084]'), [])
        self.assertEqual(parse_reference('Ch. 40 - Nowhere'), [])

    def test_labels_in_both_languages(self):
        self.assertEqual(chapter_label(4, '4', russian=False), 'Ch. 4 · Ben Hanscom Takes a Fall · §4')
        self.assertEqual(chapter_label(4, '4', russian=True), 'Гл. 4 · Бен Хэнском падает · §4')
        self.assertEqual(chapter_label('First Interlude', russian=False), 'Derry: The First Interlude')
        self.assertEqual(chapter_label('First Interlude', russian=True), 'Дерри: первая интерлюдия')
        # Голая «Ch. N» получает название; повторы схлопываются; позиции отброшены.
        self.assertEqual(novel_references(['Ch. 10', 'Ch. 10', '[41, 66]'], russian=False),
                         ['Ch. 10 · The Reunion'])

    def test_every_reference_in_the_data_is_read(self):
        """Ни одна ссылка на главу из данных не теряется молча."""
        for evidence in initial_tables()['evidence']:
            reference = evidence['reference']
            if reference.startswith('['):
                continue
            self.assertTrue(parse_reference(reference), reference)

    def test_russian_chapter_titles_are_complete(self):
        chapters = glossary()['chapters']
        self.assertEqual(set(chapters), {str(n) for n in CHAPTER_TITLES} | set(INTERLUDE_TITLES))
        for title in chapters.values():
            self.assertIsNone(re.search(r'[A-Za-z]', title), title)


class PeriodTests(SimpleTestCase):
    def test_dash_and_translation(self):
        self.assertEqual(period_label('1957-58; 1985', russian=False), '1957–58; 1985')
        self.assertEqual(period_label('Winter 1957-58', russian=False), 'Winter 1957–58')
        self.assertEqual(period_label('Winter 1957-58', russian=True), 'зима 1957–58')
        self.assertEqual(period_label('1957; revisited 1985', russian=True), '1957; снова в 1985')
        self.assertEqual(period_label('1958; 1984-85', russian=True), '1958; 1984–85')
        self.assertEqual(period_label('', russian=True), '')

    def test_every_worded_period_has_a_russian_form(self):
        periods = glossary()['periods']
        for feature in initial_tables()['feature']:
            period = feature.get('period') or ''
            if re.search(r'[A-Za-z]', period):
                self.assertIn(period, periods)
                self.assertIsNone(re.search(r'[A-Za-z]', period_label(period, russian=True)), period)


class LabelTests(SimpleTestCase):
    def test_confidence_and_kinds(self):
        with translation.override('en'):
            self.assertEqual(confidence_label('A'), 'A · Named in the novel')
            self.assertEqual(str(kind_label('Civic', short=True)), 'Civic')
        with translation.override('ru'):
            self.assertEqual(confidence_label('B'), 'B · Выведено')
            self.assertEqual(confidence_label('U'), 'U · Без координат')
            self.assertEqual(str(kind_label('Civic')), 'Городские места')
            self.assertEqual(str(kind_label('Civic', short=True)), 'Город')
            self.assertEqual(str(kind_label('Historical', short=True)), 'Историческое')
            self.assertEqual(str(kind_label('Homes', short=True)), 'Дома')

    def test_tags_start_with_a_capital(self):
        for slug, name in glossary()['tags'].items():
            self.assertEqual(name[:1], name[:1].upper(), slug)
        self.assertEqual(glossary()['tags']['neibolt'], 'Нейболт-стрит')

    def test_why_paragraphs_drop_the_old_level_names(self):
        corpus = (settings.BASE_DIR / 'data/place_editorial.json').read_text(encoding='utf-8')
        for old in ('Text-anchored relationship', 'Inferred position', 'Proposed location',
                    'Связь, закреплённая текстом', 'Выведенное положение', 'Предлагаемое положение'):
            self.assertNotIn(old, corpus)


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MapPayloadTermsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        MapState.objects.get_or_create(pk=1)
        seed = json.loads((settings.BASE_DIR / 'data/initial.json').read_text())
        ds.commit(lambda _: seed, 'test', 'seed', seed=True)

    def test_payload_carries_chapter_labels_periods_and_aliases(self):
        with tempfile.TemporaryDirectory() as artifacts:
            with override_settings(ARTIFACT_ROOT=Path(artifacts)):
                en = self.client.get('/api/v1/map/').json()['data']
                ru = self.client.get('/api/v1/map/', {'lang': 'ru'}).json()['data']
        site_en = next(s for s in en['sites'] if s['id'] == 12)
        site_ru = next(s for s in ru['sites'] if s['id'] == 12)
        self.assertNotIn('sources', site_en)
        self.assertIn('Ch. 4 · Ben Hanscom Takes a Fall · §4', site_en['refs'])
        self.assertTrue(all(r.startswith('Гл. ') or r.startswith('Дерри:') for r in site_ru['refs']))
        # The English map finds a place by its Russian name too.
        self.assertIn('Публичная библиотека Дерри', site_en['search_aliases'])
        for group in ('sites', 'unplaced'):
            for item in en[group] + ru[group]:
                self.assertIsNone(re.search(r'\d-\d', item['period']), item['period'])
                self.assertFalse(any(r.startswith('[') for r in item['refs']))
                self.assertNotIn('reference', item)
        winter = next(s for s in ru['sites'] + ru['unplaced']
                      if 'зима' in s['period'] or 'июн' in s['period'])
        self.assertIsNone(re.search(r'[A-Za-z]', winter['period']))
