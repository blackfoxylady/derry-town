import io
import tempfile
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from atlas import covers
from atlas.models import Feature, Geometry, PlaceCover

from .test_photos import make_image


class CoverData:
    """Общие данные и хелперы: атлас с местами и временный MEDIA_ROOT."""

    @classmethod
    def setUpTestData(cls):
        geometry = Geometry.objects.create(key='g:4', shape={'type': 'point', 'x': 0, 'y': 0})
        Feature.objects.create(key='4', object_type='site', name='Derry Elementary School',
                               confidence='A', geometry=geometry, metadata={})
        Feature.objects.create(key='U3', object_type='unplaced', name='Tracker Brothers',
                               confidence='U', metadata={})
        line = Geometry.objects.create(key='g:road:02', shape={'type': 'line', 'points': [[0, 0], [10, 0]]})
        Feature.objects.create(key='road:02', object_type='road', name='Main Street',
                               geometry=line, metadata={})

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.addCleanup(self.dir.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.root / 'media')
        self.media.enable()
        self.addCleanup(self.media.disable)

    def image(self, name='cover.png', **kwargs):
        kwargs.setdefault('size', (1536, 1024))
        return make_image(self.root / name, **kwargs)


class CoverTests(CoverData, TestCase):
    def test_add_stores_files_and_attributes(self):
        cover = covers.add(self.image(), feature='4', year=1958, alt='School front, 1958.',
                           alt_ru='Фасад школы, 1958.')
        self.assertEqual((cover.feature_key, cover.year), ('4', 1958))
        self.assertEqual((cover.width, cover.height), (1536, 1024))
        for kind, path in covers.paths_for(cover).items():
            self.assertTrue(path.is_file(), kind)
        self.assertEqual(covers.check(), [])

    def test_year_and_alt_are_required(self):
        with self.assertRaisesMessage(ValueError, 'year is required'):
            covers.add(self.image(), feature='4', alt='x')
        with self.assertRaisesMessage(ValueError, 'alt text is required'):
            covers.add(self.image(), feature='4', year=1958, alt='   ')
        with self.assertRaisesMessage(ValueError, 'not in the allowed set'):
            covers.add(self.image(), feature='4', year=1900, alt='x')
        self.assertEqual(PlaceCover.objects.count(), 0)
        self.assertFalse((self.root / 'media').exists())

    def test_cover_binds_to_places_only(self):
        with self.assertRaisesMessage(ValueError, 'does not exist'):
            covers.add(self.image(), feature='99', year=1958, alt='x')
        with self.assertRaisesMessage(ValueError, 'covers belong to places'):
            covers.add(self.image(), feature='road:02', year=1958, alt='x')
        covers.add(self.image(), feature='U3', year=1958, alt='Tracker Brothers yard.')

    def test_one_cover_per_year_two_per_place(self):
        covers.add(self.image('a.png', color=(10, 0, 0)), feature='4', year=1958, alt='a')
        with self.assertRaisesMessage(ValueError, 'already has a cover for 1958'):
            covers.add(self.image('b.png', color=(20, 0, 0)), feature='4', year=1958, alt='b')
        covers.add(self.image('c.png', color=(30, 0, 0)), feature='4', year=1985, alt='c')
        with self.assertRaisesMessage(ValueError, 'already has 2 covers'):
            covers.add(self.image('d.png', color=(40, 0, 0)), feature='4', year=1929, alt='d')

    def test_duplicate_content_rejected(self):
        covers.add(self.image('a.png'), feature='4', year=1958, alt='a')
        with self.assertRaisesMessage(ValueError, 'same content hash'):
            covers.add(self.image('b.png'), feature='U3', year=1958, alt='b')

    def test_edit_and_remove(self):
        cover = covers.add(self.image(), feature='4', year=1958, alt='Old alt.')
        covers.edit(cover.id, year=1985, alt='New alt.', alt_ru='Новый alt.')
        cover.refresh_from_db()
        self.assertEqual((cover.year, cover.alt, cover.alt_ru), (1985, 'New alt.', 'Новый alt.'))
        with self.assertRaisesMessage(ValueError, 'covers belong to places'):
            covers.edit(cover.id, feature='road:02')
        files = list(covers.paths_for(cover).values())
        covers.remove(cover.id)
        self.assertEqual(PlaceCover.objects.count(), 0)
        self.assertFalse(any(p.exists() for p in files))

    def test_check_reports_problems(self):
        cover = covers.add(self.image(), feature='4', year=1958, alt='x')
        covers.paths_for(cover)['medium'].unlink()
        (covers.cover_root() / 'stray.jpg').write_bytes(b'x')
        PlaceCover.objects.filter(pk=cover.id).update(feature_key='gone')
        problems = covers.check()
        self.assertTrue(any('missing medium' in p for p in problems))
        self.assertTrue(any('orphan file' in p for p in problems))
        self.assertTrue(any("feature 'gone' no longer exists" in p for p in problems))

    def test_import_from_manifest_all_or_nothing(self):
        import json
        batch = self.root / 'covers-batch'
        make_image(batch / 'a.png', size=(1536, 1024), color=(10, 0, 0))
        make_image(batch / 'b.png', size=(1536, 1024), color=(20, 0, 0))
        entries = [{'file': 'a.png', 'feature': '4', 'year': 1958, 'alt': 'School, 1958.',
                    'alt_ru': 'Школа, 1958.'},
                   {'file': 'b.png', 'feature': '4', 'year': 1985, 'alt': 'School, 1985.'}]
        # Ошибка в любой записи откатывает всю партию.
        broken = entries + [{'file': 'a.png', 'feature': '4', 'year': 1958, 'alt': 'dup'}]
        (batch / 'manifest.json').write_text(json.dumps(broken), encoding='utf-8')
        with self.assertRaises(CommandError):
            call_command('covers', 'import', str(batch), stdout=io.StringIO())
        self.assertEqual(PlaceCover.objects.count(), 0)
        (batch / 'manifest.json').write_text(json.dumps(entries), encoding='utf-8')
        out = io.StringIO()
        call_command('covers', 'import', str(batch), stdout=out)
        self.assertIn('Imported 2 covers.', out.getvalue())
        self.assertEqual(list(PlaceCover.objects.values_list('year', flat=True)), [1958, 1985])
        self.assertEqual(covers.check(), [])

    def test_manifest_rejects_unknown_fields(self):
        with self.assertRaisesMessage(ValueError, 'Unknown cover fields'):
            covers.add_many([{'file': self.image(), 'feature': '4', 'year': 1958,
                              'alt': 'x', 'caption': 'nope'}])

    def test_management_command_round_trip(self):
        out = io.StringIO()
        call_command('covers', 'add', str(self.image()), '--feature', '4', '--year', '1958',
                     '--alt', 'School front.', '--alt-ru', 'Фасад школы.', stdout=out)
        self.assertIn('Added', out.getvalue())
        cover = PlaceCover.objects.get()
        out = io.StringIO()
        call_command('covers', 'show', cover.id, stdout=out)
        self.assertIn('/media/covers/original/', out.getvalue())
        out = io.StringIO()
        call_command('covers', 'check', stdout=out)
        self.assertIn('consistent', out.getvalue())
        with self.assertRaises(CommandError):
            call_command('covers', 'edit', cover.id, stdout=io.StringIO())  # nothing to change
        call_command('covers', 'remove', cover.id, stdout=io.StringIO())
        self.assertEqual(PlaceCover.objects.count(), 0)


