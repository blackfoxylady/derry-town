import json
import tempfile
from pathlib import Path
from django.test import TestCase, override_settings
from atlas import photos
from atlas.models import Feature, Geometry

from .test_photos import make_image


def jsonld(response):
    """JSON-LD страницы: содержимое первого <script type="application/ld+json">."""
    body = response.content.decode()
    marker = '<script type="application/ld+json">'
    start = body.index(marker) + len(marker)
    return json.loads(body[start:body.index('</script>', start)])


def node(data, node_type):
    """Узел @graph заданного типа (тип может быть строкой или списком)."""
    for n in data['@graph']:
        types = n['@type'] if isinstance(n['@type'], list) else [n['@type']]
        if node_type in types:
            return n
    raise AssertionError(f'No {node_type} node in {data}')


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

    def test_pages_carry_open_graph_tags(self):
        response = self.client.get('/')
        self.assertContains(response, '<meta property="og:image" content="http://testserver/static/atlas/og-map.jpg">')
        self.assertContains(response, '<meta property="og:url" content="http://testserver/">')
        self.assertContains(response, '<meta property="og:locale" content="en_US">')
        self.assertContains(response, '<meta name="twitter:card" content="summary_large_image">')
        self.assertContains(self.client.get('/ru/'), '<meta property="og:locale" content="ru_RU">')
        # Без фото страница места подставляет общую карту.
        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, '<meta property="og:title" content="Derry Public Library · Derry">')
        self.assertContains(response, 'og-map.jpg')

    def test_photo_pages_use_the_photo_as_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben.', feature='12', year=1958)
                response = self.client.get(f'/photos/{photo.id}/')
                self.assertContains(response, '<meta property="og:image" content="http://testserver/media/')
                self.assertContains(response, '<meta property="og:title" content="Ben. · Derry">')
                # Страница места берёт первое фото места.
                response = self.client.get('/places/12-derry-public-library/')
                self.assertContains(response, '<meta property="og:image" content="http://testserver/media/')


# Обычное статическое хранилище: манифест whitenoise в тестах не собирается.
@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class JsonLdTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        Feature.objects.create(key='12', object_type='site', name='Derry Public Library',
                               short='Library', kind='Civic', confidence='B', rank=2,
                               period='1958', geometry=point, metadata={})

    def test_every_page_carries_website_and_book(self):
        for path in ('/', '/photos/', '/method/', '/places/12-derry-public-library/'):
            data = jsonld(self.client.get(path))
            self.assertEqual(data['@context'], 'https://schema.org', path)
            website = node(data, 'WebSite')
            self.assertEqual(website['url'], 'http://testserver/')
            self.assertEqual(website['about'], {'@id': 'http://testserver/#book'})
            book = node(data, 'Book')
            self.assertEqual(book['author']['name'], 'Stephen King')
            self.assertEqual(book['datePublished'], '1986')

    def test_index_is_a_map_in_the_page_language(self):
        page = node(jsonld(self.client.get('/')), 'Map')
        self.assertEqual(page['url'], 'http://testserver/')
        self.assertEqual(page['inLanguage'], 'en')
        self.assertEqual(page['about'], {'@id': 'http://testserver/#book'})
        page = node(jsonld(self.client.get('/ru/')), 'Map')
        self.assertEqual(page['url'], 'http://testserver/ru/')
        self.assertEqual(page['inLanguage'], 'ru')

    def test_gallery_and_method_pages(self):
        gallery = node(jsonld(self.client.get('/photos/')), 'ImageGallery')
        self.assertEqual(gallery['url'], 'http://testserver/photos/')
        self.assertIn('CollectionPage', gallery['@type'])
        method = node(jsonld(self.client.get('/method/')), 'WebPage')
        self.assertEqual(method['about'], {'@id': 'http://testserver/#book'})

    def test_place_page_is_article_with_breadcrumbs(self):
        data = jsonld(self.client.get('/places/12-derry-public-library/'))
        article = node(data, 'Article')
        self.assertEqual(article['headline'], 'Derry Public Library')
        self.assertEqual(article['temporalCoverage'], '1958')
        self.assertEqual(article['about'], {'@id': 'http://testserver/#book'})
        crumbs = node(data, 'BreadcrumbList')['itemListElement']
        self.assertEqual([c['position'] for c in crumbs], [1, 2])
        self.assertEqual(crumbs[0]['item'], 'http://testserver/')
        self.assertEqual(crumbs[1]['name'], 'Derry Public Library')
        self.assertNotIn('item', crumbs[1])

    def test_photo_page_is_an_image_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben & Bill.', feature='12',
                                   year=1958, characters=['ben'], tags=['library'])
                response = self.client.get(f'/photos/{photo.id}/')
        data = jsonld(response)
        image = node(data, 'ImageObject')
        self.assertEqual(image['url'], f'http://testserver/photos/{photo.id}/')
        self.assertTrue(image['contentUrl'].startswith('http://testserver/media/'))
        self.assertEqual((image['width'], image['height']), (1200, 800))
        self.assertEqual(image['caption'], 'Ben & Bill.')
        self.assertEqual(image['temporalCoverage'], '1958')
        self.assertEqual(image['creator'], {'@type': 'Organization', 'name': 'Derry',
                                            'url': 'http://testserver/'})
        self.assertEqual(image['creditText'], 'Derry')
        self.assertEqual(image['keywords'], 'Ben, library')
        crumbs = node(data, 'BreadcrumbList')['itemListElement']
        self.assertEqual(crumbs[1]['item'], 'http://testserver/photos/')
        self.assertEqual(crumbs[2]['name'], 'Ben & Bill.')
        # Спецсимволы экранируются, как в json_script: сырых <, >, & в блоке нет.
        body = response.content.decode()
        marker = '<script type="application/ld+json">'
        start = body.index(marker) + len(marker)
        block = body[start:body.index('</script>', start)]
        for raw in '<>&':
            self.assertNotIn(raw, block)

    def test_place_page_uses_the_first_photo_as_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photos.add(root / 'a.png', caption='Ben.', feature='12', year=1958)
                response = self.client.get('/places/12-derry-public-library/')
        article = node(jsonld(response), 'Article')
        self.assertTrue(article['image'].startswith('http://testserver/media/'))
