import json
import re
import tempfile
from pathlib import Path
from django.test import TestCase, override_settings
from atlas import photos
from atlas.models import Character, Feature, Geometry

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
        """Подписи карточек в порядке сетки: в HTML только подходящие фото."""
        html = response.content.decode()
        found = [(html.find(c), c) for c in ('Ben at the library.', 'The library building.',
                                             'Bill races Silver.', 'Derry in 1985.')
                 if f'class="gallery-item__caption" aria-hidden="true">{c}<' in html]
        return [c for _, c in sorted(found)]

    def test_gallery_lists_all_photos_with_thumbs_and_filter_panel(self):
        response = self.client.get('/photos/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache')
        self.assertEqual(len(self.captions(response)), 4)
        self.assertContains(response, photos.relative_paths(self.ben.sha256, self.ben.ext)['w480'])
        # Карточка — одна ссылка на страницу фото; год и место — текстом.
        self.assertContains(response, f'<a class="gallery-item__link" href="/photos/{self.ben.id}/">')
        self.assertContains(response, '<span class="t-meta">1958 · Derry Public Library</span>')
        self.assertContains(response, '<span class="t-meta">1985</span>')
        self.assertNotContains(response, 'Photographs from here')
        self.assertContains(response, 'id="galleryStatus" role="status">4 photographs<')
        self.assertContains(response, 'href="/photos/" data-clear hidden>Clear filters</a>')
        # Группы в порядке D23: Character, Place, Year (всегда), Tag.
        html = response.content.decode()
        order = [html.find(f'data-group="{g}"><legend') for g in ('character', 'place', 'year', 'tag')]
        self.assertEqual(order, sorted(order))
        self.assertTrue(all(i > 0 for i in order))
        self.assertContains(response, 'href="/photos/year/1985/" data-group="year"')
        self.assertContains(response, 'href="/photos/character/ben-hanscom/" data-group="character"')
        self.assertContains(response, '>Architecture <span class="chip__count">1</span>')
        # Места — по числу фото: у библиотеки 2, у Main Street 1.
        self.assertLess(html.find('data-value="12"'), html.find('data-value="road:02"'))
        self.assertNotContains(response, 'rel="nofollow"')
        self.assertNotContains(response, 'gallery-filters__more')  # мест меньше шести

    def test_gallery_cards_offer_responsive_sources(self):
        response = self.client.get('/photos/')
        rel = photos.relative_paths(self.ben.sha256, self.ben.ext)
        # Колонки галереи — производные по ширине 480 и 960 (снимок 1200 px шириной).
        self.assertContains(response, f'srcset="/media/{rel["w480"]} 480w, /media/{rel["w960"]} 960w"')
        self.assertContains(response, 'sizes="(max-width: 47.99em) calc(50vw - 22px)')
        # Узкий снимок: одна запись с его настоящей шириной.
        narrow = photos.add(make_image(Path(self.dir.name) / 'n.png', size=(400, 300), color=(5, 6, 7)))
        small = photos.relative_paths(narrow.sha256, narrow.ext)
        self.assertContains(self.client.get('/photos/'), f'srcset="/media/{small["w480"]} 400w"')

        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, f'{rel["thumb"]} 320w')
        self.assertContains(response, f'{rel["medium"]} 1200w')

    def test_place_filter_and_readable_url(self):
        self.assertRedirects(
            self.client.get('/photos/', {'place': '12'}),
            '/photos/place/12-derry-public-library/', status_code=301)
        response = self.client.get('/photos/place/12-derry-public-library/')
        self.assertEqual(self.captions(response), ['Ben at the library.', 'The library building.'])
        self.assertContains(response, 'role="status">2 photographs<')
        # Под H1 — страница места и карта; отмеченный пункт ведёт обратно на /photos/.
        self.assertContains(response, '<a class="link link--arrow" href="/places/12-derry-public-library/">Place page</a>')
        self.assertContains(response, '<a class="link link--arrow" href="/?place=12">Show on the map</a>')
        self.assertContains(response, 'href="/photos/" data-group="place" data-value="12" aria-current="true"')
        self.assertNotContains(response, 'chip--set')
        self.assertRedirects(
            self.client.get('/photos/', {'place': 'road:02'}),
            '/photos/place/road02-main-street/', status_code=301)
        response = self.client.get('/photos/place/road02-main-street/')
        self.assertEqual(self.captions(response), ['Bill races Silver.'])
        self.assertNotContains(response, 'gallery-head__links')  # у дороги нет страницы и точки
        self.assertContains(self.client.get('/photos/'), '/photos/place/road02-main-street/')

    def test_character_filter(self):
        self.assertRedirects(
            self.client.get('/photos/', {'character': 'ben-hanscom'}),
            '/photos/character/ben-hanscom/', status_code=301)
        response = self.client.get('/photos/character/ben-hanscom/')
        self.assertEqual(self.captions(response), ['Ben at the library.'])

    def test_character_faces(self):
        photos.set_avatar('ben-hanscom', self.ben.id, x=0.5, y=0.2, zoom=4)
        response = self.client.get('/photos/')
        thumb = photos.relative_paths(self.ben.sha256, self.ben.ext)['thumb']
        # 1200×800: зум 4 → ширина 400 %, высота 266.7 %; точка лица (0.5, 0.2) — в центре кружка.
        self.assertContains(response, f'<span class="face" style="background-image:url(/media/{thumb});'
                                      'background-size:400% auto;background-position:50.0% 2.0%"')
        self.assertContains(response, '<span class="face face--initial" aria-hidden="true">B</span>'
                                      '<span class="filter-opt__label">Bill Denbrough<')
        with self.assertRaisesMessage(ValueError, 'between 0 and 1'):
            photos.set_avatar('ben-hanscom', x=1.5)
        with self.assertRaisesMessage(ValueError, 'at least 1'):
            photos.set_avatar('ben-hanscom', zoom=0.5)
        # Удалённое фото снимает аватар, персонаж остаётся.
        photos.remove(self.ben.id)
        self.assertIsNone(Character.objects.get(pk='ben-hanscom').avatar)

    def test_places_beyond_five_fold_into_details(self):
        source = Path(self.dir.name) / 'more'
        for n in range(5):
            Feature.objects.create(key=str(20 + n), object_type='unplaced', confidence='U', name=f'Place {n}', metadata={})
            make_image(source / f'{n}.png', color=(n, 200, 100))
            photos.add(source / f'{n}.png', feature=str(20 + n))
        response = self.client.get('/photos/')
        # Библиотека (2 фото) первой; шестое место — под «All 7 places».
        self.assertContains(response, '<details class="gallery-filters__more"><summary class="link">All 7 places</summary>')
        landing = self.client.get('/photos/place/24-place-4/')
        self.assertContains(landing, '<details class="gallery-filters__more" open>')
        self.assertContains(self.client.get('/ru/photos/'), '>Все 7 мест</summary>')

    def test_tags_are_any_of_and_deduplicated(self):
        response = self.client.get('/photos/', {'tag': 'library,silver'})
        self.assertEqual(self.captions(response),
                         ['Ben at the library.', 'The library building.', 'Bill races Silver.'])
        self.assertContains(response, 'role="status">3 of 4 photographs<')
        # Фото с обоими тегами не задваивается.
        response = self.client.get('/photos/', {'tag': 'library,interior'})
        self.assertContains(response, 'role="status">2 of 4 photographs<')
        self.assertRedirects(
            self.client.get('/photos/', {'tag': 'library'}),
            '/photos/tag/library/', status_code=301)
        # Ссылки панели ведут только на лендинги одного фильтра (решение 23.10).
        response = self.client.get('/photos/tag/library/')
        self.assertContains(response, 'href="/photos/tag/interior/" data-group="tag"')
        self.assertNotContains(response, '?tag=')
        self.assertEqual(self.captions(self.client.get('/photos/', {'tag': 'silver,library'})),
                         ['Ben at the library.', 'The library building.', 'Bill races Silver.'])

    def test_all_photos_reach_the_script(self):
        response = self.client.get('/photos/tag/silver/')
        self.assertEqual(self.captions(response), ['Bill races Silver.'])
        self.assertContains(response, 'src="/static/atlas/gallery.js" defer')
        state = json.loads(re.search(r'<script id="galleryState" type="application/json">(.*?)</script>',
                                     response.content.decode()).group(1))
        # В JSON — все фото в порядке галереи, с группами для фильтра в браузере.
        self.assertEqual([p['id'] for p in state['photos']],
                         [self.ben.id, self.building.id, self.bill.id, self.loose.id])
        ben = state['photos'][0]
        self.assertEqual((ben['place'], ben['character'], ben['tag'], ben['year']),
                         (['12'], ['ben-hanscom'], ['interior', 'library'], ['1958']))
        self.assertEqual(ben['url'], f'/photos/{self.ben.id}/')
        self.assertEqual(state['selection'], {'character': [], 'place': [], 'year': [], 'tag': ['silver']})
        self.assertEqual(state['landings']['place:road:02'], '/photos/place/road02-main-street/')
        self.assertEqual(state['strings']['page'], 24)
        self.assertEqual(state['strings']['of_total'][2], '%(n)s of %(total)s photographs')
        russian = json.loads(re.search(r'<script id="galleryState" type="application/json">(.*?)</script>',
                                       self.client.get('/ru/photos/').content.decode()).group(1))
        self.assertEqual(russian['base'], '/ru/photos/')
        self.assertEqual(russian['photos'][0]['url'], f'/ru/photos/{self.ben.id}/')
        self.assertEqual(russian['strings']['show'],
                         ['Показать %(n)s фотографию', 'Показать %(n)s фотографии',
                          'Показать %(n)s фотографий'])
        self.assertEqual(russian['strings']['more'], 'Показать ещё %(n)s')

    def test_values_within_a_group_are_any_of(self):
        response = self.client.get('/photos/', {'place': '12,road:02'})
        self.assertEqual(self.captions(response),
                         ['Ben at the library.', 'The library building.', 'Bill races Silver.'])
        response = self.client.get('/photos/', {'year': '1958,1985'})
        self.assertEqual(len(self.captions(response)), 4)

    def test_dimensions_combine_as_and_with_chips_and_facets(self):
        response = self.client.get('/photos/', {'place': '12', 'tag': 'interior'})
        self.assertEqual(self.captions(response), ['Ben at the library.'])
        self.assertContains(response, '<link rel="canonical" href="http://testserver/photos/">')
        self.assertContains(response, '<h1 class="t-h1">Photographs</h1>')
        self.assertNotContains(response, 'gallery-head__intro')
        self.assertContains(response, 'role="status">1 of 4 photographs<')
        # Чип снимает своё значение: остаётся лендинг второго.
        self.assertContains(response, '<a class="chip chip--set" href="/photos/tag/interior/" '
                                      'aria-label="Remove filter: Derry Public Library">')
        self.assertContains(response, '<a class="chip chip--set" href="/photos/place/12-derry-public-library/" '
                                      'aria-label="Remove filter: Interior">')
        self.assertContains(response, '<a class="gallery-results__clear" href="/photos/" data-clear>Clear filters</a>')
        # Фасеты: Ben даёт 1 снимок, Bill — 0 (серый); другое место при ИЛИ — свои снимки.
        html = response.content.decode()
        self.assertRegex(html, r'(?s)data-value="ben-hanscom">.*?chip__count">1<')
        self.assertIn('<a class="filter-opt is-empty" href="/photos/character/bill-denbrough/"', html)
        self.assertRegex(html, r'(?s)data-value="road:02">.*?chip__count">0<')
        response = self.client.get('/photos/', {'place': '12', 'character': 'bill-denbrough'})
        self.assertEqual(self.captions(response), [])
        self.assertContains(response, 'No photographs found')
        self.assertContains(response, 'Try removing a filter.')
        self.assertContains(response, '<a class="btn btn--secondary" href="/photos/" data-clear>Clear filters</a>')

    def test_combinations_are_noindex_and_limited_to_two_values(self):
        combo = self.client.get('/photos/', {'place': '12', 'year': '1958'})
        self.assertContains(combo, '<meta name="robots" content="noindex, nofollow">')
        self.assertEqual(combo['X-Robots-Tag'], 'noindex, nofollow')
        for params in ({'place': '12', 'tag': 'interior', 'year': '1958'},
                       {'tag': 'library,interior,silver'},
                       {'place': '12,road:02', 'year': '1958'},
                       {'place': '12', 'character': 'ben-hanscom', 'tag': 'library'}):
            self.assertEqual(self.client.get('/photos/', params).status_code, 404, params)
        for path in ('/photos/', '/photos/tag/library/', '/photos/place/12-derry-public-library/'):
            response = self.client.get(path)
            self.assertNotContains(response, 'name="robots"')
            self.assertFalse(response.has_header('X-Robots-Tag'), path)
            self.assertNotContains(response, 'rel="nofollow"')

    def test_unknown_or_invalid_values_are_not_found(self):
        for params in ({'tag': 'no-such-tag'}, {'tag': 'library,no-such-tag'}, {'place': '999'},
                       {'character': 'pennywise'}, {'year': '1929'}, {'year': 'abc'}):
            self.assertEqual(self.client.get('/photos/', params).status_code, 404, params)
        for path in ('/photos/place/not-a-place/', '/photos/character/nobody/',
                     '/photos/tag/not-a-tag/', '/photos/year/1999/'):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        # Посторонние параметры (метки рекламы и т. п.) выдачу не ломают.
        response = self.client.get('/photos/', {'utm_source': 'x'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.captions(response)), 4)

    def test_landing_pages_have_unique_copy_canonical_and_breadcrumbs(self):
        cases = (
            ('/photos/place/12-derry-public-library/', 'Photographs of Derry Public Library'),
            ('/photos/character/ben-hanscom/', 'Ben Hanscom in Derry photographs'),
            ('/photos/tag/library/', 'Library photographs'),
            ('/photos/year/1958/', 'Derry photographs from 1958'),
        )
        for path, heading in cases:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, f'<h1 class="t-h1">{heading}</h1>')
            self.assertContains(response, f'<link rel="canonical" href="http://testserver{path}">')
            self.assertContains(response, f'hreflang="ru" href="http://testserver/ru{path}"')
            self.assertContains(response, 'class="gallery-head__intro"')
            self.assertContains(response, 'class="crumbs"')
        # Последняя крошка — значение фильтра.
        self.assertContains(self.client.get('/photos/tag/library/'),
                            '<li><span aria-current="page">Library</span></li>')

        russian = self.client.get('/ru/photos/year/1958/')
        self.assertContains(russian, 'Фотографии Дерри в 1958 году')
        self.assertContains(russian, 'hreflang="en" href="http://testserver/photos/year/1958/"')
        self.assertRedirects(
            self.client.get('/ru/photos/', {'tag': 'library'}),
            '/ru/photos/tag/library/', status_code=301)

    def test_russian_gallery_localizes_labels_but_keeps_filter_urls(self):
        response = self.client.get('/ru/photos/')
        self.assertContains(response, 'Публичная библиотека Дерри')
        self.assertContains(response, 'Бен Хэнском')
        self.assertContains(response, '>Архитектура <span')
        self.assertContains(response, 'href="/ru/photos/character/ben-hanscom/"')
        self.assertContains(response, 'href="/ru/photos/tag/library/"')
        self.assertContains(response, 'href="/ru/photos/place/12-derry-public-library/"')
        self.assertContains(response, 'role="status">4 фотографии<')
        self.assertContains(self.client.get('/ru/photos/', {'place': '12', 'year': '1958'}),
                            'role="status">2 из 4 фотографий<')

        place = self.client.get('/ru/photos/place/12-derry-public-library/')
        self.assertContains(
            place,
            '<h1 class="t-h1">Фотографии: Публичная библиотека Дерри</h1>')
        self.assertContains(
            place, 'фотографии, связанные с местом «Публичная библиотека Дерри»')
        self.assertContains(place, 'href="/ru/places/12-derry-public-library/">Страница места</a>')
        character = self.client.get('/ru/photos/character/ben-hanscom/')
        self.assertContains(character, 'Бен Хэнском')
        self.assertContains(character, 'фотографии с персонажем «Бен Хэнском»')
        self.assertContains(self.client.get('/ru/photos/tag/library/'), 'библиотека')

        photo = self.client.get(f'/ru/photos/{self.ben.id}/')
        self.assertContains(photo, 'Публичная библиотека Дерри')
        self.assertContains(photo, 'Бен Хэнском')
        self.assertContains(photo, '>Библиотека</a>')

    def test_photo_page_shows_attributes_as_filter_links(self):
        response = self.client.get(f'/photos/{self.ben.id}/')
        self.assertEqual(response.status_code, 200)
        rel = photos.relative_paths(self.ben.sha256, self.ben.ext)
        self.assertContains(response, rel['medium'])
        self.assertContains(response, rel['original'])
        self.assertContains(response, 'Ben at the library.')
        self.assertContains(response, '/photos/character/ben-hanscom/')
        self.assertContains(response, '/photos/tag/library/')
        self.assertContains(response, '/photos/place/12-derry-public-library/')
        self.assertContains(response, '/photos/year/1958/')
        self.assertContains(response, '>Library<')
        self.assertContains(response, '/?place=12')  # место-точка: есть переход на карту
        self.assertContains(response, 'href="/places/12-derry-public-library/"')

    def test_photo_page_map_link_only_for_sites(self):
        response = self.client.get(f'/photos/{self.bill.id}/')
        self.assertContains(response, '/photos/place/road02-main-street/')
        self.assertNotContains(response, 'Show on the map')  # у дороги нет маркера на карте
        response = self.client.get(f'/photos/{self.loose.id}/')
        self.assertNotContains(response, '<dt>Place</dt>')  # без привязки нет и блока места

    def test_missing_photo_and_write_methods(self):
        self.assertEqual(self.client.get('/photos/999/').status_code, 404)
        self.assertEqual(self.client.post('/photos/').status_code, 405)
        self.assertEqual(self.client.post(f'/photos/{self.ben.id}/').status_code, 405)