# Обычное статическое хранилище: манифест whitenoise в тестах не собирается.
@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CoverPageTests(CoverData, TestCase):
    def test_place_page_without_cover_has_no_block(self):
        response = self.client.get('/places/4-derry-elementary-school/')
        self.assertNotContains(response, 'place-cover')

    def test_single_cover_renders_without_switch(self):
        covers.add(self.image(), feature='4', year=1958, alt='School front, 1958.')
        response = self.client.get('/places/4-derry-elementary-school/')
        self.assertContains(response, 'place-cover')
        self.assertContains(response, 'alt="School front, 1958."')
        self.assertContains(response, '/media/covers/medium/')
        self.assertContains(response, '/media/covers/large/')
        self.assertNotContains(response, 'cover-years')
        # Превью для соцсетей — заглавное фото.
        self.assertContains(response, 'og:image')
        self.assertContains(response, '/media/covers/large/', status_code=200)

    def test_two_covers_render_switch_sorted_by_year(self):
        covers.add(self.image('b.png', color=(60, 60, 90)), feature='4', year=1985, alt='School, 1985.')
        covers.add(self.image('a.png', color=(200, 160, 90)), feature='4', year=1958, alt='School, 1958.')
        response = self.client.get('/places/4-derry-elementary-school/')
        content = response.content.decode()
        self.assertIn('cover-years', content)
        self.assertIn('aria-pressed="true">1958<', content)
        self.assertIn('aria-pressed="false">1985<', content)
        # 1958 показан по умолчанию (первый в стопке), 1985 грузится лениво.
        self.assertLess(content.index('data-year="1958"'), content.index('data-year="1985"'))
        self.assertIn('loading="lazy"', content)

    def test_alt_is_localized_with_fallback(self):
        covers.add(self.image('a.png'), feature='4', year=1958,
                   alt='School front.', alt_ru='Фасад школы.')
        covers.add(self.image('b.png', color=(1, 2, 3)), feature='4', year=1985, alt='School later.')
        response = self.client.get('/ru/places/4-derry-elementary-school/')
        self.assertContains(response, 'alt="Фасад школы."')
        self.assertContains(response, 'alt="School later."')  # пустой перевод откатывается
        self.assertContains(response, 'aria-label="Год"')

    def test_cover_not_duplicated_in_photo_sections(self):
        covers.add(self.image(), feature='4', year=1958, alt='School front.')
        response = self.client.get('/places/4-derry-elementary-school/')
        self.assertNotContains(response, '<h2>Photographs</h2>')  # секции нет: фото места нет
        # Контуры не пересекаются: галерея и карта не видят заглавные фото.
        self.assertNotContains(self.client.get('/photos/'), '/media/covers/')
        data = self.client.get('/api/v1/photos/').json()
        self.assertEqual(data['features'], {})
