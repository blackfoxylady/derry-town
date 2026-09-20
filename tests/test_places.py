import tempfile
from pathlib import Path
from django.test import TestCase, override_settings
from atlas import photos
from atlas.models import Evidence, Feature, Geometry, Setting, Source

from .test_photos import make_image


# Обычное статическое хранилище: манифест whitenoise в тестах не собирается.
@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PlacePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        cls.library = Feature.objects.create(
            key='12', object_type='site', name='Derry Public Library', short='Library',
            kind='Civic', confidence='B', rank=2, period='1958', note='A stone building.',
            geometry=point, metadata={})
        cls.lost = Feature.objects.create(key='U3', object_type='unplaced',
                                          name='Tracker Brothers', confidence='U', metadata={})
        line = Geometry.objects.create(key='g:road:02', shape={'type': 'line', 'points': [[0, 0], [10, 0]]})
        Feature.objects.create(key='road:02', object_type='road', name='Main Street',
                               geometry=line, metadata={})
        book = Source.objects.create(key='novel', title='IT', kind='book')
        Evidence.objects.create(key='e1', feature=cls.library, source=book,
                                reference='Ch. 4 - Ben Hanscom / 1', note='Ben reads here.', order=1)
        Evidence.objects.create(key='e2', feature=cls.library, source=book,
                                reference='Ch. 4 - Ben Hanscom / 1', note='Second mention.', order=2)
        Setting.objects.create(key='atlas', value={'method_geometry': 'Canal length is inferred.'})
        Source.objects.create(key='w1', title='Old town maps', kind='web',
                              url='https://example.com/', role='Reference imagery.')

    def test_place_page_renders_texts_photos_free(self):
        response = self.client.get('/places/12-derry-public-library/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Derry Public Library')
        self.assertContains(response, 'A stone building.')
        self.assertContains(response, 'B · Inferred position')
        # Цитаты с одинаковым референсом группируются, как в карточке на карте.
        self.assertContains(response, 'Ch. 4 - Ben Hanscom / 1', count=1)
        self.assertContains(response, 'Ben reads here.')
        self.assertContains(response, 'Second mention.')
        self.assertContains(response, '/?place=12')

    def test_stale_or_bare_slug_redirects_to_canonical(self):
        for path in ('/places/12/', '/places/12-old-name/'):
            response = self.client.get(path)
            self.assertRedirects(response, '/places/12-derry-public-library/',
                                 status_code=301, msg_prefix=path)
        # Русская версия сохраняет префикс при редиректе.
        response = self.client.get('/ru/places/12/')
        self.assertRedirects(response, '/ru/places/12-derry-public-library/', status_code=301)

    def test_unplaced_place_page(self):
        response = self.client.get('/places/u3-tracker-brothers/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tracker Brothers')
        self.assertContains(response, 'Unlocated place')

    def test_only_sites_and_unplaced_get_pages(self):
        self.assertEqual(self.client.get('/places/99-nowhere/').status_code, 404)
        # У дорог и прочих контуров страницы нет (ключ с ':' не проходит слаг-конвертер).
        self.assertEqual(self.client.get('/places/road:02-main-street/').status_code, 404)

    def test_place_page_shows_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben at the library.', feature='12', year=1958)
                response = self.client.get('/places/12-derry-public-library/')
                self.assertContains(response, 'Ben at the library.')
                self.assertContains(response, f'/photos/{photo.id}/')
                self.assertContains(response, '/photos/?place=12')

    def test_method_page(self):
        response = self.client.get('/method/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Built from the novel')
        self.assertContains(response, 'Canal length is inferred.')
        self.assertContains(response, 'Old town maps')
        self.assertNotContains(response, 'https://example.com/derry')  # web-источники — только kind='web'
        response = self.client.get('/ru/method/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="ru"')

    def test_map_header_links_to_method_page(self):
        response = self.client.get('/')
        self.assertContains(response, 'href="/method/"')
        self.assertNotContains(response, '<dialog')

    def test_photo_page_links_to_place_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben at the library.', feature='12', year=1958)
                response = self.client.get(f'/photos/{photo.id}/')
                self.assertContains(response, '/places/12-derry-public-library/')
