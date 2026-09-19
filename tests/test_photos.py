import io
import json
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from PIL import Image
from atlas import dataset as ds
from atlas import photos
from atlas.models import Character, Feature, Geometry, MapState, Photo, Tag


def make_image(path, size=(1200, 800), color=(200, 120, 40), mode='RGB', fmt='PNG'):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path, fmt)
    return path


class PhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        geometry = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        Feature.objects.create(key='12', object_type='site', name='Derry Public Library',
                               short='Library', kind='Civic', confidence='B', rank=2,
                               geometry=geometry, metadata={})

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.addCleanup(self.dir.cleanup)
        self.media = self.root / 'media'
        self.source = self.root / 'incoming'
        self.settings_override = override_settings(MEDIA_ROOT=self.media)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def cmd(self, *args):
        out = io.StringIO()
        call_command('photos', *args, stdout=out)
        return out.getvalue()

    def test_add_creates_record_files_and_reference_rows(self):
        src = make_image(self.source / 'library.png', mode='RGBA', color=(200, 120, 40, 255))
        photo = photos.add(src, caption='The library.', feature='12', year=1958,
                           characters=['ben-hanscom'], tags=['library', 'interior'], order=2)
        self.assertEqual((photo.feature_key, photo.year, photo.order, photo.width, photo.height),
                         ('12', 1958, 2, 1200, 800))
        self.assertEqual(photo.original_name, 'library.png')
        self.assertEqual(Character.objects.get(pk='ben-hanscom').name, 'Ben Hanscom')
        self.assertEqual(set(photo.tags.values_list('slug', flat=True)), {'library', 'interior'})
        files = photos.paths_for(photo)
        self.assertEqual(files['original'].read_bytes(), src.read_bytes())
        with Image.open(files['medium']) as m, Image.open(files['thumb']) as t:
            self.assertEqual(m.size, (1200, 800))  # меньше MEDIUM_SIZE — не растягивается
            self.assertLessEqual(max(t.size), photos.THUMB_SIZE)
            self.assertEqual(t.mode, 'RGB')

    def test_medium_is_downscaled_for_large_originals(self):
        src = make_image(self.source / 'big.png', size=(2400, 1600))
        photo = photos.add(src)
        with Image.open(photos.paths_for(photo)['medium']) as m:
            self.assertEqual(m.size, (1600, 1067))

    def test_duplicate_content_is_rejected(self):
        src = make_image(self.source / 'one.png')
        photo = photos.add(src)
        copy = self.source / 'renamed.png'
        copy.write_bytes(src.read_bytes())
        with self.assertRaisesMessage(ValueError, f'photo {photo.id}'):
            photos.add(copy)
        self.assertEqual(Photo.objects.count(), 1)

    def test_validation_rejects_bad_year_feature_slug_and_non_image(self):
        src = make_image(self.source / 'a.png')
        with self.assertRaisesMessage(ValueError, 'allowed set'):
            photos.add(src, year=1957)
        with self.assertRaisesMessage(ValueError, 'does not exist in the atlas'):
            photos.add(src, feature='999')
        with self.assertRaisesMessage(ValueError, 'character slug'):
            photos.add(src, characters=['Ben Hanscom'])
        text = self.source / 'not-image.png'
        text.write_text('plain text')
        with self.assertRaises(ValueError):
            photos.add(text)
        self.assertEqual(Photo.objects.count(), 0)
        self.assertFalse((self.media / 'photos').exists())

    def test_batch_import_is_atomic(self):
        make_image(self.source / 'ok.png', color=(10, 20, 30))
        make_image(self.source / 'bad-year.png', color=(40, 50, 60))
        manifest = [{'file': 'ok.png', 'caption': 'fine', 'feature': '12', 'year': 1958},
                    {'file': 'bad-year.png', 'year': 2001}]
        (self.source / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises(CommandError):
            self.cmd('import', str(self.source))
        self.assertEqual(Photo.objects.count(), 0)
        self.assertFalse((self.media / 'photos').exists())

    def test_batch_import_success_and_duplicate_within_batch(self):
        make_image(self.source / 'a.png', color=(10, 20, 30))
        make_image(self.source / 'b.png', color=(40, 50, 60))
        manifest = [{'file': 'a.png', 'feature': '12', 'year': 1958,
                     'characters': ['ben-hanscom'], 'tags': ['library'], 'caption': 'A'},
                    {'file': 'b.png', 'caption': 'B'}]
        (self.source / 'manifest.json').write_text(json.dumps(manifest))
        output = self.cmd('import', str(self.source))
        self.assertIn('Imported 2 photos.', output)
        self.assertEqual(Photo.objects.count(), 2)
        self.assertEqual(photos.check(), [])
        copy = self.source / 'copy-of-a.png'
        copy.write_bytes((self.source / 'a.png').read_bytes())
        (self.source / 'manifest.json').write_text(json.dumps(
            [{'file': 'a.png'}, {'file': 'copy-of-a.png'}]))
        with self.assertRaises(CommandError):
            self.cmd('import', str(self.source))
        self.assertEqual(Photo.objects.count(), 2)

    def test_edit_changes_attributes_without_touching_files(self):
        photo = photos.add(make_image(self.source / 'a.png'), caption='Old', feature='12',
                           year=1958, tags=['library'])
        before = photos.paths_for(photo)['original'].stat().st_mtime_ns
        self.cmd('edit', str(photo.id), '--caption', 'New caption', '--feature', '',
                 '--tag', 'downtown', '--character', 'beverly-marsh')
        photo.refresh_from_db()
        self.assertEqual((photo.caption, photo.feature_key, photo.year), ('New caption', '', 1958))
        self.assertEqual(set(photo.tags.values_list('slug', flat=True)), {'downtown'})
        self.assertEqual(set(photo.characters.values_list('slug', flat=True)), {'beverly-marsh'})
        self.assertEqual(photos.paths_for(photo)['original'].stat().st_mtime_ns, before)
        self.cmd('edit', str(photo.id), '--no-tags', '--no-characters')
        photo.refresh_from_db()
        self.assertEqual(photo.tags.count() + photo.characters.count(), 0)
        # Справочники не худеют от отвязки: слаги остаются для будущих фото.
        self.assertTrue(Tag.objects.filter(pk='downtown').exists())

    def test_remove_deletes_record_and_files(self):
        photo = photos.add(make_image(self.source / 'a.png'))
        files = photos.paths_for(photo)
        self.cmd('remove', str(photo.id))
        self.assertEqual(Photo.objects.count(), 0)
        self.assertFalse(any(p.exists() for p in files.values()))
        with self.assertRaises(CommandError):
            self.cmd('remove', str(photo.id))

    def test_check_reports_missing_and_orphan_files(self):
        photo = photos.add(make_image(self.source / 'a.png'))
        photos.paths_for(photo)['thumb'].unlink()
        orphan = self.media / 'photos' / 'original' / 'deadbeef.png'
        orphan.write_bytes(b'x')
        problems = photos.check()
        self.assertEqual(len(problems), 2)
        self.assertTrue(any('missing thumb' in p for p in problems))
        self.assertTrue(any('orphan file' in p for p in problems))

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_media_view_serves_immutable_files_and_rejects_traversal(self):
        photo = photos.add(make_image(self.source / 'a.png'))
        rel = photos.relative_paths(photo.sha256, photo.ext)
        response = self.client.get('/media/' + rel['thumb'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'public, max-age=31536000, immutable')
        self.assertEqual(b''.join(response.streaming_content),
                         photos.paths_for(photo)['thumb'].read_bytes())
        self.assertEqual(self.client.get('/media/photos/original/missing.png').status_code, 404)
        # Обход каталога режется до view (400) либо safe_join во view (404).
        self.assertIn(self.client.get('/media/../manage.py').status_code, (400, 404))
        self.assertIn(self.client.get('/media/photos/%2e%2e/%2e%2e/.env').status_code, (400, 404))
        self.assertEqual(self.client.post('/media/' + rel['thumb']).status_code, 405)


class PhotoAtlasInterplayTests(TestCase):
    """Фотоконтур должен переживать полную замену строк атласа при commit()."""

    @classmethod
    def setUpTestData(cls):
        MapState.objects.get_or_create(pk=1)
        seed = json.loads((settings.BASE_DIR / 'data/initial.json').read_text())
        ds.commit(lambda _: seed, 'test', 'seed', seed=True)

    def test_atlas_commit_preserves_photo_binding(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with override_settings(MEDIA_ROOT=root / 'media'):
                photo = photos.add(make_image(root / 'a.png'), feature='12', year=1958)
                call_command('atlas', 'edit', '12', '--name', 'Library renamed',
                             '--author', 'dev', '--reason', 'test', stdout=io.StringIO())
                photo.refresh_from_db()
                self.assertEqual(photo.feature_key, '12')
                self.assertEqual(photos.check(), [])
                call_command('atlas', 'delete', '12', '--author', 'dev', '--reason', 'test',
                             stdout=io.StringIO())
                problems = photos.check()
                self.assertEqual(len(problems), 1)
                self.assertIn("feature '12' no longer exists", problems[0])
