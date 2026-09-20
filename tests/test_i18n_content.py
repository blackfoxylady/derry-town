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
            geometry=point,
            metadata={'ru': {'note': 'Каменное здание.', 'evidence': {'e1': 'Бен читает здесь.'}}})
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
        self.assertContains(response, 'Derry Public Library')  # названия не переводятся
        self.assertContains(response, 'Ch. 4 - Ben Hanscom / 1')  # главы — в оригинале
        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, 'A stone building.')
        self.assertNotContains(response, 'Каменное здание.')

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
        self.assertEqual(site_en['name'], site_ru['name'])  # названия не переводятся

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
        self.assertContains(self.client.get('/ru/method/'), 'водонапорную башню')
        self.assertContains(self.client.get('/method/'), 'Standpipe')  # английская без изменений

    def test_clearing_description_ru_removes_metadata_key(self):
        self.cmd('edit', '12', '--description-ru', 'Черновик.', '--author', 'dev', '--reason', 'set')
        self.cmd('edit', '12', '--description-ru', '', '--author', 'dev', '--reason', 'clear')
        self.assertEqual(Feature.objects.get(pk='12').metadata, {})
