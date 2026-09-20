from django import template
from django.urls import translate_url

register = template.Library()


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
