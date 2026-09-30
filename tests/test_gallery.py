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
        self.assertContains(response, 'href="/places/12-derry-public-library/"')
        self.assertContains(response, 'Photographs from here')
        self.assertContains(response, 'Ben Hanscom')
        self.assertContains(response, '4 photographs')
        # Год показан: в наборе два разных года.
        self.assertContains(response, '/photos/year/1985/')
        self.assertContains(response, '>Architecture<')

    def test_gallery_cards_offer_responsive_sources(self):
        response = self.client.get('/photos/')
        rel = photos.relative_paths(self.ben.sha256, self.ben.ext)
        self.assertContains(response, f'{rel["thumb"]} 320w')
        self.assertContains(response, f'{rel["medium"]} 1200w')
        self.assertContains(response, 'sizes="(max-width:525px) calc(100vw - 30px)')

        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, f'{rel["thumb"]} 320w')
        self.assertContains(response, f'{rel["medium"]} 1200w')

    def test_place_filter_and_readable_url(self):
        self.assertRedirects(
            self.client.get('/photos/', {'place': '12'}),
            '/photos/place/12-derry-public-library/', status_code=301)
        response = self.client.get('/photos/place/12-derry-public-library/')
        self.assertEqual(self.captions(response), ['Ben at the library.', 'The library building.'])
        self.assertContains(response, 'Clear filters')
        # The place title remains canonical, while a redundant self-filter link is omitted.
        self.assertContains(response, 'href="/places/12-derry-public-library/"')
        self.assertNotContains(response, 'Photographs from here')
        self.assertRedirects(
            self.client.get('/photos/', {'place': 'road:02'}),
            '/photos/place/road02-main-street/', status_code=301)
        response = self.client.get('/photos/place/road02-main-street/')
        self.assertEqual(self.captions(response), ['Bill races Silver.'])
        self.assertContains(self.client.get('/photos/'), '/photos/place/road02-main-street/')

    def test_character_filter(self):
        self.assertRedirects(
            self.client.get('/photos/', {'character': 'ben-hanscom'}),
            '/photos/character/ben-hanscom/', status_code=301)
        response = self.client.get('/photos/character/ben-hanscom/')
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
        self.assertRedirects(
            self.client.get('/photos/', {'tag': 'library'}),
            '/photos/tag/library/', status_code=301)
        response = self.client.get('/photos/tag/library/')
        self.assertContains(response, '?tag=library,interior')

    def test_dimensions_combine_as_and(self):
        response = self.client.get('/photos/', {'place': '12', 'tag': 'interior', 'year': '1958'})
        self.assertEqual(self.captions(response), ['Ben at the library.'])
        self.assertContains(response, '<link rel="canonical" href="http://testserver/photos/">')
        self.assertContains(response, '<h1 class="gallery-title">Photographs</h1>')
        self.assertNotContains(response, 'class="gallery-intro"')
        response = self.client.get('/photos/', {'place': '12', 'character': 'bill-denbrough'})
        self.assertEqual(self.captions(response), [])

    def test_unknown_or_invalid_values_give_empty_result_not_error(self):
        for params in ({'tag': 'no-such-tag'}, {'place': '999'}, {'character': 'pennywise'},
                       {'year': '1929'}, {'year': 'abc'}):
            response = self.client.get('/photos/', params)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'No photographs match')
            self.assertContains(response, 'Clear filters')
        for path in ('/photos/place/not-a-place/', '/photos/character/nobody/',
                     '/photos/tag/not-a-tag/', '/photos/year/1999/'):
            self.assertEqual(self.client.get(path).status_code, 404, path)

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
            self.assertContains(response, f'<h1 class="gallery-title">{heading}</h1>')
            self.assertContains(response, f'<link rel="canonical" href="http://testserver{path}">')
            self.assertContains(response, f'hreflang="ru" href="http://testserver/ru{path}"')
            self.assertContains(response, 'class="gallery-intro"')
            self.assertContains(response, 'class="crumbs"')

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
        self.assertContains(response, '>архитектура<span')
        self.assertContains(response, 'href="/ru/photos/character/ben-hanscom/"')
        self.assertContains(response, 'href="/ru/photos/tag/library/"')
        self.assertContains(response, 'href="/ru/places/12-derry-public-library/"')

        place = self.client.get('/ru/photos/place/12-derry-public-library/')
        self.assertContains(
            place,
            '<h1 class="gallery-title">Фотографии: Публичная библиотека Дерри</h1>')
        self.assertContains(
            place, 'фотографии, связанные с местом «Публичная библиотека Дерри»')
        character = self.client.get('/ru/photos/character/ben-hanscom/')
        self.assertContains(character, 'Бен Хэнском')
        self.assertContains(character, 'фотографии с персонажем «Бен Хэнском»')
        self.assertContains(self.client.get('/ru/photos/tag/library/'), 'библиотека')

        photo = self.client.get(f'/ru/photos/{self.ben.id}/')
        self.assertContains(photo, 'Публичная библиотека Дерри')
        self.assertContains(photo, 'Бен Хэнском')
        self.assertContains(photo, '>библиотека</a>')

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
