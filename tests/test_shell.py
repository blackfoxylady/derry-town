"""Оболочка сайта (редизайн, блок 02): шапка, дропдаун About Derry, меню-панель,
крошки, футер и cookie-уведомление на контентных страницах."""
import re
from datetime import date

from django.test import TestCase, override_settings
from atlas.models import Feature, Geometry


def nav(html, cls):
    """Содержимое первого <nav class="cls">…</nav>."""
    return html.split(f'<nav class="{cls}"', 1)[1].split('</nav>', 1)[0]


def current(html):
    """Подписи ссылок nav.nav с aria-current: {подпись: значение}."""
    found = re.findall(r'class="nav__link" aria-current="(\w+)">([^<]+)<', nav(html, 'nav'))
    return {label: value for value, label in found}


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ShellTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        point = Geometry.objects.create(key='g:12', shape={'type': 'point', 'x': 0, 'y': 0})
        Feature.objects.create(key='12', object_type='site', name='Derry Public Library',
                               short='Library', kind='Civic', confidence='A', rank=2,
                               geometry=point, metadata={})

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.content.decode()

    def test_every_content_page_has_one_shell(self):
        for path in ('/places/', '/places/12-derry-public-library/', '/photos/', '/method/',
                     '/is-derry-maine-real/', '/how-bangor-inspired-derry-maine/',
                     '/books-set-in-derry-maine/', '/printable-derry-map/', '/articles/'):
            html = self.page(path)
            body = html.split('<body class="shell">', 1)[1]
            # Skip link first, then the cookie notice, then the header.
            self.assertTrue(body.lstrip().startswith('<a class="skip-link" href="#main">Skip to content</a>'), path)
            self.assertLess(body.index('id="cookieConsent"'), body.index('class="site-header"'), path)
            self.assertRegex(body, r'<main class="page( page--(editorial|place|index|gallery))?" id="main"')
            self.assertEqual(html.count('class="site-header"'), 1, path)
            self.assertEqual(html.count('class="site-footer"'), 1, path)
            # The menu panel is server HTML and not a <dialog> element.
            self.assertIn('<div class="panel" id="site-menu" role="dialog" aria-modal="true"', html)
            self.assertNotIn('<dialog', html)
            self.assertEqual(html.count('data-cookie-settings'), 2, path)  # footer + panel
            self.assertNotIn('NOVEL-BASED RECONSTRUCTION', html)
            self.assertNotIn('How to cite', html)

    def test_current_page_and_section(self):
        self.assertEqual(current(self.page('/places/')), {'Places': 'page'})
        self.assertEqual(current(self.page('/places/12-derry-public-library/')), {'Places': 'true'})
        self.assertEqual(current(self.page('/photos/')), {'Photos': 'page'})
        self.assertEqual(current(self.page('/method/')), {'Method': 'page'})
        article = self.page('/how-bangor-inspired-derry-maine/')
        self.assertEqual(current(article), {})
        self.assertIn('nav__disclosure is-section" aria-expanded="false"', article)
        dropdown = article.split('id="about-menu"', 1)[1].split('</div>', 1)[0]
        self.assertEqual(dropdown.count('aria-current="page"'), 1)
        self.assertIn('<a href="/how-bangor-inspired-derry-maine/" aria-current="page">', dropdown)
        self.assertNotIn('is-section', self.page('/places/'))
        # /articles/ is not in the navigation, but belongs to the About Derry section.
        listing = self.page('/articles/')
        self.assertEqual(current(listing), {})
        self.assertIn('nav__disclosure is-section"', listing)
        self.assertNotIn('href="/articles/"', listing.split('<main', 1)[0])
        self.assertNotIn('href="/articles/"', listing.split('class="site-footer"', 1)[1])

    def test_breadcrumb_root_is_the_map(self):
        crumbs = nav(self.page('/places/12-derry-public-library/'), 'crumbs')
        self.assertIn('aria-label="Breadcrumb"', crumbs)
        self.assertIn('<li><a href="/">Map</a></li>', crumbs)
        self.assertIn('<span aria-current="page">Derry Public Library</span>', crumbs)
        self.assertIn('<li><a href="/ru/">Карта</a></li>', nav(self.page('/ru/places/'), 'crumbs'))

    def test_footer_year_is_not_hard_coded(self):
        year = date.today().year
        for path in ('/places/', '/ru/places/', '/'):
            self.assertIn(f'© {year} derryfiles.space · ', self.page(path))

    def test_russian_labels(self):
        html = self.page('/ru/photos/')
        labels = re.findall(r'class="nav__link[^"]*"[^>]*>([^<]+)<', nav(html, 'nav'))
        self.assertEqual(labels, ['Карта', 'Места', 'Фото', 'О Дерри', 'Метод'])
        self.assertIn('aria-label="Главное меню"', html)
        self.assertIn('role="group" aria-label="Язык"', html)
        self.assertIn('aria-label="Меню"', html)
        self.assertIn('aria-label="Дерри, литературный атлас: на главную"', html)
        self.assertIn('Источники и метод', html.split('class="site-footer"', 1)[1])
        self.assertIn('Литературный атлас, не путеводитель по местам съёмок', html)
        # The cookie notice keeps the production text (decision 23.10).
        self.assertIn('Мы используем дополнительные файлы cookie для анализа посещаемости сайта.', html)

    def test_language_switch_keeps_the_page(self):
        html = self.page('/places/')
        self.assertIn('<span class="lang" role="group" aria-label="Language"><span aria-current="true">EN</span>'
                      '<a href="/ru/places/" hreflang="ru" lang="ru">RU</a></span>', html)
