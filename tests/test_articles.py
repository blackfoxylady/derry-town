"""Редакционные статьи (редизайн, блок 03a): шаблон статьи, оглавление,
карточка карты, «Keep reading» и список /articles/."""
import re

from django.test import TestCase, override_settings
from atlas.models import Feature, Geometry

from .test_seo import jsonld, node

ARTICLES = ('/is-derry-maine-real/', '/how-bangor-inspired-derry-maine/',
            '/books-set-in-derry-maine/')


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ArticleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        Feature.objects.create(key='12', object_type='site', name='Derry Public Library',
                               short='Library', kind='Civic', confidence='A', rank=2,
                               geometry=point, metadata={})
        Feature.objects.create(key='U3', object_type='unplaced', name='Tracker Brothers',
                               confidence='U', metadata={})

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.content.decode()

    def test_articles_sit_under_the_articles_crumb(self):
        html = self.page('/how-bangor-inspired-derry-maine/')
        crumbs = html.split('<nav class="crumbs"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('<li><a href="/articles/">Articles</a></li>', crumbs)
        self.assertIn('<span aria-current="page">How Bangor inspired Derry</span>', crumbs)
        items = node(jsonld(self.client.get('/how-bangor-inspired-derry-maine/')),
                     'BreadcrumbList')['itemListElement']
        self.assertEqual([item['name'] for item in items],
                         ['Map', 'Articles', 'How Bangor inspired Derry'])
        self.assertEqual(items[1]['item'], 'http://testserver/articles/')
        russian = node(jsonld(self.client.get('/ru/books-set-in-derry-maine/')),
                       'BreadcrumbList')['itemListElement']
        self.assertEqual([item['name'] for item in russian], ['Карта', 'Статьи', 'Книги о Дерри'])
        self.assertEqual(russian[1]['item'], 'http://testserver/ru/articles/')
        # The printable map is not an article: its crumbs stay Map / Printable map.
        printable = node(jsonld(self.client.get('/printable-derry-map/')),
                         'BreadcrumbList')['itemListElement']
        self.assertEqual([item['name'] for item in printable], ['Map', 'Printable map'])

    def test_answer_box_and_map_card_sit_next_to_the_heading(self):
        html = self.page('/is-derry-maine-real/')
        self.assertLess(html.index('<h1 class="t-h1">'), html.index('class="answer-box"'))
        self.assertIn('<aside class="answer-box" aria-label="Short answer"><span class="eyebrow">'
                      'Short answer</span>', html)
        self.assertLess(html.index('class="answer-box"'), html.index('class="map-card"'))
        self.assertLess(html.index('class="map-card"'), html.index('class="article__body"'))
        self.assertIn('<a href="/" class="map-card" aria-label="Open the map of Derry">', html)
        self.assertIn('2 places, drawn from the novel', html)
        russian = self.page('/ru/is-derry-maine-real/')
        self.assertIn('aria-label="Открыть карту Дерри"', russian)
        self.assertIn('2 места, нарисованных по тексту романа', russian)
        self.assertIn('aria-label="Краткий ответ"', russian)

    def test_table_of_contents_points_at_every_section(self):
        for path, count in zip(ARTICLES, (6, 7, 5)):
            html = self.page(path)
            toc = html.split('<nav class="toc"', 1)[1].split('</nav>', 1)[0]
            anchors = re.findall(r'<a class="toc__link" href="#([\w-]+)">', toc)
            self.assertEqual(len(anchors), count, path)
            for anchor in anchors:
                self.assertEqual(html.count(f'<h2 id="{anchor}">'), 1, (path, anchor))
            self.assertIn(f'<summary>On this page · {count} sections</summary>', html)
            self.assertTrue(toc.startswith(' aria-label="On this page"'), path)
            self.assertNotIn('aria-current', toc)  # set by the scroll-spy only
            self.assertIn('src="/static/atlas/article.js"', html)
        bangor = self.page('/how-bangor-inspired-derry-maine/')
        self.assertIn('href="#compare">Derry vs Bangor</a>', bangor)
        self.assertIn('<summary>На этой странице · 7 разделов</summary>',
                      self.page('/ru/how-bangor-inspired-derry-maine/'))
        self.assertIn('<summary>На этой странице · 5 разделов</summary>',
                      self.page('/ru/books-set-in-derry-maine/'))

    def test_comparison_table_keeps_one_copy_of_the_data(self):
        html = self.page('/how-bangor-inspired-derry-maine/')
        self.assertIn('<div class="compare" role="region" aria-label="Derry vs Bangor comparison">', html)
        self.assertEqual(html.count('<th scope="row">'), 6)
        self.assertEqual(html.count('data-label="Limit of the comparison"'), 6)
        self.assertNotIn('comparison-scroll', html)
        russian = self.page('/ru/how-bangor-inspired-derry-maine/')
        self.assertIn('aria-label="Сравнение Дерри и Бангора"', russian)
        self.assertEqual(russian.count('data-label="Дерри в «Оно»"'), 6)

    def test_sources_open_externally_with_a_spoken_hint(self):
        html = self.page('/books-set-in-derry-maine/')
        sources = html.split('<section class="sources"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(sources.count('target="_blank" rel="noopener noreferrer"'), 8)
        self.assertEqual(sources.count('<span class="visually-hidden"> (opens an external site)</span>'), 8)
        self.assertIn('(откроется внешний сайт)', self.page('/ru/books-set-in-derry-maine/'))

    def test_books_article_components(self):
        html = self.page('/books-set-in-derry-maine/')
        self.assertEqual(html.count('<article class="book'), 7)
        self.assertEqual(html.count('<article class="book book--central">'), 1)
        self.assertIn('<ol class="reading-order">', html)
        self.assertIn('<aside class="pencil-note"><span class="pencil-note__label">Editorial note</span>', html)
        self.assertIn('Примечание редакции', self.page('/ru/books-set-in-derry-maine/'))

    def test_russian_articles_write_names_in_cyrillic(self):
        bangor = self.page('/ru/how-bangor-inspired-derry-maine/')
        self.assertIn('канал, ручей Кендускиг, водонапорная башня на Томас-Хилл, библиотека', bangor)
        self.assertIn('<h2 id="compare">Дерри и Бангор: что похоже, а что нет</h2>', bangor)
        self.assertIn('Ручей Кендускиг (Kenduskeag Stream)', bangor)
        self.assertIn('Порт-Хоуп (Port Hope)', bangor)
        real = self.page('/ru/is-derry-maine-real/')
        self.assertIn('ручей Кендускиг (Kenduskeag Stream)', real)
        books = self.page('/ru/books-set-in-derry-maine/')
        self.assertIn('Пустошь, общественные здания', books)
        for html in (bangor, real, books):
            text = html.split('<div class="article__text">', 1)[1].split('<section class="sources"', 1)[0]
            # Latin names only as the original in brackets after the Cyrillic one.
            for name in ('Barrens', 'Derry Public Library', 'Derry Standpipe', 'Civic Center',
                         'Full Dark, No Stars</i> переносит'):
                self.assertNotIn(name, text)
            for name in ('Paul Bunyan', 'Kenduskeag', 'Thomas Hill', 'Fair Extension'):
                self.assertLessEqual(text.count(name), 1, name)

    def test_keep_reading_lists_the_other_articles_and_the_printable_map(self):
        html = self.page('/how-bangor-inspired-derry-maine/')
        block = html.split('<nav class="explore explore--reading"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('Keep reading', block)
        self.assertIn('href="/is-derry-maine-real/"', block)
        self.assertIn('href="/books-set-in-derry-maine/"', block)
        self.assertNotIn('href="/how-bangor-inspired-derry-maine/"', block)
        self.assertIn('href="/static/atlas/downloads/en/Derry_Print_Atlas.pdf"', block)
        self.assertIn('All formats →', block)
        self.assertEqual(block.count('Back to the map'), 2)  # head on desktop, end on phone
        russian = self.page('/ru/how-bangor-inspired-derry-maine/')
        block = russian.split('<nav class="explore explore--reading"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('Читать дальше', block)
        self.assertIn('Существует ли город Дерри, штат Мэн?', block)
        self.assertIn('href="/static/atlas/downloads/ru/Derry_Print_Atlas.pdf"', block)
        # Each article leaves itself out.
        for path in ARTICLES:
            block = self.page(path).split('<nav class="explore explore--reading"', 1)[1].split('</nav>', 1)[0]
            for other in ARTICLES:
                self.assertEqual(f'href="{other}"' in block, other != path, (path, other))
        # Place pages keep the plain "Read more about the town" block.
        self.assertNotIn('explore--reading', self.page('/places/12-derry-public-library/'))

    def test_articles_listing(self):
        response = self.client.get('/articles/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<title>Articles about Derry, Maine · Derry atlas</title>', html=True)
        self.assertContains(response, 'Guides to Stephen King’s Derry: is the town real')
        self.assertContains(response, '<h1 class="t-h1">Articles about Derry, Maine</h1>', html=True)
        self.assertContains(response, '<h1', count=1)
        html = response.content.decode()
        listing = html.split('<ol class="listing">', 1)[1].split('</ol>\n', 1)[0]
        order = re.findall(r'<h2 class="listing__title"><a href="([^"]+)">', listing)
        self.assertEqual(order, list(ARTICLES))
        # The visible text starts the accessible name (WCAG 2.5.3), the title follows it.
        self.assertIn('>Read the article<span class="visually-hidden">: Is Derry, Maine a real town?</span></a>',
                      listing)
        self.assertIn('<li>County, population and ZIP code</li>', listing)
        self.assertNotIn('printable-derry-map', listing)
        self.assertNotIn('/method/', listing)
        self.assertIn('class="map-card"', html)
        crumbs = html.split('<nav class="crumbs"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('<span aria-current="page">Articles</span>', crumbs)

        russian = self.client.get('/ru/articles/')
        self.assertContains(russian, '<title>Статьи о Дерри, штат Мэн · Атлас Дерри</title>', html=True)
        self.assertContains(russian, 'Статьи о Дерри, штат Мэн')
        self.assertContains(russian, '>Читать статью<span class="visually-hidden">: Существует ли Дерри, штат Мэн?</span></a>')
        self.assertContains(russian, 'href="/ru/is-derry-maine-real/"')
        self.assertContains(russian, 'hreflang="en" href="http://testserver/articles/"')

    def test_articles_listing_jsonld(self):
        data = jsonld(self.client.get('/articles/'))
        collection = node(data, 'CollectionPage')
        self.assertEqual(collection['url'], 'http://testserver/articles/')
        self.assertEqual(collection['mainEntity'], {'@id': 'http://testserver/articles/#articles'})
        items = node(data, 'ItemList')
        self.assertEqual(items['numberOfItems'], 3)
        self.assertEqual([item['url'] for item in items['itemListElement']],
                         ['http://testserver' + path for path in ARTICLES])
        crumbs = node(data, 'BreadcrumbList')['itemListElement']
        self.assertEqual([crumb['name'] for crumb in crumbs], ['Map', 'Articles'])
        self.assertNotIn('item', crumbs[1])
