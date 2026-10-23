"""Локаторы (редизайн, блок 04): геометрия для рендерера, упаковка кадров, manifest
и вывод на страницах."""
import copy
import io
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template import Context, Template
from django.test import TestCase, override_settings
from django.utils import translation
from PIL import Image

from atlas import dataset as ds
from atlas import locators
from atlas.models import MapState
from atlas.rendering import compile_payload

STATIC = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
          'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


def tiny_payload():
    return {
        'base': [
            {'type': 'line', 'cls': 'water-edge', 'feature_id': 'water:river', 'width': 25,
             'stroke': '#648f9a', 'points': [[0, 0], [10, 0.2], [20, 0], [30, 5]]},
            {'type': 'line', 'cls': 'water-edge', 'feature_id': 'water:canal', 'width': 37,
             'stroke': '#8b968e', 'points': [[0, 0], [5, 5]]},
            {'type': 'line', 'cls': 'water-core', 'feature_id': 'water:river', 'points': [[0, 0], [1, 1]]},
            {'type': 'line', 'cls': 'road-primary-casing', 'feature_id': 'road:01', 'width': 19,
             'points': [[0, 100], [50, 120]]},
            {'type': 'line', 'cls': 'road-primary-fill', 'feature_id': 'road:01', 'points': [[0, 100], [50, 120]]},
            {'type': 'line', 'cls': 'road-lane', 'feature_id': 'road:09', 'points': [[0, 0], [9, 9]]},
            {'type': 'poly', 'cls': 'misc', 'fill': '#e7e1bf', 'stroke': '#c7caac', 'width': 1.2,
             'feature_id': '43', 'points': [[0, 0], [10, 0], [10, 10]]},
            {'type': 'rect', 'cls': 'building', 'x': 10, 'y': 20, 'w': 8, 'h': 6, 'angle': 30,
             'fill': '#c7beb0', 'stroke': None},
            {'type': 'circle', 'cls': 'building', 'x': 1, 'y': 2, 'r': 14, 'fill': '#eee7d4',
             'stroke': '#7e8875', 'width': 2, 'feature_id': '33'},
            {'type': 'line', 'cls': 'contour', 'width': 1.4, 'points': [[0, 0], [1, 1], [2, 2]]},
        ],
        'labels': [{'text': 'Kenduskeag Stream', 'x': -100, 'y': -40, 'font': 'Serif', 'kind': 'water',
                    'size': 12, 'angle': 20, 'views': ['city'], 'web_offset': [-10, 120]}],
        'views': [{'id': 'city', 'title': 'DERRY', 'bounds': [-6100, -4300, 3580, 3400]}],
        'colors': {'Civic': '#315e5a'}, 'palette': {}, 'print': {'flow_arrows': [[1, 2, 3]]},
        'data': {'sites': [{'id': 12, 'x': 100, 'y': -200, 'name': 'Derry Public Library',
                            'short': 'Library', 'kind': 'Civic', 'confidence': 'A'}],
                 'unplaced': []},
    }


