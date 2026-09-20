from django.test import TestCase, override_settings


# Обычное статическое хранилище: манифест whitenoise в тестах не собирается.
@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class I18nRoutingTests(TestCase):
    def test_pages_exist_in_both_languages(self):
        for path, lang in (('/', 'en'), ('/ru/', 'ru'), ('/photos/', 'en'), ('/ru/photos/', 'ru')):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, f'<html lang="{lang}"')

    def test_language_ignores_accept_language_header(self):
        # Язык определяет только префикс URL: / остаётся английской и для
        # русскоязычного браузера — никаких автоматических редиректов.
        response = self.client.get('/', HTTP_ACCEPT_LANGUAGE='ru')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="en"')

    def test_switcher_links_to_the_same_page_in_the_other_language(self):
        self.assertContains(self.client.get('/'), 'href="/ru/"')
        self.assertContains(self.client.get('/ru/'), 'href="/"')
        # Query-параметры фильтров сохраняются при переключении языка.
        self.assertContains(self.client.get('/photos/', {'place': '12'}),
                            'href="/ru/photos/?place=12"')
        self.assertContains(self.client.get('/ru/photos/', {'place': '12'}),
                            'href="/photos/?place=12"')

    def test_service_routes_have_no_language_prefix(self):
        for path in ('/ru/api/v1/map/', '/ru/healthz/'):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_ru_gallery_links_stay_under_ru_prefix(self):
        response = self.client.get('/ru/photos/')
        self.assertContains(response, 'href="/ru/photos/"')

    def test_russian_ui_strings_render(self):
        self.assertContains(self.client.get('/ru/'), 'РЕКОНСТРУКЦИЯ ПО РОМАНУ')
        self.assertContains(self.client.get('/ru/photos/'), 'Фотографии')
        self.assertContains(self.client.get('/ru/method/'), 'Построено по роману')
        # Каталог для map.js содержит наши msgid (кириллица в нём \u-экранирована).
        response = self.client.get('/ru/jsi18n/')
        self.assertContains(response, 'Place page')
        self.assertContains(response, '\\u0421\\u0442\\u0440\\u0430\\u043d\\u0438\\u0446\\u0430')
        # Английская версия остаётся английской.
        self.assertContains(self.client.get('/'), 'NOVEL-BASED RECONSTRUCTION')
