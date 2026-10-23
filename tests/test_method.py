"""Страница печати и метод (редизайн, блок 03b): матрица A/B/C/U с примерами,
роли источников W1–W7, «Using the map», карточки печати и «Keep reading»."""
from django.test import TestCase, override_settings
from atlas.models import Feature, Geometry, Setting, Source

from .test_articles import ARTICLES
from .test_seo import jsonld, node


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MethodPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        def site(key, name, confidence):
            point = Geometry.objects.create(key=f'g:{key}', shape={'type': 'point', 'x': 0, 'y': 0})
            Feature.objects.create(key=key, object_type='site', name=name, short=name, kind='Civic',
                                   confidence=confidence, rank=2, geometry=point, metadata={})
        site('12', 'Derry Public Library', 'A')
        site('13', 'Derry Standpipe', 'A')
        site('6', 'Ben Hanscom home', 'B')
        site('8', 'Richie Tozier home', 'C')
        Feature.objects.create(key='U3', object_type='unplaced', name='Derry Town Hall',
                               confidence='U', metadata={})
        Setting.objects.create(key='atlas', value={'method_geometry': 'Canal length is inferred.'})
        Source.objects.create(key='W1', kind='web', title='Stephen King - IT: Inspiration',
                              url='https://stephenking.com/works/novel/it.html',
                              role='Author’s explanation.',
                              metadata={'role_type': 'inspiration',
                                        'ru': {'role': 'Авторское объяснение.'}})
        Source.objects.create(key='W4', kind='web', title='City of Bangor - Parkway map',
                              url='https://example.com/parkway', role='Analogue.',
                              metadata={'role_type': 'analogue'})
        Source.objects.create(key='W9', kind='web', title='Untitled source',
                              url='https://example.com/x', role='No role yet.', metadata={})

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.content.decode()

    def test_matrix_counts_levels_from_the_database_and_links_examples(self):
        html = self.page('/method/')
        self.assertIn('<h2 id="how-sure">How sure is each pin</h2>', html)
        matrix = html.split('<table class="matrix">', 1)[1].split('</table>', 1)[0]
        rows = matrix.split('<tr class="matrix__row">')[1:]
        self.assertEqual(len(rows), 4)
        counts = [row.split('<span class="matrix__n">', 1)[1].split('<', 1)[0] for row in rows]
        self.assertEqual(counts, ['2', '1', '1', '1'])
        self.assertIn('Named in the novel', rows[0])
        self.assertIn('The exact lot and the building outline', rows[0])
        # A/B/C: a link to the place page with its locator crop; U: a hatched tile.
        self.assertIn('href="/places/12-derry-public-library/"', rows[0])
        self.assertIn('12 Derry Public Library', rows[0])
        self.assertIn('/static/atlas/locators/12-example.webp', rows[0])
        self.assertIn('href="/places/u3-derry-town-hall/"', rows[3])
        self.assertIn('Listed, not drawn', rows[3])
        self.assertNotIn('<img', rows[3])
        self.assertIn('<span class="matrix__unit"> places</span>', rows[0])  # phone card: "47 places"

    def test_sources_split_publisher_and_show_role_chips(self):
        html = self.page('/method/')
        sources = html.split('<ol class="source-list">', 1)[1].split('</ol>', 1)[0]
        self.assertIn('<span class="t-meta">Stephen King</span>', sources)
        self.assertIn('>IT: Inspiration<span class="ext" aria-hidden="true">↗</span>', sources)
        self.assertIn('<span class="visually-hidden"> (opens an external site)</span>', sources)
        self.assertIn('target="_blank" rel="noopener noreferrer"', sources)
        self.assertIn('<span class="role-chip role-chip--inspiration">Inspiration</span>', sources)
        self.assertIn('<span class="role-chip role-chip--analogue">Analogue only</span>', sources)
        # A source without a role gets no chip and keeps its whole title.
        w9 = sources.split('W9', 1)[1]
        self.assertIn('>Untitled source<', w9)
        self.assertNotIn('role-chip', w9)
        russian = self.page('/ru/method/')
        self.assertIn('Авторское объяснение.', russian)
        self.assertIn('Источник вдохновения', russian)
        self.assertIn('Только аналог', russian)

    def test_method_texts_crumbs_and_using_the_map(self):
        html = self.page('/method/')
        self.assertIn('Canal length is inferred.', html)
        self.assertIn('The relief is conceptual', html)
        self.assertNotIn('The original research notes record', html)
        self.assertIn('<kbd>Esc</kbd> clears a measurement or closes a place card', html)
        self.assertIn('class="map-card"', html)
        crumbs = html.split('<nav class="crumbs"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('<span aria-current="page">Sources &amp; method</span>', crumbs)
        items = node(jsonld(self.client.get('/method/')), 'BreadcrumbList')['itemListElement']
        self.assertEqual([item['name'] for item in items], ['Map', 'Sources & method'])
        russian = self.page('/ru/method/')
        self.assertIn('Насколько точна каждая точка', russian)
        self.assertIn('Как пользоваться картой', russian)
        self.assertIn('Рельеф условный', russian)
        self.assertIn('<span class="matrix__n">2</span><span class="matrix__unit"> места</span>', russian)
        items = node(jsonld(self.client.get('/ru/method/')), 'BreadcrumbList')['itemListElement']
        self.assertEqual([item['name'] for item in items], ['Карта', 'Источники и метод'])

    def test_keep_reading_on_printable_and_method_lists_all_articles(self):
        for path in ('/printable-derry-map/', '/method/'):
            html = self.page(path)
            block = html.split('<nav class="explore explore--reading explore--three"', 1)[1]
            block = block.split('</nav>', 1)[0]
            for article in ARTICLES:
                self.assertIn(f'href="{article}"', block, (path, article))
            self.assertNotIn('print-card', block)
            self.assertNotIn('aria-current', block)

    def test_printable_cards(self):
        html = self.page('/printable-derry-map/')
        self.assertIn('aria-label="Open sheet 1 as SVG"', html)
        self.assertIn('alt="Sheet 1 of the printable atlas: Derry, the Barrens and the rural approaches"',
                      html)
        self.assertIn('Print at 100% to keep the scale stated on each sheet.', html)
        self.assertEqual(html.count('class="sheet-list__link"'), 4)
        self.assertIn('Downtown, the canal and Up-Mile Hill', html)
        self.assertIn('lang="ru">Download the Russian PDF</a>', html)
        crumbs = html.split('<nav class="crumbs"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('<span aria-current="page">Printable map</span>', crumbs)
        russian = self.page('/ru/printable-derry-map/')
        self.assertIn('aria-label="Открыть лист 1 в SVG"', russian)
        self.assertIn('Центр, канал и Подъём-в-милю', russian)
        self.assertIn('lang="en">Скачать English PDF</a>', russian)
