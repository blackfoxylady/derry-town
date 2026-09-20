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
class SeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        Feature.objects.create(key='12', object_type='site', name='Derry Public Library',
                               short='Library', kind='Civic', confidence='B', rank=2,
                               geometry=point, metadata={})
        Feature.objects.create(key='U3', object_type='unplaced', name='Tracker Brothers',
                               confidence='U', metadata={})

    def test_sitemap_lists_pages_in_both_languages_with_hreflang(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben.', feature='12', year=1958)
                response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        body = response.content.decode()
        for path in ('/', '/ru/', '/photos/', '/method/', '/ru/method/',
                     '/places/12-derry-public-library/', '/ru/places/12-derry-public-library/',
                     '/places/u3-tracker-brothers/', f'/photos/{photo.id}/', f'/ru/photos/{photo.id}/'):
            self.assertIn(f'http://testserver{path}</loc>', body, path)
        self.assertIn('hreflang="ru" href="http://testserver/ru/places/12-derry-public-library/"', body)
        self.assertIn('hreflang="x-default"', body)

    def test_robots_txt_points_to_sitemap(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sitemap: http://testserver/sitemap.xml')
        self.assertContains(response, 'Disallow: /api/')

    def test_pages_carry_canonical_and_hreflang(self):
        response = self.client.get('/')
        self.assertContains(response, '<link rel="canonical" href="http://testserver/">')
        self.assertContains(response, 'hreflang="ru" href="http://testserver/ru/"')
        self.assertContains(response, '<meta name="description"')
        response = self.client.get('/ru/')
        self.assertContains(response, 'hreflang="en" href="http://testserver/"')
        # Canonical галереи не тащит query-параметры фильтров.
        response = self.client.get('/photos/', {'place': '12'})
        self.assertContains(response, '<link rel="canonical" href="http://testserver/photos/">')
