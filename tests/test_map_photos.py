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
class MapPhotosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 120, 'y': -80})
        # Три вершины: якорь миниатюры — средняя, а не конец дороги.
        line = Geometry.objects.create(key='g:road:02', shape={'type': 'line',
                                                               'points': [[0, 0], [50, 10], [100, 0]]})
        Feature.objects.create(key='12', object_type='site', name='Derry Public Library',
                               short='Library', kind='Civic', confidence='B', rank=2,
                               geometry=point, metadata={})
        Feature.objects.create(key='road:02', object_type='road', name='Main Street',
                               geometry=line, metadata={})
        Feature.objects.create(key='U3', object_type='unplaced', name='Juniper Hill',
                               confidence='U', metadata={})

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
        make_image(source / 'e.png', color=(130, 140, 150))
        # order у второго фото меньше — оно должно выйти первым.
        self.building = photos.add(source / 'a.png', caption='The library building.', feature='12',
                                   year=1958, order=2)
        self.ben = photos.add(source / 'b.png', caption='Ben at the library.', feature='12',
                              year=1958, order=1, characters=['ben-hanscom'])
        self.bill = photos.add(source / 'c.png', caption='Bill races Silver.', feature='road:02',
                               year=1958, characters=['bill-denbrough'])
        self.juniper = photos.add(source / 'd.png', caption='Juniper Hill, far upriver.', feature='U3')
        self.loose = photos.add(source / 'e.png', caption='Derry in 1985.', year=1985)

    def fetch(self):
        response = self.client.get('/api/v1/photos/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache')
        return response.json()['features']

    def test_photos_grouped_by_feature_with_order_and_thumbs(self):
        features = self.fetch()
        self.assertEqual(set(features), {'12', 'road:02', 'U3'})  # фото без привязки не попадает
        library = features['12']
        self.assertEqual(library['name'], 'Derry Public Library')
        self.assertEqual(library['object_type'], 'site')
        self.assertEqual([p['id'] for p in library['photos']], [self.ben.id, self.building.id])
        first = library['photos'][0]
        self.assertEqual(first['caption'], 'Ben at the library.')
        self.assertEqual(first['year'], 1958)
        self.assertEqual(first['thumb'],
                         '/media/' + photos.relative_paths(self.ben.sha256, self.ben.ext)['thumb'])

    def test_anchor_point_middle_vertex_and_absent_for_unplaced(self):
        features = self.fetch()
        self.assertEqual(features['12']['anchor'], [120, -80])
        # У дороги якорь — средняя вершина, а не конец.
        self.assertEqual(features['road:02']['anchor'], [50, 10])
        self.assertNotIn('anchor', features['U3'])

    def test_vanished_feature_is_skipped_not_an_error(self):
        # Правка атласа могла удалить место; сироту находит `photos check`,
        # а карта до починки просто не показывает такие фото.
        Feature.objects.filter(key='road:02').delete()
        features = self.fetch()
        self.assertEqual(set(features), {'12', 'U3'})

    def test_map_page_carries_photo_layer_and_toggle(self):
        response = self.client.get('/')
        self.assertContains(response, 'photoLayer')
        self.assertContains(response, 'showPhotos')

    def test_write_methods_rejected(self):
        self.assertEqual(self.client.post('/api/v1/photos/').status_code, 405)
