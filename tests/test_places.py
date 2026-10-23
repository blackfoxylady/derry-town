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
        # Мета-строка: номер маркера, категория, уровень с ⓘ; H1 со скрытым префиксом.
        self.assertContains(response, '<span class="num num--b num--civic" aria-hidden="true">12</span>')
        self.assertContains(response, '<span class="eyebrow">Inferred</span>')
        self.assertContains(response, 'aria-controls="conf-tip" data-toggletip')
        self.assertContains(response, '<span class="visually-hidden">Place 12: </span>Derry Public Library</h1>')
        # Ссылки на роман: подпись из таблицы глав, одинаковые ссылки — одной строкой.
        # Заметки evidence в «In the novel» не показываются.
        self.assertContains(response, '<li><span class="refs__ch">Ch. 4<span class="visually-hidden"> · </span></span>'
                                      '<span>Ben Hanscom Takes a Fall</span><span class="refs__part">'
                                      '<span class="visually-hidden"> · </span>§1</span></li>', count=1)
        self.assertContains(response, 'In the novel<small>1 chapter</small>')
        self.assertNotContains(response, 'Ben reads here.')
        self.assertNotContains(response, 'Ch. 4 - Ben Hanscom')
        # Панель: локатор и кнопка ведут на карту, якорь — к Why.
        self.assertContains(response, '<aside class="fact-panel" aria-label="Place facts">')
        self.assertContains(response, 'href="/?place=12">Show on the map</a>')
        self.assertContains(response, 'href="#why" class="fact-panel__why">Why this pin is B ↓</a>')
        self.assertContains(response, 'Worked out from routes, distances and what stands next to it.')
        self.assertContains(response, 'href="/method/#how-sure"')
        self.assertNotContains(response, 'id="about"')

    def test_long_form_content_is_safe_and_follows_sources(self):
        self.library.about = 'A civic landmark with a literal <script> tag in its draft.'
        self.library.confidence_explanation = 'The street is named; the exact lot is inferred.'
        self.library.save(update_fields=['about', 'confidence_explanation'])

        response = self.client.get('/places/12-derry-public-library/')
        body = response.content.decode()
        self.assertContains(response, 'About Derry Public Library')
        self.assertContains(response, 'Why this pin is marked B')
        self.assertContains(response, 'The street is named; the exact lot is inferred.')
        self.assertContains(response, '&lt;script&gt;', html=False)
        self.assertNotContains(response, '<script> tag')
        # Панель в DOM — после обложки, до фото и текстов (порядок чтения на телефоне).
        self.assertLess(body.index('class="fact-panel"'), body.index('id="about"'))
        self.assertLess(body.index('id="about"'), body.index('id="why"'))

    def test_partial_long_form_content_has_no_empty_section(self):
        self.library.about = 'A civic landmark.'
        self.library.save(update_fields=['about'])

        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, 'About Derry Public Library')
        # Why есть всегда (общая строка уровня и ссылка на метод), абзаца данных нет.
        self.assertContains(response, 'Why this pin is marked B')
        why = response.content.decode().split('id="why"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn('class="prose"', why)

    def test_related_places_are_ranked_and_not_duplicated(self):
        book = Source.objects.get(pk='novel')

        def place(key, x):
            geometry = Geometry.objects.create(
                key=f'g:{key}', shape={'type': 'point', 'x': x, 'y': 0})
            return Feature.objects.create(
                key=key, object_type='site', name=f'Place {key}', kind='Civic',
                confidence='B', geometry=geometry, metadata={})

        nearby_shared = place('13', 10)
        place('14', 20)
        place('15', 30)
        place('16', 40)
        exact_section = place('17', 100)
        same_chapter = place('18', 110)
        bare_reference = place('19', 120)
        Evidence.objects.create(key='e13', feature=nearby_shared, source=book,
                                reference='Ch. 4 - Ben Hanscom / 2')
        Evidence.objects.create(key='e17', feature=exact_section, source=book,
                                reference='Ch. 4 - Ben Hanscom / 1')
        Evidence.objects.create(key='e18', feature=same_chapter, source=book,
                                reference='Ch. 4 - Ben Hanscom / 9')
        Evidence.objects.create(key='e19', feature=bare_reference, source=book,
                                reference='[1771]')

        response = self.client.get('/places/12-derry-public-library/')
        nearby = response.context['nearby_places']
        chapters = response.context['same_chapter_places']
        self.assertEqual([item['feature'].key for item in nearby], ['13', '14', '15', '16'])
        self.assertEqual(nearby[0]['chapter'], 'Ch. 4')
        self.assertEqual([item['feature'].key for item in chapters], ['17', '18'])
        self.assertNotIn('distance', nearby[0])
        self.assertContains(response, 'Explore related places')
        self.assertContains(response, 'href="/places/17-place-17/"')
        self.assertContains(response, '<h3 class="eyebrow">Also in Ch. 4</h3>')
        self.assertContains(response, '<span class="t-meta">Civic · Ch. 4</span>')
        self.assertContains(response, '/static/atlas/locators/13-card.webp')
        self.assertNotContains(response, 'Place 19')
        russian = self.client.get('/ru/places/12-derry-public-library/')
        self.assertContains(russian, 'Исследуйте связанные места')
        self.assertContains(russian, 'Места рядом на карте')
        self.assertContains(russian, '<h3 class="eyebrow">Ещё в гл. 4</h3>')

    def test_stale_or_bare_slug_redirects_to_canonical(self):
        for path in ('/places/12/', '/places/12-old-name/'):
            response = self.client.get(path)
            self.assertRedirects(response, '/places/12-derry-public-library/',
                                 status_code=301, msg_prefix=path)
        # Русская версия сохраняет префикс при редиректе.
        response = self.client.get('/ru/places/12/')
        self.assertRedirects(response, '/ru/places/12-derry-public-library/', status_code=301)

    def test_retired_unplaced_key_redirects_to_new_place(self):
        point = Geometry.objects.create(key='g:84', shape={'type': 'point', 'x': 10, 'y': 10})
        Feature.objects.create(key='84', object_type='site', name='Cycle Shoppe', short='Cycle Shoppe',
                               kind='Civic', confidence='A', geometry=point, metadata={})
        for path, target in (('/places/u5-cycle-shoppe/', '/places/84-cycle-shoppe/'),
                             ('/ru/places/U5/', '/ru/places/84-cycle-shoppe/')):
            self.assertRedirects(self.client.get(path), target, status_code=301, msg_prefix=path)

    def test_unplaced_place_page(self):
        response = self.client.get('/places/u3-tracker-brothers/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tracker Brothers')
        self.assertContains(response, '<span class="num num--u" aria-hidden="true">U3</span>')
        self.assertContains(response, 'Why this place has no pin')
        self.assertContains(response, 'Why there is no pin ↓')
        self.assertContains(response, 'No point on the map')  # в городе, не «вне карты»
        self.assertContains(response, 'href="/places/?sure=u">See the 1 place without a point</a>')
        self.assertNotContains(response, 'Show on the map')
        self.assertNotContains(response, 'Back to the map, at')

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
                self.assertContains(response, '/photos/place/12-derry-public-library/')

    def test_place_page_caps_photos_with_more_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                for index in range(8):
                    make_image(root / f'{index}.png', color=(10 + index * 20, 20, 30))
                    photos.add(root / f'{index}.png', caption=f'Photo {index}.', feature='12', year=1958)
                html = self.client.get('/places/12-derry-public-library/').content.decode()
                grid = html.split('<ul class="place-photos__grid">', 1)[1].split('</ul>', 1)[0]
                # 8 фото: на десктопе 5 + «+3», на телефоне 3 + «+5» (лишние два скрыты CSS).
                self.assertEqual(grid.count('class="card-photo"'), 5)
                self.assertEqual(grid.count('place-photos__item is-desktop-only"'), 2)
                self.assertIn('<b>+3</b><span>All 8 photos →</span>', grid)
                self.assertIn('<b>+5</b><span>All 8 photos →</span>', grid)

    def test_place_page_shows_up_to_six_photos_without_a_tile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                for index in range(6):
                    make_image(root / f'{index}.png', color=(10 + index * 20, 20, 30))
                    photos.add(root / f'{index}.png', caption=f'Photo {index}.', feature='12')
                html = self.client.get('/places/12-derry-public-library/').content.decode()
                grid = html.split('<ul class="place-photos__grid">', 1)[1].split('</ul>', 1)[0]
                self.assertEqual(grid.count('class="card-photo"'), 6)
                self.assertNotIn('is-desktop-only"><a class="place-photos__more"', grid)
                self.assertIn('<b>+3</b>', grid)  # телефон: 3 + «+3»

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
                self.assertContains(response, 'Photographs from here')
                self.assertNotContains(response, 'target="_blank"')
