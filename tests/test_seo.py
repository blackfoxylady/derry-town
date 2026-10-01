import json
import tempfile
from pathlib import Path
from xml.etree import ElementTree
from django.test import TestCase, override_settings
from atlas import photos
from atlas.models import Feature, Geometry, MapState, Revision

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
        revision = Revision.objects.create(
            author='test', reason='published', before={}, digest='x' * 64,
            after={'tables': {'feature': [{'key': '12'}, {'key': 'U3'}]}})
        MapState.objects.update_or_create(
            pk=1, defaults={'initialized': True, 'revision': revision})

    def test_sitemap_lists_pages_in_both_languages_with_hreflang(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben.', feature='12', year=1958,
                                   characters=['ben-hanscom'], tags=['library'])
                response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        body = response.content.decode()
        for path in ('/', '/ru/', '/places/', '/ru/places/', '/photos/', '/method/', '/ru/method/',
                     '/is-derry-maine-real/', '/ru/is-derry-maine-real/',
                     '/how-bangor-inspired-derry-maine/',
                     '/ru/how-bangor-inspired-derry-maine/',
                     '/books-set-in-derry-maine/', '/ru/books-set-in-derry-maine/',
                     '/printable-derry-map/', '/ru/printable-derry-map/',
                     '/places/12-derry-public-library/', '/ru/places/12-derry-public-library/',
                     '/places/u3-tracker-brothers/', f'/photos/{photo.id}/', f'/ru/photos/{photo.id}/',
                     '/photos/place/12-derry-public-library/',
                     '/photos/character/ben-hanscom/', '/photos/tag/library/',
                     '/photos/year/1958/', '/ru/photos/year/1958/'):
            self.assertIn(f'http://testserver{path}</loc>', body, path)
        self.assertIn('hreflang="ru" href="http://testserver/ru/places/12-derry-public-library/"', body)
        self.assertIn('hreflang="x-default"', body)
        self.assertIn('xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"', body)
        root = ElementTree.fromstring(body)
        namespaces = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9',
                      'image': 'http://www.google.com/schemas/sitemap-image/1.1'}
        indexed = {item.find('s:loc', namespaces).text: item for item in root.findall('s:url', namespaces)}
        self.assertEqual(body.count('<lastmod>'), len(indexed))
        for url in (f'http://testserver/photos/{photo.id}/',
                    'http://testserver/places/12-derry-public-library/',
                    'http://testserver/photos/place/12-derry-public-library/',
                    'http://testserver/photos/character/ben-hanscom/',
                    'http://testserver/photos/tag/library/',
                    'http://testserver/photos/year/1958/'):
            image = indexed[url].find('image:image/image:loc', namespaces)
            self.assertIsNotNone(image, url)
            self.assertIn('/media/photos/original/', image.text)
        fallback = indexed['http://testserver/places/u3-tracker-brothers/'].find(
            'image:image/image:loc', namespaces)
        self.assertEqual(fallback.text, 'http://testserver/static/atlas/og-map.jpg')

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
        for path in ('/is-derry-maine-real/', '/how-bangor-inspired-derry-maine/',
                     '/books-set-in-derry-maine/', '/printable-derry-map/'):
            response = self.client.get(path)
            self.assertContains(response, f'<link rel="canonical" href="http://testserver{path}">')
            self.assertContains(response, f'hreflang="ru" href="http://testserver/ru{path}"')
            russian = self.client.get('/ru' + path)
            self.assertContains(russian, f'hreflang="en" href="http://testserver{path}"')

    def test_google_verification_and_single_content_heading(self):
        verification = '<meta name="google-site-verification" content="PQSwf6jyMi2X-8WbazpZT47x4vm7KZqvt-KBrnmpiH0">'
        self.assertContains(self.client.get('/'), verification)
        self.assertContains(self.client.get('/photos/'), verification)
        self.assertContains(self.client.get('/photos/'), '<h1 class="gallery-title">Photographs</h1>')
        self.assertContains(self.client.get('/places/12-derry-public-library/'), '<h1', count=1)

    def test_pages_carry_open_graph_tags(self):
        response = self.client.get('/')
        self.assertContains(response, '<meta property="og:image" content="http://testserver/static/atlas/og-map.jpg">')
        self.assertContains(response, '<meta property="og:url" content="http://testserver/">')
        self.assertContains(response, '<meta property="og:locale" content="en_US">')
        self.assertContains(response, '<meta name="twitter:card" content="summary_large_image">')
        self.assertContains(self.client.get('/ru/'), '<meta property="og:locale" content="ru_RU">')
        # Без фото страница места подставляет общую карту.
        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, '<meta property="og:title" content="Derry Public Library — Derry, Maine · Stephen King’s IT">')
        self.assertContains(response, 'og-map.jpg')

    def test_approved_seo_templates_and_dynamic_place_count(self):
        response = self.client.get('/')
        self.assertContains(
            response, '<title>Map of Derry, Maine — Stephen King’s IT Literary Atlas</title>')
        self.assertContains(
            response, 'the fictional town in Stephen King’s IT, with 1 mapped place, '
                      'book evidence and photographs.')
        self.assertNotContains(response, '83 mapped places')

        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(
            response, '<title>Derry Public Library — Derry, Maine · Stephen King’s IT</title>')
        self.assertContains(
            response, 'Explore Derry Public Library in Derry, Maine: its location, book evidence '
                      'and mapping confidence in this literary atlas of Stephen King’s IT.')

        response = self.client.get('/photos/')
        self.assertContains(
            response, '<title>Photographs of Derry, Maine — Stephen King’s IT</title>')
        self.assertContains(response, 'with filters by place, character, tag and year.')

        response = self.client.get('/method/')
        self.assertContains(
            response,
            '<title>Mapping Derry, Maine — Sources &amp; Method · Stephen King’s IT</title>')
        self.assertContains(
            response, 'including sources, evidence, confidence levels and mapping decisions.')

    def test_editorial_hubs_have_approved_titles_descriptions_and_sources(self):
        cases = (
            ('/is-derry-maine-real/',
             'Is Derry, Maine Real? Stephen King’s Fictional Town Explained',
             'Derry, Maine is fictional.', 'Is Derry, Maine a real town?'),
            ('/how-bangor-inspired-derry-maine/',
             'How Bangor Inspired Derry, Maine — Stephen King’s IT',
             'Compare fictional Derry with Bangor, Maine:',
             'How Bangor inspired Derry, Maine'),
            ('/books-set-in-derry-maine/',
             'Stephen King Books Set in Derry, Maine — A Spoiler-Light Guide',
             'A spoiler-light guide to Stephen King books',
             'Stephen King books set in Derry, Maine'),
        )
        for path, title, description, heading in cases:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'<title>{title}</title>', html=True)
            self.assertContains(response, description)
            self.assertContains(response, f'<h1>{heading}</h1>', html=True)
            self.assertContains(response, '<h1', count=1)
            self.assertContains(response, '<meta property="og:type" content="article">')
            self.assertContains(response, '<meta property="article:published_time" content="2026-09-29">')
            self.assertContains(response, 'target="_blank" rel="noopener noreferrer"')

    def test_editorial_hubs_have_complete_russian_versions(self):
        cases = (
            ('/ru/is-derry-maine-real/', 'Существует ли Дерри, штат Мэн?',
             'Дерри, штат Мэн, — вымышленный город.'),
            ('/ru/how-bangor-inspired-derry-maine/', 'Как Бангор вдохновил Дерри, штат Мэн',
             'Сравнение вымышленного Дерри с Бангором:'),
            ('/ru/books-set-in-derry-maine/', 'Книги Стивена Кинга о Дерри, штат Мэн',
             'Гид без крупных спойлеров'),
        )
        for path, heading, description in cases:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, heading)
            self.assertContains(response, description)
            self.assertNotContains(response, '<html lang="en">')
        books = self.client.get('/ru/books-set-in-derry-maine/')
        self.assertContains(books, '«На выгодных условиях»')
        self.assertContains(books, '«Последнее дело Гвенди»')

    def test_printable_map_has_localized_downloads_and_print_guidance(self):
        english = self.client.get('/printable-derry-map/')
        self.assertEqual(english.status_code, 200)
        self.assertContains(english, '<h1>Download a printable map of Derry, Maine</h1>', html=True)
        self.assertContains(english, 'atlas/downloads/en/Derry_Print_Atlas.pdf')
        self.assertContains(english, 'atlas/downloads/en/derry_city.svg')
        self.assertContains(english, 'Photographs and photo markers are not included')
        self.assertContains(english, 'href="/method/"')
        self.assertContains(english, '<h1', count=1)

        russian = self.client.get('/ru/printable-derry-map/')
        self.assertEqual(russian.status_code, 200)
        self.assertContains(russian, '<h1>Скачать карту Дерри для печати</h1>', html=True)
        self.assertContains(russian, 'atlas/downloads/ru/Derry_Print_Atlas.pdf')
        self.assertContains(russian, 'названия улиц и мест переведены на русский')
        self.assertContains(russian, 'Фотографии и их отметки в печатную версию не включены')
        self.assertContains(russian, 'hreflang="en" href="http://testserver/printable-derry-map/"')

    def test_town_navigation_links_hubs_and_places_but_not_homepage(self):
        self.assertNotContains(self.client.get('/'), 'class="derry-explore"')
        for path in ('/places/', '/places/12-derry-public-library/',
                     '/is-derry-maine-real/', '/how-bangor-inspired-derry-maine/',
                     '/books-set-in-derry-maine/', '/printable-derry-map/'):
            response = self.client.get(path)
            self.assertContains(response, 'class="derry-explore"')
            self.assertContains(response, 'Is Derry, Maine a real town?')
            self.assertContains(response, 'How Bangor inspired Derry')
            self.assertContains(response, 'Stephen King books set in Derry')
            self.assertContains(response, 'Printable map of Derry')
            self.assertContains(response, 'Map of Derry')
            self.assertContains(response, 'All places')
        russian = self.client.get('/ru/places/')
        self.assertContains(russian, 'Узнать больше о Дерри')
        self.assertContains(russian, 'Книги Стивена Кинга о Дерри')
        self.assertContains(russian, 'Карта Дерри для печати')

    def test_approved_seo_templates_are_localized_in_russian(self):
        response = self.client.get('/ru/')
        self.assertContains(
            response,
            '<title>Карта Дерри, штат Мэн — литературный атлас «Оно» Стивена Кинга</title>')
        self.assertContains(response, '1 место на карте')
        response = self.client.get('/ru/places/12-derry-public-library/')
        self.assertContains(
            response,
            '<title>Публичная библиотека Дерри — Дерри, штат Мэн · «Оно» Стивена Кинга</title>')

    def test_home_renders_a_linked_place_directory_without_javascript(self):
        response = self.client.get('/')
        self.assertContains(response, '<h2 id="all-places-title">All places in Derry</h2>')
        self.assertContains(response, 'Browse all 2 places')
        self.assertContains(response, '1 mapped · 1 unlocated')
        self.assertContains(response, 'href="/places/12-derry-public-library/"')
        self.assertContains(response, 'href="/places/u3-tracker-brothers/"')
        self.assertContains(response, 'class="directory-copy"', count=2)
        body = response.content.decode()
        self.assertLess(body.index('>Civic<'), body.index('>Unlocated<'))

        response = self.client.get('/ru/')
        self.assertContains(response, '<h2 id="all-places-title">Все места Дерри</h2>')
        self.assertContains(response, '1 на карте · 1 без координат')
        self.assertContains(response, 'href="/ru/places/12-derry-public-library/"')
        self.assertContains(response, 'href="/ru/places/u3-tracker-brothers/"')

    def test_home_and_places_add_context_without_competing_with_primary_ui(self):
        home = self.client.get('/').content.decode()
        self.assertIn('A map of Derry from Stephen King’s <i>IT</i>', home)
        self.assertGreater(home.index('class="map-context"'), home.index('class="workspace"'))
        self.assertLess(home.index('class="map-context"'), home.index('class="place-directory"'))
        self.assertNotIn('href="/is-derry-maine-real/"', home)
        places = self.client.get('/places/')
        self.assertContains(places, 'These are locations from the novel, not filming locations')
        self.assertContains(self.client.get('/ru/places/'),
                            'Это места книги, а не съёмочные локации экранизаций.')

    def test_photo_pages_use_the_photo_as_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(root / 'a.png', caption='Ben.', feature='12', year=1958)
                response = self.client.get(f'/photos/{photo.id}/')
                self.assertContains(response, '<meta property="og:image" content="http://testserver/media/')
                self.assertContains(response, '<meta property="og:title" content="Ben. — Derry, Maine · Stephen King’s IT">')
                self.assertContains(
                    response,
                    '<meta name="description" content="Ben. A photograph of Derry Public Library '
                    'in the Derry, Maine literary atlas based on Stephen King’s IT, dated 1958.">')
                self.assertContains(response, '<meta property="og:image:width" content="1200">')
                self.assertContains(response, '<meta property="og:image:height" content="800">')
                self.assertContains(response, '<meta property="article:published_time"')
                self.assertContains(response, '<meta property="article:modified_time"')
                self.assertContains(response, '<h1>Ben.</h1>')
                self.assertContains(response, 'srcset="/media/photos/medium/')
                # Страница места берёт первое фото места.
                response = self.client.get('/places/12-derry-public-library/')
                self.assertContains(response, '<meta property="og:image" content="http://testserver/media/')
                self.assertContains(response, '<meta property="og:image:width" content="1200">')
                self.assertContains(response, '<meta property="article:published_time"')
                self.assertContains(response, '<meta property="article:modified_time"')

    def test_missing_caption_uses_place_name_in_alt_not_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'secret-upload-name.png', color=(10, 20, 30))
                photo = photos.add(root / 'secret-upload-name.png', feature='12', year=1958)
                for path in ('/photos/', f'/photos/{photo.id}/',
                             '/places/12-derry-public-library/'):
                    response = self.client.get(path)
                    self.assertContains(response, 'alt="Derry Public Library photograph"')
                    self.assertNotContains(response, 'alt="secret-upload-name.png"')


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
        for path in ('/', '/places/', '/photos/', '/method/', '/places/12-derry-public-library/',
                     '/is-derry-maine-real/', '/how-bangor-inspired-derry-maine/',
                     '/books-set-in-derry-maine/', '/printable-derry-map/'):
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
        gallery_data = jsonld(self.client.get('/photos/'))
        gallery = node(gallery_data, 'ImageGallery')
        self.assertEqual(gallery['url'], 'http://testserver/photos/')
        self.assertIn('CollectionPage', gallery['@type'])
        crumbs = node(gallery_data, 'BreadcrumbList')['itemListElement']
        self.assertEqual([crumb['name'] for crumb in crumbs], ['Derry', 'Photographs'])
        self.assertEqual(crumbs[0]['item'], 'http://testserver/')
        self.assertNotIn('item', crumbs[1])
        method = node(jsonld(self.client.get('/method/')), 'WebPage')
        self.assertEqual(method['about'], {'@id': 'http://testserver/#book'})

    def test_editorial_hubs_are_articles_with_breadcrumbs(self):
        for path, heading in (
                ('/is-derry-maine-real/', 'Is Derry, Maine a real town?'),
                ('/how-bangor-inspired-derry-maine/', 'How Bangor inspired Derry, Maine'),
                ('/books-set-in-derry-maine/', 'Stephen King books set in Derry, Maine'),
                ('/printable-derry-map/', 'Download a printable map of Derry, Maine')):
            data = jsonld(self.client.get(path))
            article = node(data, 'Article')
            self.assertEqual(article['url'], 'http://testserver' + path)
            self.assertEqual(article['author']['name'], 'Derry')
            self.assertEqual(article['datePublished'], '2026-09-29')
            self.assertEqual(article['dateModified'], '2026-09-29')
            crumbs = node(data, 'BreadcrumbList')['itemListElement']
            self.assertEqual(crumbs[0]['item'], 'http://testserver/')
            self.assertNotIn('item', crumbs[-1])
            response = self.client.get(path)
            self.assertContains(response, heading)

    def test_gallery_landing_jsonld_has_its_own_url_and_breadcrumb(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photos.add(root / 'a.png', caption='Ben.', feature='12', tags=['library'])
                data = jsonld(self.client.get('/photos/tag/library/'))
        gallery = node(data, 'ImageGallery')
        self.assertEqual(gallery['url'], 'http://testserver/photos/tag/library/')
        self.assertEqual(gallery['name'], 'Library photographs of Derry, Maine · Stephen King’s IT')
        crumbs = node(data, 'BreadcrumbList')['itemListElement']
        self.assertEqual([crumb['name'] for crumb in crumbs],
                         ['Derry', 'Photographs', 'Library photographs'])
        self.assertEqual(crumbs[1]['item'], 'http://testserver/photos/')
        self.assertNotIn('item', crumbs[2])

    def test_place_index_is_a_collection_and_item_list(self):
        data = jsonld(self.client.get('/places/'))
        collection = node(data, 'CollectionPage')
        self.assertEqual(collection['url'], 'http://testserver/places/')
        items = node(data, 'ItemList')
        self.assertEqual(items['numberOfItems'], 1)
        self.assertEqual([item['position'] for item in items['itemListElement']], [1])
        self.assertTrue(items['itemListElement'][0]['url'].startswith('http://testserver/places/'))

    def test_place_page_is_article_with_breadcrumbs(self):
        data = jsonld(self.client.get('/places/12-derry-public-library/'))
        article = node(data, 'Article')
        self.assertEqual(article['headline'], 'Derry Public Library')
        self.assertEqual(article['temporalCoverage'], '1958')
        self.assertEqual(article['about'], {'@id': 'http://testserver/#book'})
        crumbs = node(data, 'BreadcrumbList')['itemListElement']
        self.assertEqual([c['position'] for c in crumbs], [1, 2, 3])
        self.assertEqual(crumbs[0]['item'], 'http://testserver/')
        self.assertEqual(crumbs[1]['item'], 'http://testserver/places/')
        self.assertEqual(crumbs[2]['name'], 'Derry Public Library')
        self.assertNotIn('item', crumbs[2])

        russian = jsonld(self.client.get('/ru/places/12-derry-public-library/'))
        article = node(russian, 'Article')
        self.assertEqual(article['headline'], 'Публичная библиотека Дерри')
        crumbs = node(russian, 'BreadcrumbList')['itemListElement']
        self.assertEqual(crumbs[0]['name'], 'Дерри')
        self.assertEqual(crumbs[2]['name'], 'Публичная библиотека Дерри')

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
        self.assertEqual(image['keywords'], 'Ben, Library')
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
