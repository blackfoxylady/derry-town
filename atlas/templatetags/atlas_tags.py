import json
from django import template
from django.urls import translate_url
from django.utils.safestring import mark_safe

register = template.Library()

# Внутри <script> JSON нельзя оставлять сырым: '</script>' в подписи фото
# оборвал бы тег. Экранирование то же, что у стандартного json_script.
_JSON_SCRIPT_ESCAPES = {ord('<'): '\\u003C', ord('>'): '\\u003E', ord('&'): '\\u0026'}


@register.simple_tag
def jsonld(data):
    """Блок микроразметки <script type="application/ld+json"> из словаря."""
    if not data:
        return ''
    return mark_safe('<script type="application/ld+json">'
                     + json.dumps(data, ensure_ascii=False).translate(_JSON_SCRIPT_ESCAPES)
                     + '</script>')


@register.simple_tag(takes_context=True)
def lang_url(context, lang):
    """Адрес текущей страницы на другом языке — для переключателя в шапке.
    Пути различаются только префиксом /ru/, query-параметры сохраняются."""
    return translate_url(context['request'].get_full_path(), lang)


@register.simple_tag(takes_context=True)
def canonical_url(context):
    """Канонический абсолютный адрес страницы: без query-параметров,
    чтобы фильтры галереи не плодили дубли в индексе."""
    request = context['request']
    return request.build_absolute_uri(request.path)


@register.simple_tag(takes_context=True)
def absolute_url(context, path):
    """Абсолютный адрес относительного пути — для og:image и подобных мета-тегов,
    где соцсети требуют полный URL."""
    return context['request'].build_absolute_uri(path)


@register.simple_tag(takes_context=True)
def alternate_url(context, lang):
    """Абсолютный адрес страницы в заданном языке — для hreflang."""
    request = context['request']
    return request.build_absolute_uri(translate_url(request.path, lang))
