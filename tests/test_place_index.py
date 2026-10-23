import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from atlas import covers, photos
from atlas.models import Evidence, Feature, Geometry, Source

from .test_photos import make_image


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PlaceIndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:4', shape={'type': 'point', 'x': 0, 'y': 0})
        cls.school = Feature.objects.create(
            key='4', object_type='site', name='Derry Elementary School', short='School',
            kind='Civic', confidence='A', period='1957–58, 1985',
            note='A civic landmark.', about='The school anchors the district.',
            confidence_explanation='Jackson Street fixes its relationship.', geometry=point,
            metadata={'ru': {'note': 'Городской ориентир.', 'about': 'Школа отмечает район.',
                             'confidence_explanation': 'Привязка подтверждена улицей.'}})
        cls.lost = Feature.objects.create(
            key='U3', object_type='unplaced', name='Tracker Brothers', confidence='U',
            note='The exact location is unknown.', metadata={})
        line = Geometry.objects.create(
            key='g:road:02', shape={'type': 'line', 'points': [[0, 0], [10, 0]]})
        Feature.objects.create(key='road:02', object_type='road', name='Main Street',
                               geometry=line, metadata={})
        source = Source.objects.create(key='novel', title='IT', kind='book')
        Evidence.objects.create(key='e1', feature=cls.school, source=source,
                                reference='Ch. 1', note='School reference.')

    def test_index_is_server_rendered_and_excludes_non_places(self):
        response = self.client.get('/places/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1 class="t-h1">Places in Derry, Maine</h1>', html=True)
        self.assertContains(response, '<li class="tile', count=2)
        self.assertContains(response, '/places/4-derry-elementary-school/')
        self.assertContains(response, '/places/u3-tracker-brothers/')
        self.assertNotContains(response, 'Main Street')
        self.assertContains(response, 'A civic landmark.')
        self.assertContains(
            response,
            'data-search="4 Derry Elementary School School Начальная школа Дерри Civic')
        self.assertContains(response, 'data-sure="a" data-kind="civic" data-media=""')
        self.assertContains(response, 'data-sure="u" data-kind="" data-media=""')
        # Плитка — одна ссылка: номер маркера, имя, мета-строка словами.
        self.assertContains(response, '<span class="num num--a num--civic" aria-hidden="true">4</span>')
        self.assertContains(response, '<h2 class="tile__name">Derry Elementary School</h2>')
        self.assertContains(response, '<span class="tile__conf tile__conf--a">named in the novel</span>')
        self.assertContains(response, '/static/atlas/locators/4-tile.webp')
        self.assertContains(response, 'No point on the map')  # U3 — штриховка
        # Сводка и ссылки hero; фильтры, сортировка и вид — только с JS.
        self.assertContains(response, '<b>2</b> places · <b>1</b> on the map · <b>1</b> without a point')
        self.assertContains(response, 'href="/method/#how-sure"')
        self.assertContains(response, 'class="index-filters js-only"')
        self.assertContains(response, 'name="sure" value="u"')
        self.assertContains(response, 'name="kind" value="civic"')
        self.assertContains(response, '<section class="index-about" id="about-list"')
        # Аудит публично не виден.
        self.assertNotContains(response, 'owner-bar')
        self.assertNotContains(response, 'data-missing')
        self.assertNotContains(response, 'text incomplete')
        self.assertNotContains(response, 'name="robots"')

    def test_query_state_keeps_full_server_html_and_canonical(self):
        response = self.client.get('/places/', {'q': 'school', 'confidence': 'A'})
        self.assertContains(response, 'Derry Elementary School')
        self.assertContains(response, 'Tracker Brothers')
        self.assertContains(response, '<link rel="canonical" href="http://testserver/places/">')
        self.assertContains(response, 'href="/ru/places/?q=school&amp;confidence=A"')

    def test_audit_mode_is_noindex_and_marks_gaps(self):
        response = self.client.get('/places/', {'audit': '1'})
        self.assertContains(response, '<meta name="robots" content="noindex, nofollow">')
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
        self.assertContains(response, 'Owner mode · data audit')
        self.assertContains(response, 'data-audit="photos" aria-pressed="false">Photos <span class="chip__count">2</span>')
        self.assertContains(response, 'data-audit="one-source" aria-pressed="false">One source only '
                                      '<span class="chip__count">1</span>')
        self.assertContains(response, 'data-missing="photos cover one-source"')
        self.assertContains(response, 'no photos · no cover · one source')
        self.assertContains(response, 'href="/places/">Exit owner mode</a>')

    def test_place_cards_use_cover_then_photo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'photo.png', color=(10, 20, 30))
                photos.add(root / 'photo.png', feature='4', year=1958, caption='School yard.')
                make_image(root / 'cover.png', size=(1536, 1024), color=(40, 50, 60))
                covers.add(root / 'cover.png', feature='4', year=1958, alt='School front.')
                response = self.client.get('/places/')
        self.assertContains(response, '/media/covers/medium/')
        self.assertNotContains(response, '/media/photos/thumb/')
        self.assertContains(response, 'data-media="photos cover"')
        self.assertContains(response, '<li class="tile tile--picture"')
        self.assertContains(response, 'class="card-photo tile__polaroid"')  # компактный вид
        self.assertNotContains(response, '/static/atlas/locators/4-tile.webp')

    def test_russian_page_uses_localized_copy_and_search_data(self):
        response = self.client.get('/ru/places/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="ru"')
        self.assertContains(response, '<h2 class="tile__name">Начальная школа Дерри</h2>')
        # Категории: полная форма на фильтре, короткая — в мета-строке плитки.
        self.assertContains(response, '<span class="filter-opt__label">Городские места</span>')
        self.assertContains(response, '<span class="t-meta tile__meta">Город · ')
        self.assertContains(response, '<h2 class="tile__name">Городская ратуша Дерри</h2>')
        self.assertContains(response, 'Городской ориентир.')
        self.assertContains(response, 'Школа отмечает район.')
        self.assertContains(response, '<b>2</b> места · <b>1</b> на карте · <b>1</b> без координат')
        self.assertContains(response, 'без координат</span>')
        self.assertContains(
            response,
            'data-search="4 Derry Elementary School School Начальная школа Дерри')
        self.assertContains(response, '/ru/places/4-derry-elementary-school/')
