import io
import json
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from atlas import dataset as ds, photos
from atlas.models import Evidence, Feature, Geometry, MapState, Setting, Source

from .test_photos import make_image


# Обычное статическое хранилище: манифест whitenoise в тестах не собирается.
@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class RuContentTests(TestCase):
    """Русские тексты из metadata['ru'] и caption_ru с фолбэком на английский."""

    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        cls.library = Feature.objects.create(
            key='12', object_type='site', name='Derry Public Library', short='Library',
            kind='Civic', confidence='B', rank=2, period='1958', note='A stone building.',
            about='The library is a civic landmark.',
            confidence_explanation='Its street relationship is inferred.', geometry=point,
            metadata={'ru': {'note': 'Каменное здание.', 'about': 'Библиотека — городской ориентир.',
                             'evidence': {'e1': 'Бен читает здесь.'}}})
        book = Source.objects.create(key='novel', title='IT', kind='book')
        Evidence.objects.create(key='e1', feature=cls.library, source=book,
                                reference='Ch. 4 - Ben Hanscom / 1', note='Ben reads here.', order=1)
        Evidence.objects.create(key='e2', feature=cls.library, source=book,
                                reference='Ch. 4 - Ben Hanscom / 1', note='Second mention.', order=2)
        Setting.objects.create(key='atlas', value={'method_geometry': 'Canal length is inferred.'})
        Setting.objects.create(key='i18n_ru', value={'method_geometry': 'Длина канала выведена.'})

    def test_place_page_russian_note_with_fallback(self):
        response = self.client.get('/ru/places/12-derry-public-library/')
        self.assertContains(response, 'Каменное здание.')
        self.assertContains(response, 'Бен читает здесь.')
        self.assertContains(response, 'Second mention.')  # без перевода — английский
        self.assertContains(response, 'Публичная библиотека Дерри')
        self.assertContains(response, 'Ch. 4 - Ben Hanscom / 1')  # главы — в оригинале
        self.assertContains(response, 'Библиотека — городской ориентир.')
        # Для отсутствующего русского поля действует поэлементный fallback на английский.
        self.assertContains(response, 'Its street relationship is inferred.')
        self.assertContains(response, 'О месте: Публичная библиотека Дерри')
        self.assertContains(response, 'Почему месту присвоен уровень B')
        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, 'A stone building.')
        self.assertContains(response, 'The library is a civic landmark.')
        self.assertNotContains(response, 'Каменное здание.')

    def test_place_names_are_localized_without_changing_canonical_urls(self):
        russian = self.client.get('/ru/places/12-derry-public-library/')
        self.assertContains(russian, '<h1>Публичная библиотека Дерри</h1>')
        self.assertContains(russian, 'Узнайте о месте «Публичная библиотека Дерри»')
        self.assertContains(
            russian,
            '<link rel="canonical" href="http://testserver/ru/places/12-derry-public-library/">')
        self.assertNotContains(russian, '/places/12-publichnaia-biblioteka-derri/')

        catalog = self.client.get('/ru/places/')
        self.assertContains(catalog, '>Публичная библиотека Дерри</a>')
        self.assertContains(
            catalog,
            'data-search="12 Derry Public Library Library Публичная библиотека Дерри')

        english = self.client.get('/places/12-derry-public-library/')
        self.assertContains(english, '<h1>Derry Public Library</h1>')
        self.assertNotContains(english, 'Публичная библиотека Дерри')

    def test_method_page_russian_geometry_note(self):
        self.assertContains(self.client.get('/ru/method/'), 'Длина канала выведена.')
        self.assertContains(self.client.get('/method/'), 'Canal length is inferred.')

    def test_photo_caption_ru_on_pages_and_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben at the library.',
                                   caption_ru='Бен в библиотеке.', feature='12', year=1958)
                self.assertContains(self.client.get(f'/ru/photos/{photo.id}/'), 'Бен в библиотеке.')
                self.assertContains(self.client.get(f'/photos/{photo.id}/'), 'Ben at the library.')
                self.assertContains(self.client.get('/ru/photos/'), 'Бен в библиотеке.')
                data = self.client.get('/api/v1/photos/', {'lang': 'ru'}).json()
                self.assertEqual(data['features']['12']['photos'][0]['caption'], 'Бен в библиотеке.')
                data = self.client.get('/api/v1/photos/').json()
                self.assertEqual(data['features']['12']['photos'][0]['caption'], 'Ben at the library.')
                # Правка перевода без пересоздания записи.
                photos.edit(photo.id, caption_ru='Бен читает.')
                self.assertContains(self.client.get(f'/ru/photos/{photo.id}/'), 'Бен читает.')


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AtlasEditRuTests(TestCase):
    """Полный контур: atlas edit --description-ru → ревизия → /api/v1/map/?lang=ru."""

    @classmethod
    def setUpTestData(cls):
        MapState.objects.get_or_create(pk=1)
        seed = json.loads((settings.BASE_DIR / 'data/initial.json').read_text())
        ds.commit(lambda _: seed, 'test', 'seed', seed=True)

    def cmd(self, *args):
        out = io.StringIO()
        call_command('atlas', *args, stdout=out)
        return out.getvalue()

    def test_description_ru_flows_into_localized_map_payload(self):
        self.cmd('edit', '12', '--description-ru', 'Русское описание библиотеки.',
                 '--author', 'dev', '--reason', 'ru note')
        self.assertEqual(Feature.objects.get(pk='12').metadata['ru']['note'],
                         'Русское описание библиотеки.')
        with tempfile.TemporaryDirectory() as artifacts:
            with override_settings(ARTIFACT_ROOT=Path(artifacts)):
                en = self.client.get('/api/v1/map/')
                ru = self.client.get('/api/v1/map/', {'lang': 'ru'})
        self.assertNotEqual(en['ETag'], ru['ETag'])
        site_en = next(s for s in en.json()['data']['sites'] if s['id'] == 12)
        site_ru = next(s for s in ru.json()['data']['sites'] if s['id'] == 12)
        self.assertEqual(site_ru['note'], 'Русское описание библиотеки.')
        self.assertNotEqual(site_en['note'], site_ru['note'])
        # Основная карта переводится отдельным этапом; её payload пока сохраняет каноническое имя.
        self.assertEqual(site_en['name'], site_ru['name'])

    def test_shipped_translation_patch_applies_cleanly(self):
        self.cmd('apply', str(settings.BASE_DIR / 'data/i18n_ru.json'),
                 '--author', 'dev', '--reason', 'ru corpus')
        feature = Feature.objects.get(pk='12')
        self.assertIn('стеклянный переход', feature.metadata['ru']['note'])
        self.assertTrue(feature.note.startswith('At Kansas Street'))  # canonical не тронут
        self.assertIn('водонапорную башню',
                      Setting.objects.get(pk='i18n_ru').value['method_geometry'])
        self.assertContains(self.client.get('/ru/places/12-derry-public-library/'),
                            'стеклянный переход')
        school = Feature.objects.get(pk='4')
        self.assertTrue(school.metadata['ru']['about'].startswith('Начальная школа Дерри —'))
        self.assertIn('точный земельный участок',
                      school.metadata['ru']['confidence_explanation'])
        school_page = self.client.get('/ru/places/4-derry-elementary-school/')
        self.assertContains(school_page, 'О месте: начальная школа Дерри')
        self.assertContains(school_page, 'общественный ориентир')
        self.assertContains(school_page, 'Почему месту присвоен уровень A')
        self.assertContains(self.client.get('/ru/method/'), 'водонапорную башню')
        self.assertContains(self.client.get('/method/'), 'Standpipe')  # английская без изменений

        translated = json.dumps(
            [item['values'] for item in json.loads(
                (settings.BASE_DIR / 'data/i18n_ru.json').read_text(encoding='utf-8'))],
            ensure_ascii=False)
        for english_name in ('Witcham Street', 'Beverly Marsh', 'Zack Denbrough',
                             'Mrs Kersh', 'Kenduskeag', 'Matthew Clements',
                             'Bullseye', 'Penobscot'):
            self.assertNotIn(english_name, translated)

    def test_clearing_description_ru_removes_metadata_key(self):
        self.cmd('edit', '12', '--description-ru', 'Черновик.', '--author', 'dev', '--reason', 'set')
        self.cmd('edit', '12', '--description-ru', '', '--author', 'dev', '--reason', 'clear')
        self.assertEqual(Feature.objects.get(pk='12').metadata, {})

    def test_edit_place_content_in_both_languages_and_clear_translation(self):
        self.cmd('edit', '12', '--about', 'English overview.',
                 '--confidence-explanation', 'English placement explanation.',
                 '--about-ru', 'Русская справка.',
                 '--confidence-explanation-ru', 'Русское объяснение привязки.',
                 '--author', 'dev', '--reason', 'place content')
        feature = Feature.objects.get(pk='12')
        self.assertEqual(feature.about, 'English overview.')
        self.assertEqual(feature.confidence_explanation, 'English placement explanation.')
        self.assertEqual(feature.metadata['ru']['about'], 'Русская справка.')
        self.assertEqual(feature.metadata['ru']['confidence_explanation'],
                         'Русское объяснение привязки.')

        self.cmd('edit', '12', '--about-ru', '', '--confidence-explanation-ru', '',
                 '--author', 'dev', '--reason', 'clear translated place content')
        feature.refresh_from_db()
        self.assertNotIn('about', feature.metadata.get('ru', {}))
        self.assertNotIn('confidence_explanation', feature.metadata.get('ru', {}))
