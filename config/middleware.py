"""Язык страницы определяет только префикс URL: / — английская версия,
/ru/ — русская. Accept-Language и cookie сознательно не учитываются:
поведение предсказуемо для людей, ссылок и поисковых роботов."""
from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class UrlLocaleMiddleware(LocaleMiddleware):
    def process_request(self, request):
        language = translation.get_language_from_path(request.path_info) or settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = language
