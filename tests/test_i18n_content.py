import io
import json
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from atlas import dataset as ds, photos
from atlas.models import Evidence, Feature, Geometry, MapState, Photo, Setting, Source

from .test_photos import make_image


# Обычное статическое хранилище: манифест whitenoise в тестах не собирается.
@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class RuContentTests(TestCase):
    """Русские тексты из metadata, реестров и БД с фолбэком на английский."""

    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        cls.library = Feature.objects.create(
            key='12', object_type='site', name='Derry Public Library', short='Library',
            kind='Civic', confidence='B', rank=2, period='1958', note='A stone building.',
            about='The library is a civic landmark.',
            confidence_explanation='Its street relationship is inferred.', geometry=point,
            metadata={'ru': {'note': 'Каменное здание.', 'about': 'Библиотека — городской ориентир.',
                             'evidence': {'e1': 'Бен читает здесь.'}}})
        book = Source.objects.create(key='novel', title='IT', kind='book')
        Evidence.objects.create(key='e1', feature=cls.library, source=book,
                                reference='Ch. 4 - Ben Hanscom / 1', note='Ben reads here.', order=1)
        Evidence.objects.create(key='e2', feature=cls.library, source=book,
                                reference='Ch. 4 - Ben Hanscom / 1', note='Second mention.', order=2)
        Setting.objects.create(key='atlas', value={'method_geometry': 'Canal length is inferred.'})
        Setting.objects.create(key='i18n_ru', value={'method_geometry': 'Длина канала выведена.'})

    def test_place_page_russian_note_with_fallback(self):
        response = self.client.get('/ru/places/12-derry-public-library/')
        self.assertContains(response, 'Каменное здание.')
        self.assertContains(response, 'Бен читает здесь.')
        self.assertContains(response, 'Second mention.')  # без перевода — английский
        self.assertContains(response, 'Публичная библиотека Дерри')
        self.assertContains(response, 'Ch. 4 - Ben Hanscom / 1')  # главы — в оригинале
        self.assertContains(response, 'Библиотека — городской ориентир.')
        # Для отсутствующего русского поля действует поэлементный fallback на английский.
        self.assertContains(response, 'Its street relationship is inferred.')
        self.assertContains(response, 'О месте: Публичная библиотека Дерри')
        self.assertContains(response, 'Почему месту присвоен уровень B')
        response = self.client.get('/places/12-derry-public-library/')
        self.assertContains(response, 'A stone building.')
        self.assertContains(response, 'The library is a civic landmark.')
        self.assertNotContains(response, 'Каменное здание.')

    def test_place_names_are_localized_without_changing_canonical_urls(self):
        russian = self.client.get('/ru/places/12-derry-public-library/')
        self.assertContains(russian, '<h1>Публичная библиотека Дерри</h1>')
        self.assertContains(russian, 'Узнайте о месте «Публичная библиотека Дерри»')
        self.assertContains(
            russian,
            '<link rel="canonical" href="http://testserver/ru/places/12-derry-public-library/">')
        self.assertNotContains(russian, '/places/12-publichnaia-biblioteka-derri/')

        catalog = self.client.get('/ru/places/')
        self.assertContains(catalog, '>Публичная библиотека Дерри</a>')
        self.assertContains(
            catalog,
            'data-search="12 Derry Public Library Library Публичная библиотека Дерри')

        english = self.client.get('/places/12-derry-public-library/')
        self.assertContains(english, '<h1>Derry Public Library</h1>')
        self.assertNotContains(english, 'Публичная библиотека Дерри')

    def test_method_page_russian_geometry_note(self):
        self.assertContains(self.client.get('/ru/method/'), 'Длина канала выведена.')
        self.assertContains(self.client.get('/method/'), 'Canal length is inferred.')

    def test_photo_caption_ru_on_pages_and_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with override_settings(MEDIA_ROOT=root / 'media'):
                make_image(root / 'a.png', color=(10, 20, 30))
                photo = photos.add(
                    root / 'a.png', caption='Ben at the library.',
                    caption_ru='Бен в библиотеке.', feature='12', year=1958,
                    characters=['pennywise'], tags=['school'],
                )
                self.assertContains(self.client.get(f'/ru/photos/{photo.id}/'), 'Бен в библиотеке.')
                self.assertContains(self.client.get(f'/ru/photos/{photo.id}/'), 'Пеннивайз')
                self.assertContains(self.client.get(f'/ru/photos/{photo.id}/'), '>школа</a>')
                self.assertNotContains(self.client.get(f'/ru/photos/{photo.id}/'), '>Pennywise</a>')
                self.assertContains(self.client.get(f'/photos/{photo.id}/'), 'Ben at the library.')
                self.assertContains(self.client.get('/ru/photos/'), 'Бен в библиотеке.')
                data = self.client.get('/api/v1/photos/', {'lang': 'ru'}).json()
                self.assertEqual(data['features']['12']['photos'][0]['caption'], 'Бен в библиотеке.')
                self.assertEqual(data['features']['12']['name'], 'Публичная библиотека Дерри')
                data = self.client.get('/api/v1/photos/').json()
                self.assertEqual(data['features']['12']['photos'][0]['caption'], 'Ben at the library.')
                self.assertEqual(data['features']['12']['name'], 'Derry Public Library')
                # Правка перевода без пересоздания записи.
                photos.edit(photo.id, caption_ru='Бен читает.')
                self.assertContains(self.client.get(f'/ru/photos/{photo.id}/'), 'Бен читает.')

    def test_versioned_photo_caption_replaces_mixed_database_translation_everywhere(self):
        english = (
            'Ben Hanscom watches Beverly Marsh run down the steps of Derry Elementary School '
            'as summer vacation begins.')
        mixed = (
            'Ben Hanscom смотрит, как Beverly Marsh сбегает по ступеням школы '
            'Derry Elementary School в начале летних каникул.')
        translated = (
            'Бен Хэнском смотрит, как Беверли Марш сбегает по ступеням начальной школы '
            'Дерри в начале летних каникул.')
        photo = Photo.objects.create(
            sha256='e8c7247f080ee16c74e04c92c52db3edd41c3f42edc7f029c22fb70ab92ebf46',
            ext='jpg', original_name='school.jpg', caption=english, caption_ru=mixed,
            year=1958, feature_key='12', width=1200, height=800)

        page = self.client.get(f'/ru/photos/{photo.id}/')
        self.assertContains(page, f'<h1>{translated}</h1>')
        self.assertContains(page, f'alt="{translated}"')
        self.assertContains(page, '<a href="/ru/">Дерри</a>')
        self.assertNotContains(page, mixed)
        self.assertContains(self.client.get('/ru/photos/'), translated)

        api = self.client.get('/api/v1/photos/', {'lang': 'ru'}).json()
        api_photo = next(item for item in api['features']['12']['photos']
                         if item['id'] == photo.id)
        self.assertEqual(api_photo['caption'], translated)

        english_page = self.client.get(f'/photos/{photo.id}/')
        self.assertContains(english_page, f'<h1>{english}</h1>')
        photo.refresh_from_db()
        self.assertEqual(photo.caption_ru, mixed)  # реестр не изменяет рабочую БД

    def test_published_photo_caption_registry_is_complete_and_fully_russian(self):
        captions = json.loads(
            (settings.BASE_DIR / 'data/photo_captions_ru.json').read_text(encoding='utf-8'))
        self.assertEqual(len(captions), 18)
        for sha256, caption in captions.items():
            self.assertEqual(len(sha256), 64)
            int(sha256, 16)
            self.assertTrue(caption.endswith(('.', '!', '»')))
        corpus = '\n'.join(captions.values())
        for english_name in ('Ben Hanscom', 'Beverly Marsh', 'Bill Denbrough',
                             'Derry Elementary School', 'Eddie Kaspbrak', 'Kenduskeag',
                             'Mike Hanlon', 'Richie Tozier', 'Stan Uris', 'Pennywise',
                             'Paul Bunyan', 'Adrian Mellon', 'Don Hagarty',
                             'Main Street Bridge', 'Kleen-Kloze'):
            self.assertNotIn(english_name, corpus)

    def test_proper_name_glossary_keeps_approved_general_terms(self):
        glossary = json.loads(
            (settings.BASE_DIR / 'data/proper_names_ru.json').read_text(encoding='utf-8'))
        self.assertEqual(glossary['terms']['Pennywise'], 'Пеннивайз')
        self.assertEqual(glossary['terms']['Adrian Mellon'], 'Адриан Меллон')
        self.assertEqual(glossary['terms']['Main Street Bridge'], 'мост на Главной улице')
        self.assertEqual(glossary['terms']["Losers' Club"], 'Клуб Неудачников')
        self.assertEqual(glossary['characters']['pennywise'], 'Пеннивайз')
        expected_photo_tags = {
            'balloons': 'воздушные шары',
            'canal': 'Канал',
            'canal-days': 'Дни Канала',
            'cleaning-up': 'уборка',
            'georgies-room': 'комната Джорджи',
            'giant-bird': 'гигантская птица',
            'interludes': 'интерлюдии',
            'laundromat': 'прачечная',
            'losers-club': 'Клуб Неудачников',
            'main-street-bridge': 'мост на Главной улице',
            'night': 'ночь',
            'paul-bunyan': 'Пол Баньян',
            'photo-album': 'фотоальбом',
            'police': 'полиция',
            'pov': 'точка зрения',
            'school': 'школа',
            'summer': 'лето',
            'summer-vacation': 'летние каникулы',
            'supernatural': 'сверхъестественное',
            'vacation': 'каникулы',
            'winter': 'зима',
        }
        for slug, name in expected_photo_tags.items():
            self.assertEqual(glossary['tags'][slug], name)


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AtlasEditRuTests(TestCase):
    """Полный контур: atlas edit --description-ru → ревизия → /api/v1/map/?lang=ru."""

    @classmethod
    def setUpTestData(cls):
        MapState.objects.get_or_create(pk=1)
        seed = json.loads((settings.BASE_DIR / 'data/initial.json').read_text())
        ds.commit(lambda _: seed, 'test', 'seed', seed=True)

    def cmd(self, *args):
        out = io.StringIO()
        call_command('atlas', *args, stdout=out)
        return out.getvalue()

    def test_description_ru_flows_into_localized_map_payload(self):
        self.cmd('edit', '12', '--description-ru', 'Русское описание библиотеки.',
                 '--author', 'dev', '--reason', 'ru note')
        self.assertEqual(Feature.objects.get(pk='12').metadata['ru']['note'],
                         'Русское описание библиотеки.')
        with tempfile.TemporaryDirectory() as artifacts:
            with override_settings(ARTIFACT_ROOT=Path(artifacts)):
                en = self.client.get('/api/v1/map/')
                ru = self.client.get('/api/v1/map/', {'lang': 'ru'})
        self.assertNotEqual(en['ETag'], ru['ETag'])
        site_en = next(s for s in en.json()['data']['sites'] if s['id'] == 12)
        site_ru = next(s for s in ru.json()['data']['sites'] if s['id'] == 12)
        self.assertEqual(site_ru['note'], 'Русское описание библиотеки.')
        self.assertNotEqual(site_en['note'], site_ru['note'])
        # Основная карта переводится отдельным этапом; её payload пока сохраняет каноническое имя.
        self.assertEqual(site_en['name'], site_ru['name'])

    def test_shipped_translation_patch_applies_cleanly(self):
        self.cmd('apply', str(settings.BASE_DIR / 'data/i18n_ru.json'),
                 '--author', 'dev', '--reason', 'ru corpus')
        feature = Feature.objects.get(pk='12')
        self.assertIn('стеклянный переход', feature.metadata['ru']['note'])
        self.assertTrue(feature.note.startswith('At Kansas Street'))  # canonical не тронут
        self.assertIn('водонапорную башню',
                      Setting.objects.get(pk='i18n_ru').value['method_geometry'])
        self.assertContains(self.client.get('/ru/places/12-derry-public-library/'),
                            'стеклянный переход')
        school = Feature.objects.get(pk='4')
        self.assertTrue(school.metadata['ru']['about'].startswith('Начальная школа Дерри —'))
        self.assertIn('точный земельный участок',
                      school.metadata['ru']['confidence_explanation'])
        school_page = self.client.get('/ru/places/4-derry-elementary-school/')
        self.assertContains(school_page, 'О месте: Начальная школа Дерри')
        self.assertContains(school_page, 'общественный ориентир')
        self.assertContains(school_page, 'Почему месту присвоен уровень A')
        self.assertContains(self.client.get('/ru/method/'), 'водонапорную башню')
        self.assertContains(self.client.get('/method/'), 'Standpipe')  # английская без изменений

        translated = json.dumps(
            [item['values'] for item in json.loads(
                (settings.BASE_DIR / 'data/i18n_ru.json').read_text(encoding='utf-8'))],
            ensure_ascii=False)
        for english_name in ('Witcham Street', 'Beverly Marsh', 'Zack Denbrough',
                             'Mrs Kersh', 'Kenduskeag', 'Matthew Clements',
                             'Bullseye', 'Penobscot'):
            self.assertNotIn(english_name, translated)

    def test_clearing_description_ru_removes_metadata_key(self):
        self.cmd('edit', '12', '--description-ru', 'Черновик.', '--author', 'dev', '--reason', 'set')
        self.cmd('edit', '12', '--description-ru', '', '--author', 'dev', '--reason', 'clear')
        self.assertEqual(Feature.objects.get(pk='12').metadata, {})

    def test_edit_place_content_in_both_languages_and_clear_translation(self):
        self.cmd('edit', '12', '--about', 'English overview.',
                 '--confidence-explanation', 'English placement explanation.',
                 '--about-ru', 'Русская справка.',
                 '--confidence-explanation-ru', 'Русское объяснение привязки.',
                 '--author', 'dev', '--reason', 'place content')
        feature = Feature.objects.get(pk='12')
        self.assertEqual(feature.about, 'English overview.')
        self.assertEqual(feature.confidence_explanation, 'English placement explanation.')
        self.assertEqual(feature.metadata['ru']['about'], 'Русская справка.')
        self.assertEqual(feature.metadata['ru']['confidence_explanation'],
                         'Русское объяснение привязки.')

        self.cmd('edit', '12', '--about-ru', '', '--confidence-explanation-ru', '',
                 '--author', 'dev', '--reason', 'clear translated place content')
        feature.refresh_from_db()
        self.assertNotIn('about', feature.metadata.get('ru', {}))
        self.assertNotIn('confidence_explanation', feature.metadata.get('ru', {}))
