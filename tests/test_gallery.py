import tempfile
from pathlib import Path
from django.test import TestCase, override_settings
from atlas import photos
from atlas.models import Feature, Geometry

from .test_photos import make_image


# Обычное статическое хранилище: манифест whitenoise в тестах не собирается.
@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class GalleryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        line = Geometry.objects.create(key='g:road:02', shape={'type': 'line', 'points': [[0, 0], [10, 0]]})
        Feature.objects.create(key='12', object_type='site', name='Derry Public Library',
                               short='Library', kind='Civic', confidence='B', rank=2,
                               geometry=point, metadata={})
        Feature.objects.create(key='road:02', object_type='road', name='Main Street',
                               geometry=line, metadata={})

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        self.settings_override = override_settings(MEDIA_ROOT=root / 'media')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        source = root / 'incoming'
        # Разные цвета — разные SHA-256, иначе add() отбросит дубликаты.
        make_image(source / 'a.png', color=(10, 20, 30))
        make_image(source / 'b.png', color=(40, 50, 60))
        make_image(source / 'c.png', color=(70, 80, 90))
        make_image(source / 'd.png', color=(100, 110, 120))
        self.ben = photos.add(source / 'a.png', caption='Ben at the library.', feature='12',
                              year=1958, characters=['ben-hanscom'], tags=['library', 'interior'])
        self.building = photos.add(source / 'b.png', caption='The library building.', feature='12',
                                   year=1958, tags=['library', 'architecture'])
        self.bill = photos.add(source / 'c.png', caption='Bill races Silver.', feature='road:02',
                               year=1958, characters=['bill-denbrough'], tags=['silver'])
        self.loose = photos.add(source / 'd.png', caption='Derry in 1985.', year=1985)

    def captions(self, response):
        return [c for c in ('Ben at the library.', 'The library building.',
                            'Bill races Silver.', 'Derry in 1985.')
                if c.encode() in response.content]

    def test_gallery_lists_all_photos_with_thumbs_and_filter_panel(self):
        response = self.client.get('/photos/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache')
        self.assertEqual(len(self.captions(response)), 4)
        self.assertContains(response, photos.relative_paths(self.ben.sha256, self.ben.ext)['thumb'])
        self.assertContains(response, f'/photos/{self.ben.id}/')
        self.assertContains(response, 'Derry Public Library')
        self.assertContains(response, 'Ben Hanscom')
        self.assertContains(response, '4 photographs')
        # Год показан: в наборе два разных года.
        self.assertContains(response, '?year=1985')

    def test_place_filter_and_readable_url(self):
        response = self.client.get('/photos/', {'place': '12'})
        self.assertEqual(self.captions(response), ['Ben at the library.', 'The library building.'])
        self.assertContains(response, 'Clear filters')
        response = self.client.get('/photos/', {'place': 'road:02'})
        self.assertEqual(self.captions(response), ['Bill races Silver.'])
        # Ключ дороги в собранных ссылках остаётся читабельным.
        self.assertContains(self.client.get('/photos/'), '?place=road:02')

    def test_character_filter(self):
        response = self.client.get('/photos/', {'character': 'ben-hanscom'})
        self.assertEqual(self.captions(response), ['Ben at the library.'])

    def test_tags_are_any_of_and_deduplicated(self):
        response = self.client.get('/photos/', {'tag': 'library,silver'})
        self.assertEqual(self.captions(response),
                         ['Ben at the library.', 'The library building.', 'Bill races Silver.'])
        self.assertContains(response, '3 photographs')
        # Фото с обоими тегами не задваивается.
        response = self.client.get('/photos/', {'tag': 'library,interior'})
        self.assertContains(response, '2 photographs')
        # Ссылка-переключатель второго тега дописывает его через запятую.
        response = self.client.get('/photos/', {'tag': 'library'})
        self.assertContains(response, '?tag=library,interior')

    def test_dimensions_combine_as_and(self):
        response = self.client.get('/photos/', {'place': '12', 'tag': 'interior', 'year': '1958'})
        self.assertEqual(self.captions(response), ['Ben at the library.'])
        response = self.client.get('/photos/', {'place': '12', 'character': 'bill-denbrough'})
        self.assertEqual(self.captions(response), [])

    def test_unknown_or_invalid_values_give_empty_result_not_error(self):
        for params in ({'tag': 'no-such-tag'}, {'place': '999'}, {'character': 'pennywise'},
                       {'year': '1929'}, {'year': 'abc'}):
            response = self.client.get('/photos/', params)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'No photographs match')
            self.assertContains(response, 'Clear filters')

    def test_photo_page_shows_attributes_as_filter_links(self):
        response = self.client.get(f'/photos/{self.ben.id}/')
        self.assertEqual(response.status_code, 200)
        rel = photos.relative_paths(self.ben.sha256, self.ben.ext)
        self.assertContains(response, rel['medium'])
        self.assertContains(response, rel['original'])
        self.assertContains(response, 'Ben at the library.')
        self.assertContains(response, '?character=ben-hanscom')
        self.assertContains(response, '?tag=library')
        self.assertContains(response, '?place=12')
        self.assertContains(response, '?year=1958')
        self.assertContains(response, '/?place=12')  # место-точка: есть переход на карту

    def test_photo_page_map_link_only_for_sites(self):
        response = self.client.get(f'/photos/{self.bill.id}/')
        self.assertContains(response, '?place=road:02')  # фильтр галереи остаётся
        self.assertNotContains(response, 'Show on the map')  # у дороги нет маркера на карте
        response = self.client.get(f'/photos/{self.loose.id}/')
        self.assertNotContains(response, 'Place')  # без привязки нет и блока места

    def test_missing_photo_and_write_methods(self):
        self.assertEqual(self.client.get('/photos/999/').status_code, 404)
        self.assertEqual(self.client.post('/photos/').status_code, 405)
        self.assertEqual(self.client.post(f'/photos/{self.ben.id}/').status_code, 405)