class GeometryTests(TestCase):
    def test_live_payload_becomes_renderer_geometry(self):
        g = locators.renderer_geometry(tiny_payload())
        # y flips to screen orientation; nearly straight runs are simplified
        self.assertEqual(g['water'][0], {'id': 'river', 'p': [[0.0, 0.0], [20.0, 0.0], [30.0, -5.0]],
                                         'w': 25, 'edge': False})
        self.assertTrue(g['water'][1]['edge'])
        self.assertEqual(len(g['water']), 2)                     # cores and fills are rebuilt
        self.assertEqual([r['c'] for r in g['roads']], ['primary', 'lane'])
        self.assertEqual(g['areas'][0]['fill'], '#e7e1bf')        # misc polygons are areas
        self.assertEqual(g['buildings'][0][:6], [10.0, -20.0, 8.0, 6.0, -30.0, 0])
        self.assertEqual(g['dots'][0]['y'], -2.0)
        self.assertEqual(g['contours'][0]['i'], 1)
        self.assertEqual(g['labels'][0], {'t': 'Kenduskeag Stream', 'x': -110.0, 'y': -80.0, 's': 12,
                                          'a': 20, 'f': 'Serif', 'k': 'water', 'v': ['city']})
        self.assertEqual(g['sites'], [{'id': 12, 'x': 100.0, 'y': 200.0, 'n': 'Library', 'k': 'Civic',
                                       'c': 'A'}])
        self.assertEqual(g['views'][0]['b'], [-6100, -3400, 3580, 4300])
        self.assertEqual(g['flow'], [[1, -2, 3]])

    def test_russian_geometry_has_russian_names(self):
        geos = locators.geometries(tiny_payload())
        self.assertEqual(geos['ru']['labels'][0]['t'], 'река Кендускиг')
        self.assertEqual(geos['ru']['sites'][0]['n'], 'Публичная библиотека Дерри')  # no RU short name
        self.assertNotEqual(locators.digest(geos), locators.digest({'en': geos['en'], 'ru': geos['en']}))

    def test_plan_lists_every_frame(self):
        geos, jobs, manifest = locators.plan(tiny_payload(), 7)
        names = {job['name'] for job in jobs}
        self.assertTrue({'12-panel', '12-card', '12-tile', '12-example', 'town', 'mapcard',
                         '12-panel-ru', 'town-ru', 'mapcard-ru'} <= names)
        panel = next(job for job in jobs if job['name'] == '12-panel')
        self.assertEqual((panel['w'], panel['h'], panel['k'], panel['dpr']), (380, 270, 0.5, 2))
        self.assertEqual((panel['cx'], panel['cy'], panel['sel']), (100.0, 200.0, 12))
        self.assertEqual(manifest['revision'], 7)
        self.assertEqual(manifest['places'], {'12': [100.0, 200.0]})

    def test_pack_writes_webp_and_drops_stale_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp, 'src'), Path(tmp, 'out')
            (src / 'png').mkdir(parents=True)
            out.mkdir()
            (out / '99-panel.webp').write_bytes(b'old')
            jobs = [{'name': '12-panel'}, {'name': 'town'}]
            Image.new('RGB', (760, 540), (200, 210, 190)).save(src / 'png' / '12-panel.png')
            Image.new('RGB', (448, 320), (200, 210, 190)).save(src / 'png' / 'town.png')
            locators.pack(src, jobs, {'digest': 'x'}, out)
            first = (out / '12-panel.webp').read_bytes()
            self.assertFalse((out / '99-panel.webp').exists())
            with Image.open(out / 'town.webp') as town:
                self.assertEqual(town.size, locators.TOWN_STORED)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['files'], ['12-panel.webp', 'town.webp'])
            locators.pack(src, jobs, {'digest': 'x'}, out)
            self.assertEqual((out / '12-panel.webp').read_bytes(), first)  # deterministic
            with self.assertRaises(FileNotFoundError):
                locators.pack(src, jobs + [{'name': '13-panel'}], {}, out)

    def test_pack_refuses_frames_older_than_the_plan_and_keeps_shifted_views(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp, 'src'), Path(tmp, 'out')
            (src / 'png').mkdir(parents=True)
            Image.new('RGB', (760, 540)).save(src / 'png' / '12-panel.png')
            (src / 'png' / 'views.json').write_text(json.dumps({'12-panel': {'cx': 130.5, 'cy': 200, 'k': 0.5}}))
            (src / 'jobs.json').write_text('{}')
            os.utime(src / 'png' / '12-panel.png', (1, 1))           # drawn before this export
            with self.assertRaisesMessage(FileNotFoundError, 'older than jobs.json'):
                locators.pack(src, [{'name': '12-panel'}], {'places': {'12': [100, 200]}}, out)
            os.utime(src / 'png' / '12-panel.png')
            locators.pack(src, [{'name': '12-panel'}], {'places': {'12': [100, 200]}}, out)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['places'], {'12': [130.5, 200]})  # the panel crop as shot


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES=STATIC)
class CommittedLocatorTests(TestCase):
    """The frames in git must match the map data in git (data/initial.json)."""

    @classmethod
    def setUpTestData(cls):
        MapState.objects.get_or_create(pk=1)
        seed = json.loads((settings.BASE_DIR / 'data/initial.json').read_text(encoding='utf-8'))
        ds.commit(lambda _: seed, 'test', 'seed', seed=True)
        state = MapState.objects.select_related('revision').get(pk=1)
        cls.payload = compile_payload(state.revision.after, state.revision_id)

    def test_manifest_matches_the_map_data(self):
        manifest = locators.manifest()
        self.assertIsNotNone(manifest, 'run render_locators export → shoot.cjs → pack')
        self.assertEqual(manifest['digest'], locators.digest(locators.geometries(self.payload)),
                         'locators are stale: rebuild them (render_locators export → shoot.cjs → pack)')

    def test_every_place_has_its_frames_on_disk(self):
        manifest = locators.manifest()
        expected = {'town.webp', 'town-ru.webp', 'mapcard.webp', 'mapcard-ru.webp'}
        for site in self.payload['data']['sites']:
            for preset in locators.PRESETS:
                expected |= {f"{site['id']}-{preset}.webp", f"{site['id']}-{preset}-ru.webp"}
        for key in locators.EXAMPLES:
            expected |= {f'{key}-example.webp', f'{key}-example-ru.webp'}
        self.assertEqual(set(manifest['files']), expected)
        on_disk = {p.name for p in locators.OUTPUT_DIR.glob('*.webp')}
        self.assertEqual(on_disk, expected)

    def test_check_command(self):
        target = 'atlas.management.commands.render_locators.current_payload'
        out = io.StringIO()
        with mock.patch(target, return_value=(self.payload, 'k')):
            call_command('render_locators', 'check', stdout=out)
        self.assertIn('match the map data', out.getvalue())
        moved = copy.deepcopy(self.payload)
        moved['data']['sites'][0]['x'] += 50
        with mock.patch(target, return_value=(moved, 'k')):
            with self.assertRaisesMessage(CommandError, 'Locators are stale'):
                call_command('render_locators', 'check', stdout=io.StringIO())

    def test_town_marker_is_css_in_percent(self):
        mark = locators.town_marker('12')
        self.assertTrue(0 < mark['left'] < 100 and 0 < mark['top'] < 100)
        self.assertTrue(0 < mark['width'] < 20)
        self.assertRegex(mark['style'], r'^left:[\d.]+%;top:[\d.]+%;width:[\d.]+%;height:[\d.]+%$')
        self.assertIsNone(locators.town_marker('U3'))


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES=STATIC)
class LocatorTemplateTests(TestCase):
    def render(self, text, language='en', **context):
        with translation.override(language):
            return Template('{% load atlas_tags %}' + text).render(Context(context))

    def test_place_locator_is_one_link_to_the_map(self):
        html = self.render("{% include 'atlas/locator.html' with preset='panel' key='12' name='Derry Public Library' eager=True %}")
        self.assertIn('<a class="locator locator--panel" href="/?place=12">', html)
        self.assertIn('src="/static/atlas/locators/12-panel.webp" width="380" height="270"', html)
        self.assertIn('alt="Map around Derry Public Library"', html)
        self.assertNotIn('loading="lazy"', html)
        russian = self.render("{% include 'atlas/locator.html' with preset='card' key='12' name='Публичная библиотека Дерри' link=False %}", 'ru')
        self.assertIn('<span class="locator locator--card">', russian)
        self.assertIn('12-card-ru.webp', russian)
        self.assertIn('alt="Карта вокруг: Публичная библиотека Дерри"', russian)
        self.assertIn('loading="lazy"', russian)

    def test_places_without_a_point(self):
        html = self.render("{% include 'atlas/locator.html' with preset='panel' key='U4' name='Juniper Hill' %}")
        self.assertIn('locator--away', html)
        self.assertIn('Off the map', html)
        self.assertIn('Derry → Augusta area, beyond the edge of the map', html)
        russian = self.render("{% include 'atlas/locator.html' with preset='tile' key='U8' name='x' %}", 'ru')
        self.assertIn('За пределами карты', russian)
        self.assertIn('Дерри → Ньюпорт, за краем карты', russian)
        # A place with a point but no frame yet: plain hatching, not "No point on the map".
        missing = self.render("{% include 'atlas/locator.html' with preset='card' key='999' name='New place' %}")
        self.assertIn('<div class="locator locator--none locator--card" aria-hidden="true"></div>', missing)
        town = self.render("{% include 'atlas/locator.html' with preset='tile' key='U3' name='Derry Town Hall' %}", 'ru')
        self.assertIn('locator--nopoint', town)
        self.assertIn('Точки на карте нет', town)
        self.assertNotIn('<a ', town)

    def test_town_inset_marks_the_panel_crop(self):
        html = self.render("{% include 'atlas/locator_town.html' with key='12' %}", 'ru')
        self.assertIn('src="/static/atlas/locators/town-ru.webp" width="224" height="160"', html)
        self.assertRegex(html, r'class="locator-town__frame" style="left:\d+\.\d\d%;')  # no "12,5%" on /ru/
        self.assertEqual(self.render("{% include 'atlas/locator_town.html' with key='U4' %}").strip(), '')

    def test_map_card_uses_the_mapcard_frame(self):
        html = self.render("{% include 'atlas/map_card.html' with places_count=92 %}", 'ru')
        self.assertIn('src="/static/atlas/locators/mapcard-ru.webp" width="400" height="140"', html)
        self.assertIn('92 места, нарисованных по тексту романа', html)
