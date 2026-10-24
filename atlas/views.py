from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape
from django.conf import settings
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse, HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, translate_url
from django.utils._os import safe_join
from django.utils.text import slugify
from django.utils.translation import get_language, gettext_lazy as _, ngettext, pgettext
from django.views.decorators.http import require_safe
from . import schema
from .covers import COVER_LARGE_SIZE, COVER_MEDIUM_SIZE, relative_paths as cover_relative_paths
from .localized_names import (character_name, feature_name, feature_search_terms,
                              localize_map_payload, russian_search_terms, tag_name)
from .localized_photos import photo_caption
from .models import (Character, Evidence, Feature, MapState, Photo, PlaceCover,
                     Revision, Setting, Source, Tag)
from .photos import GRID_WIDTHS, MEDIUM_SIZE, THUMB_SIZE, relative_paths
from .locators import EXAMPLES as LOCATOR_EXAMPLES
from .rendering import current_payload, RENDER_VERSION
from .terms import (CONFIDENCE_EXPLANATIONS, CONFIDENCE_LABELS, CONFIDENCE_META,
                    chapter_short, confidence_label, confidence_levels, kind_label,
                    novel_reference_rows, novel_references, parse_reference, period_label,
                    same_chapters_heading)


HUB_LASTMOD = date(2026, 9, 29)
RU_MAP_PAYLOAD_VERSION = '3'
HUB_PAGES = {
    'real': {
        'template': 'atlas/derry_real.html',
        'title': {
            'en': 'Is Derry, Maine Real? Stephen King’s Fictional Town Explained',
            'ru': 'Существует ли Дерри, штат Мэн? Город Стивена Кинга',
        },
        'description': {
            'en': ('Derry, Maine is fictional. Learn where Stephen King places it, how Bangor '
                   'inspired the town, what the novel says about its size, and what this atlas '
                   'reconstructs.'),
            'ru': ('Дерри, штат Мэн, — вымышленный город. Где Стивен Кинг его размещает, как '
                   'Бангор повлиял на образ города и что реконструирует этот атлас.'),
        },
        'breadcrumb': {'en': 'Is Derry, Maine real?', 'ru': 'Существует ли Дерри, штат Мэн?'},
        'url_name': 'derry_real',
        'eyebrow': {'en': 'A guide to the Derry of the novel',
                    'ru': 'Путеводитель по книжному Дерри'},
        'heading': {'en': 'Is Derry, Maine a real town?', 'ru': 'Существует ли Дерри, штат Мэн?'},
        'answer_label': {'en': 'Short answer', 'ru': 'Краткий ответ'},
        # Оглавление строится по H2 статьи (решение 23.10): подписи повторяют заголовки.
        'toc': {
            'en': (('where', 'Where is Derry supposed to be?'),
                   ('bangor', 'Is Bangor the real Derry?'),
                   ('census', 'Does Derry have a population, county or ZIP code?'),
                   ('visit', 'Can you visit Derry?'),
                   ('map', 'What does this map show?'),
                   ('sources', 'Sources')),
            'ru': (('where', 'Где находится Дерри?'),
                   ('bangor', 'Бангор — это настоящий Дерри?'),
                   ('census', 'Есть ли у Дерри население, округ и почтовый индекс?'),
                   ('visit', 'Можно ли посетить Дерри?'),
                   ('map', 'Что показывает эта карта?'),
                   ('sources', 'Источники')),
        },
        'topics': {
            'en': ('Where King places Derry', 'Is Bangor the real Derry',
                   'County, population and ZIP code', 'Can you visit'),
            'ru': ('Где Кинг помещает Дерри', 'Бангор — это настоящий Дерри?',
                   'Округ, население и почтовый индекс', 'Можно ли туда поехать'),
        },
    },
    'bangor': {
        'template': 'atlas/derry_bangor.html',
        'title': {
            'en': 'How Bangor Inspired Derry, Maine — Stephen King’s IT',
            'ru': 'Как Бангор вдохновил Дерри, штат Мэн — «Оно» Стивена Кинга',
        },
        'description': {
            'en': ('Compare fictional Derry with Bangor, Maine: the canal, Kenduskeag Stream, '
                   'Thomas Hill Standpipe, library and other real-world echoes behind IT.'),
            'ru': ('Сравнение вымышленного Дерри с Бангором: канал, ручей Кендускиг, '
                   'водонапорная башня на Томас-Хилл, библиотека и другие реальные истоки '
                   'романа «Оно».'),
        },
        'breadcrumb': {'en': 'How Bangor inspired Derry', 'ru': 'Как Бангор вдохновил Дерри'},
        'url_name': 'derry_bangor',
        'eyebrow': {'en': 'The real city and the literary geography',
                    'ru': 'Реальный город и литературная география'},
        'heading': {'en': 'How Bangor inspired Derry, Maine',
                    'ru': 'Как Бангор вдохновил Дерри, штат Мэн'},
        'answer_label': {'en': 'The central point', 'ru': 'Главный вывод'},
        'toc': {
            'en': (('king', 'What King has said'), ('compare', 'Derry vs Bangor'),
                   ('canal', 'The canal and the stream'), ('standpipe', 'The Standpipe'),
                   ('library', 'The library'), ('atlas', 'How this informs the atlas'),
                   ('sources', 'Sources')),
            'ru': (('king', 'Что говорил Кинг'), ('compare', 'Дерри и Бангор'),
                   ('canal', 'Канал и ручей'), ('standpipe', 'Водонапорная башня'),
                   ('library', 'Библиотека'), ('atlas', 'Как это используется в атласе'),
                   ('sources', 'Источники')),
        },
        'topics': {
            'en': ('What King has said', 'Derry vs Bangor, side by side',
                   'The canal and the Standpipe', 'The library'),
            'ru': ('Что говорил Кинг', 'Дерри и Бангор бок о бок',
                   'Канал и водонапорная башня', 'Библиотека'),
        },
    },
    'books': {
        'template': 'atlas/derry_books.html',
        'title': {
            'en': 'Stephen King Books Set in Derry, Maine — A Spoiler-Light Guide',
            'ru': 'Книги Стивена Кинга о Дерри, штат Мэн — гид без спойлеров',
        },
        'description': {
            'en': ('A spoiler-light guide to Stephen King books set in or connected to Derry, '
                   'Maine, from IT and Insomnia to 11/22/63 and Dreamcatcher.'),
            'ru': ('Гид без крупных спойлеров по книгам Стивена Кинга, действие которых '
                   'происходит в Дерри или связано с ним: от «Оно» до «Бессонницы» и «11/22/63».'),
        },
        'breadcrumb': {'en': 'Books set in Derry', 'ru': 'Книги о Дерри'},
        'url_name': 'derry_books',
        'eyebrow': {'en': 'A spoiler-light reading path',
                    'ru': 'Маршрут чтения без крупных спойлеров'},
        'heading': {'en': 'Stephen King books set in Derry, Maine',
                    'ru': 'Книги Стивена Кинга о Дерри, штат Мэн'},
        'answer_label': {'en': 'Where to begin', 'ru': 'С чего начать'},
        'toc': {
            'en': (('setting', 'Derry as the setting'), ('return', 'Books that return'),
                   ('distant', 'More distant connections'), ('order', 'Reading order'),
                   ('sources', 'Sources')),
            'ru': (('setting', 'Дерри как место действия'),
                   ('return', 'Книги, которые возвращаются в Дерри'),
                   ('distant', 'Более далёкие связи'), ('order', 'Порядок чтения'),
                   ('sources', 'Источники')),
        },
        'topics': {
            'en': ('Seven books and stories', 'Where Derry is the setting', 'A reading order'),
            'ru': ('Семь книг и рассказов', 'Где Дерри — место действия', 'Порядок чтения'),
        },
    },
    'printable': {
        'template': 'atlas/printable_map.html',
        'title': {
            'en': 'Printable Map of Derry, Maine — Free PDF & SVG Download',
            'ru': 'Карта Дерри для печати — скачать PDF и SVG',
        },
        'description': {
            'en': ('Download a free printable map of Derry, Maine reconstructed from Stephen '
                   'King’s IT. Four A2 sheets are available as a PDF atlas and individual SVG files.'),
            'ru': ('Скачайте карту Дерри, штат Мэн, реконструированную по роману Стивена Кинга '
                   '«Оно»: четыре листа A2 в PDF и отдельные файлы SVG.'),
        },
        'breadcrumb': {'en': 'Printable map', 'ru': 'Карта для печати'},
    },
}


# Статьи в редакционном порядке: /articles/ и «Keep reading» идут по нему.
ARTICLES = ('real', 'bangor', 'books')
ARTICLES_PAGE = {
    'title': {'en': 'Articles about Derry, Maine · Derry atlas',
              'ru': 'Статьи о Дерри, штат Мэн · Атлас Дерри'},
    'description': {
        'en': ('Guides to Stephen King’s Derry: is the town real, how Bangor inspired it, '
               'and which books return to it.'),
        'ru': ('Путеводитель по Дерри Стивена Кинга: существует ли город, как его вдохновил '
               'Бангор и в каких книгах он появляется.'),
    },
}


def _places_count():
    """Все места атласа (на карте и без точки) — для карточки «Open the map»."""
    return Feature.objects.filter(object_type__in=('site', 'unplaced')).count()


def _hub_page(request, key):
    """Render a static editorial hub in either complete editorial language version."""
    config = HUB_PAGES[key]
    language = 'ru' if _is_ru() else 'en'
    page_title = config['title'][language]
    meta_description = config['description'][language]
    breadcrumb = config['breadcrumb'][language]
    is_article = key in ARTICLES
    context = {
        'page_title': page_title,
        'meta_description': meta_description,
        'breadcrumb': breadcrumb,
        'published_time': HUB_LASTMOD.isoformat(),
        'current_hub': key,
    }
    if is_article:
        context.update({
            'eyebrow': config['eyebrow'][language],
            'heading': config['heading'][language],
            'answer_label': config['answer_label'][language],
            'toc': [{'id': anchor, 'label': label} for anchor, label in config['toc'][language]],
            'places_count': _places_count(),
        })
    context['jsonld'] = schema.editorial(
        request, page_title, meta_description, breadcrumb, HUB_LASTMOD, in_articles=is_article)
    response = render(request, config['template'], context)
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def articles(request):
    """/articles/: список статей в редакционном порядке. В навигации его нет,
    сюда ведут крошки статей и sitemap."""
    language = 'ru' if _is_ru() else 'en'
    page_title = ARTICLES_PAGE['title'][language]
    meta_description = ARTICLES_PAGE['description'][language]
    items = [{'url': reverse(HUB_PAGES[key]['url_name']),
              'eyebrow': HUB_PAGES[key]['eyebrow'][language],
              'heading': HUB_PAGES[key]['heading'][language],
              'topics': HUB_PAGES[key]['topics'][language]} for key in ARTICLES]
    response = render(request, 'atlas/articles.html', {
        'page_title': page_title, 'meta_description': meta_description,
        'articles': items, 'places_count': _places_count(),
        'jsonld': schema.articles(request, page_title, meta_description, items)})
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def derry_real(request):
    return _hub_page(request, 'real')


@require_safe
def derry_bangor(request):
    return _hub_page(request, 'bangor')


@require_safe
def derry_books(request):
    return _hub_page(request, 'books')


@require_safe
def printable_map(request):
    return _hub_page(request, 'printable')


def _ru_plural(number, one, few, many):
    """Russian noun form for editorial strings kept outside the gettext catalogue."""
    if number % 10 == 1 and number % 100 != 11:
        return one
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return few
    return many


@require_safe
def index(request):
    features = list(Feature.objects.filter(object_type__in=('site', 'unplaced')).only(
        'key', 'object_type', 'name', 'kind', 'period'))
    mapped_count = sum(feature.object_type == 'site' for feature in features)
    unlocated_count = len(features) - mapped_count

    # The same editorial order is used by the map filters. Unknown future kinds
    # are kept rather than silently disappearing from the server-rendered index.
    kind_order = ('Homes', 'Civic', 'Barrens', 'Encounters', 'Historical', 'Outlying')
    buckets = {kind: [] for kind in kind_order}
    buckets['Unlocated'] = []
    for feature in features:
        kind = 'Unlocated' if feature.object_type == 'unplaced' else feature.kind
        buckets.setdefault(kind or 'Other', []).append(feature)

    labels = {
        'Homes': _('Homes'), 'Civic': _('Civic'), 'Barrens': _('Barrens'),
        'Encounters': _('Encounters'), 'Historical': _('Historical'),
        'Outlying': _('Outlying'), 'Unlocated': _('Unlocated'), 'Other': _('Other'),
    }

    def feature_sort(feature):
        return (0, int(feature.key)) if feature.key.isdigit() else (1, feature.key)

    ordered_kinds = [kind for kind in kind_order if buckets[kind]]
    ordered_kinds += sorted(kind for kind in buckets
                            if kind not in (*kind_order, 'Unlocated') and buckets[kind])
    if buckets['Unlocated']:
        ordered_kinds.append('Unlocated')
    place_groups = []
    for kind in ordered_kinds:
        items = []
        for feature in sorted(buckets[kind], key=feature_sort):
            items.append({
                'feature': feature,
                'name': feature_name(feature),
                'number': f'{int(feature.key):02d}' if feature.key.isdigit() else feature.key.upper(),
                'url': reverse('place', args=[place_slug(feature)]),
            })
        place_groups.append({
            'slug': slugify(kind), 'title': labels.get(kind, kind), 'items': items,
        })

    place_count = len(features)
    directory_jump = ngettext(
        'Browse all %(count)s place', 'Browse all %(count)s places', place_count
    ) % {'count': place_count}
    directory_stats = _('%(mapped)s mapped · %(unlocated)s unlocated') % {
        'mapped': mapped_count, 'unlocated': unlocated_count}
    page_title = _('Map of Derry, Maine — Stephen King’s IT Literary Atlas')
    if _is_ru():
        mapped_noun = _ru_plural(mapped_count, 'место', 'места', 'мест')
        meta_description = (
            'Исследуйте интерактивную карту вымышленного города Дерри, штат Мэн, из романа '
            f'Стивена Кинга «Оно»: {mapped_count} {mapped_noun} на карте, книжные '
            'свидетельства и фотографии.')
    else:
        meta_description = ngettext(
            'Explore an interactive map of Derry, Maine, the fictional town in Stephen King’s IT, '
            'with %(count)s mapped place, book evidence and photographs.',
            'Explore an interactive map of Derry, Maine, the fictional town in Stephen King’s IT, '
            'with %(count)s mapped places, book evidence and photographs.',
            mapped_count) % {'count': mapped_count}
    context = {
        'page_title': page_title, 'meta_description': meta_description,
        'mapped_count': mapped_count, 'unlocated_count': unlocated_count,
        'place_count': place_count, 'place_groups': place_groups,
        'directory_jump': directory_jump, 'directory_stats': directory_stats,
    }
    context['jsonld'] = schema.index(request, page_title, meta_description)
    response = render(request, 'atlas/index.html', context)
    response['Cache-Control'] = 'no-cache'
    return response


# Русские тексты живут рядом с каноническими английскими: у Feature и Source —
# в metadata['ru'] (валидация датасета сознательно не заглядывает в metadata),
# у Photo — в версионном SHA-реестре с fallback на caption_ru и caption.

def _is_ru():
    return get_language() == 'ru'


def _feature_ru(feature):
    ru = (feature.metadata or {}).get('ru') if isinstance(feature.metadata, dict) else None
    return ru if isinstance(ru, dict) else {}


def _feature_note(feature):
    return (_feature_ru(feature).get('note') or feature.note) if _is_ru() else feature.note


def _feature_place_content(feature):
    """Long-form place copy, with the same per-field RU fallback as notes."""
    ru = _feature_ru(feature) if _is_ru() else {}
    return {
        'about': ru.get('about') or feature.about,
        'confidence_explanation': (
            ru.get('confidence_explanation') or feature.confidence_explanation),
    }


def _caption(photo, ru=None):
    return photo_caption(photo, _is_ru() if ru is None else ru)


def _photo_alt(photo, feature=None):
    """Human-readable image fallback; original upload names are not alt text."""
    caption = _caption(photo)
    if caption:
        return caption
    place = feature_name(feature) if feature else 'Derry'
    return f'Фотография: {place}' if _is_ru() else f'{place} photograph'


def _fitted_dimensions(width, height, max_side):
    longest = max(width, height)
    if longest <= max_side:
        return width, height
    return max(1, round(width * max_side / longest)), max(1, round(height * max_side / longest))


def _scene_modified():
    """Timestamp of the database revision currently powering the map."""
    state = MapState.objects.select_related('revision').filter(pk=1).first()
    return state.revision.created if state and state.revision else None


def _feature_published(feature_key, fallback=None):
    """First atlas revision whose resulting snapshot contains the place."""
    for revision in Revision.objects.order_by('created', 'id').only('created', 'after'):
        tables = revision.after.get('tables', {}) if isinstance(revision.after, dict) else {}
        if any(row.get('key') == feature_key for row in tables.get('feature', [])):
            return revision.created
    return fallback


@require_safe
def map_data(request):
    state = MapState.objects.select_related('revision').only('initialized','revision_id','revision__digest','revision__id').get(pk=1)
    if not state.initialized:
        return JsonResponse({'error':'Atlas is not initialized.'}, status=503)
    # API живёт вне языкового префикса; язык приходит явным параметром ?lang=ru
    # и попадает в ETag, чтобы версии не перепутались в кеше браузера.
    ru = request.GET.get('lang') == 'ru'
    suffix = f'-ru-v{RU_MAP_PAYLOAD_VERSION}' if ru else ''
    etag = f'"{state.revision.digest}-r{state.revision_id}-v{RENDER_VERSION}{suffix}"'
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponseNotModified()
    else:
        payload, key = current_payload()
        payload = _presented_payload(payload, ru)
        etag = '"'+key+suffix+'"'
        response = JsonResponse(payload, json_dumps_params={'ensure_ascii':False,'separators':(',',':')})
    response['ETag'] = etag
    response['Cache-Control'] = 'no-cache'
    return response


def _presented_payload(payload, ru):
    """Payload карты для показа. Канонические данные английские; здесь
    ссылки на роман становятся подписями глав (`refs`, позиции в тексте
    отброшены), у периодов — короткое тире. На RU поверх идут имена, подписи,
    заметки и переводы периодов и глав; на EN — русские имена как алиасы поиска."""
    if ru:
        payload = localize_map_payload(payload)
        meta = {f.key: data for f in Feature.objects.exclude(metadata={})
                if (data := _feature_ru(f))}
    for group in ('sites', 'unplaced'):
        for s in payload['data'][group]:
            s['refs'] = novel_references([src['reference'] for src in s.pop('sources', [])], ru)
            s.pop('reference', None)
            s['period'] = period_label(s.get('period', ''), ru)
            if ru:
                if note := meta.get(str(s['id']), {}).get('note'):
                    s['note'] = note
            else:
                s['search_aliases'] = russian_search_terms(s['id'])
    return payload


def _media_urls(photo):
    return {k: settings.MEDIA_URL + v for k, v in relative_paths(photo.sha256, photo.ext).items()}


def _card_image(photo):
    """Responsive sources for a gallery card without inventing file widths.

    Derivatives preserve the original aspect ratio and are never enlarged, so
    portrait images and small originals can be narrower than the configured
    maximum side. Width descriptors must contain that real intrinsic width or
    the browser may choose an undersized source on high-density screens.
    """
    urls = _media_urls(photo)
    srcset = _fitted_srcset(photo.width, photo.height,
                            [(urls['thumb'], THUMB_SIZE), (urls['medium'], MEDIUM_SIZE)])
    return {'thumb': urls['thumb'], 'medium': urls['medium'], 'srcset': srcset}


def _grid_image(photo):
    """Колонка галереи: производные по ширине (480 и 960), без увеличения малых снимков."""
    urls = _media_urls(photo)
    widths = []
    for width in GRID_WIDTHS:
        fitted = min(width, photo.width)
        if fitted not in [w for _, w in widths]:
            widths.append((urls[f'w{width}'], fitted))
    return {'src': widths[0][0], 'srcset': ', '.join(f'{url} {w}w' for url, w in widths)}


def _fitted_srcset(width, height, sources):
    """srcset из пар (url, max_side производного) с реальными intrinsic-ширинами."""
    longest = max(width, height)
    unique = []
    for url, max_side in sources:
        fitted = width if longest <= max_side else max(1, round(width * max_side / longest))
        # Very small originals produce identical derivative widths. Keep the
        # srcset valid by listing each width only once.
        if all(existing_width != fitted for _, existing_width in unique):
            unique.append((url, fitted))
    return ', '.join(f'{url} {w}w' for url, w in unique)


def _cover_context(cover):
    """Данные заглавного фото для шаблона места; alt локализуется как caption."""
    urls = {k: settings.MEDIA_URL + v for k, v in cover_relative_paths(cover.sha256, cover.ext).items()}
    return {'year': cover.year, 'src': urls['medium'], 'large': urls['large'],
            'srcset': _fitted_srcset(cover.width, cover.height,
                                     [(urls['medium'], COVER_MEDIUM_SIZE), (urls['large'], COVER_LARGE_SIZE)]),
            'alt': (cover.alt_ru or cover.alt) if _is_ru() else cover.alt,
            'width': cover.width, 'height': cover.height}


def _photo_anchor(shape):
    """Точка для миниатюры на карте: у точечных фигур — сама точка, у линий
    и контуров — средняя вершина (полароид стоит на середине дороги, а не на конце)."""
    if 'points' in shape:
        return shape['points'][len(shape['points']) // 2]
    return [shape['x'], shape['y']]


@require_safe
def photo_data(request):
    """Фото для карты: превью в карточках мест и слой миниатюр.

    Отдаётся отдельно от /api/v1/map/: payload карты кешируется по ревизии
    атласа, а фото — контур вне ревизий, их правки ревизий не создают.
    """
    ru = request.GET.get('lang') == 'ru'
    grouped = {}
    for p in Photo.objects.exclude(feature_key='').order_by('order', 'id'):
        grouped.setdefault(p.feature_key, []).append(p)
    features = Feature.objects.select_related('geometry').in_bulk(grouped)
    result = {}
    for key, group in grouped.items():
        feature = features.get(key)
        if feature is None:  # привязка не пережила правку атласа; чинится через `photos check`
            continue
        entry = {'name': feature_name(feature, russian=ru), 'object_type': feature.object_type,
                 'photos': [{'id': p.id, 'thumb': _media_urls(p)['thumb'],
                             'caption': _caption(p, ru), 'year': p.year} for p in group]}
        if feature.geometry_id:
            entry['anchor'] = _photo_anchor(feature.geometry.shape)
        # Прямой адрес лендинга места: ссылка с карты без промежуточного 301.
        gallery = _gallery_url(place=key, place_feature=feature)
        entry['gallery'] = translate_url(gallery, 'ru') if ru else gallery
        result[key] = entry
    response = JsonResponse({'features': result},
                            json_dumps_params={'ensure_ascii': False, 'separators': (',', ':')})
    response['Cache-Control'] = 'no-cache'
    return response


def gallery_place_slug(feature):
    """Readable photo-landing slug for every Feature type, including roads."""
    return slugify(f'{feature.key}-{feature.name}')


# Сочетания фильтров галереи — бесконечное пространство адресов для краулеров
# (инцидент 17.10.2026): не больше двух значений сразу.
MAX_GALLERY_FILTERS = 2
# Группы фильтра галереи в порядке панели (D23) и порядок параметров в адресе.
GALLERY_GROUPS = ('character', 'place', 'year', 'tag')
GALLERY_QUERY = ('place', 'character', 'tag', 'year')
GALLERY_PLACES_SHOWN = 5


def _selection_url(selection, features=None):
    """Адрес отбора {группа: [значения]}: одно значение — индексируемый лендинг,
    сочетание — query на /photos/. Значения внутри группы отсортированы, поэтому
    у сочетания ровно один адрес."""
    values = [(group, value) for group in GALLERY_QUERY for value in selection.get(group, ())]
    if len(values) == 1:
        group, value = values[0]
        if group == 'place':
            feature = (features or {}).get(value) or Feature.objects.filter(pk=value).first()
            if feature:
                return reverse('gallery_place', args=[gallery_place_slug(feature)])
        elif group == 'character':
            return reverse('gallery_character', args=[value])
        elif group == 'tag':
            return reverse('gallery_tag', args=[value])
        elif str(value).isdigit():
            return reverse('gallery_year', args=[value])
    query = urlencode([(group, ','.join(sorted(selection[group])))
                       for group in GALLERY_QUERY if selection.get(group)], safe=',:')
    return reverse('gallery') + ('?' + query if query else '')


def _gallery_url(place='', character='', tags=(), year='', place_feature=None):
    """Адрес галереи для отдельных значений (страницы фото, места, карта)."""
    selection = {'place': [place] if place else [], 'character': [character] if character else [],
                 'tag': list(tags), 'year': [str(year)] if year else []}
    return _selection_url(selection, {place: place_feature} if place_feature else None)


def _place_sort_key(feature):
    """Stable atlas order: numbered sites first, then named unlocated entries."""
    return (0, int(feature.key)) if feature.key.isdigit() else (1, feature.key.casefold())


def _place_number(feature):
    return f'{int(feature.key):02d}' if feature.key.isdigit() else feature.key.upper()


def _chapter_keys(reference):
    """Главы одной ссылки Evidence без раздела (§), чтобы места связывались
    по главе. Позиции в тексте вида ``[1771]`` главами не считаются."""
    return list(dict.fromkeys(key for key, section in parse_reference(reference)))


def _reference_key(reference):
    return ' '.join(reference.split()).casefold()


def _related_place_card(feature, chapter=None):
    """Карточка связанного места: кадр локатора, номер, имя, «Категория · Гл. N»."""
    return {
        'feature': feature,
        'name': feature_name(feature),
        'number': _place_number(feature),
        'url': reverse('place', args=[place_slug(feature)]),
        # У мест без точки категории нет: вместо неё — уровень «No location».
        'kind': kind_label(feature.kind, short=True) if feature.kind else CONFIDENCE_LABELS['U'],
        'kind_class': feature.kind.lower() if feature.kind else '',
        'letter': feature.confidence or 'U',
        'chapter_key': chapter,
        'chapter': chapter_short(chapter) if chapter is not None else '',
    }


def _related_places(feature, current_evidence, limit=4):
    """Build geographical and textual links for a place page.

    Distances rank reconstructed map points but are deliberately not exposed:
    they are navigation hints, not claims about surveyed real-world geography.
    Textual candidates favour the same exact section, then the greatest number
    of shared chapters. A place already shown as nearby is not repeated in the
    second panel; its shared chapter is attached to the nearby card instead.
    """
    nearby = []
    if feature.object_type == 'site' and feature.geometry_id:
        shape = feature.geometry.shape
        if shape.get('type') == 'point':
            x, y = shape.get('x'), shape.get('y')
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                distances = []
                candidates = (Feature.objects.filter(object_type='site')
                              .exclude(pk=feature.pk).select_related('geometry'))
                for candidate in candidates:
                    candidate_shape = candidate.geometry.shape
                    if candidate_shape.get('type') != 'point':
                        continue
                    cx, cy = candidate_shape.get('x'), candidate_shape.get('y')
                    if not isinstance(cx, (int, float)) or not isinstance(cy, (int, float)):
                        continue
                    distances.append(((cx - x) ** 2 + (cy - y) ** 2, candidate))
                distances.sort(key=lambda item: (item[0], _place_sort_key(item[1])))
                nearby = [_related_place_card(candidate) for _, candidate in distances[:limit]]

    current_exact = {_reference_key(e.reference) for e in current_evidence}
    current_chapters = {}
    reference_chapters = {}
    for evidence in current_evidence:
        keys = _chapter_keys(evidence.reference)
        for key in keys:
            current_chapters.setdefault(key, key)
        if keys:
            reference_chapters[_reference_key(evidence.reference)] = keys[0]

    semantic = {}
    if current_chapters:
        evidence_rows = (Evidence.objects.filter(
            feature__object_type__in=('site', 'unplaced')).exclude(feature=feature)
            .select_related('feature').order_by('feature_id', 'order', 'key'))
        for evidence in evidence_rows:
            keys = [key for key in _chapter_keys(evidence.reference) if key in current_chapters]
            if not keys:
                continue
            entry = semantic.setdefault(evidence.feature_id, {
                'feature': evidence.feature, 'references': set(), 'chapters': set(),
            })
            entry['references'].add(_reference_key(evidence.reference))
            entry['chapters'].update(keys)

    def primary_chapter(entry):
        exact = current_exact & entry['references']
        for reference in current_evidence:
            reference_key = _reference_key(reference.reference)
            chapter_key = reference_chapters.get(reference_key)
            if reference_key in exact and chapter_key in entry['chapters']:
                return current_chapters[chapter_key]
        return next(current_chapters[key] for key in current_chapters
                    if key in entry['chapters'])

    nearby_keys = {card['feature'].key for card in nearby}
    for card in nearby:
        entry = semantic.get(card['feature'].key)
        if entry:
            card['chapter_key'] = primary_chapter(entry)
            card['chapter'] = chapter_short(card['chapter_key'])

    candidates = [entry for key, entry in semantic.items() if key not in nearby_keys]
    candidates.sort(key=lambda entry: (
        -len(current_exact & entry['references']),
        -len(entry['chapters']),
        entry['feature'].rank,
        _place_sort_key(entry['feature']),
    ))
    same_chapters = [
        _related_place_card(entry['feature'], primary_chapter(entry))
        for entry in candidates[:limit]
    ]
    return nearby, same_chapters


# Порядок категорий в фильтре указателя и на карте.
KIND_ORDER = ('Homes', 'Civic', 'Barrens', 'Encounters', 'Historical', 'Outlying')
# Пробелы в данных для режима владельца (?audit=1): ключ фильтра → подпись.
AUDIT_CHECKS = (
    ('photos', _('Photos')), ('cover', _('Cover')), ('content', _('Descriptions')),
    ('ru', _('Russian text')), ('one-source', _('One source only')),
)
AUDIT_TILE_NOTES = {
    'photos': _('no photos'), 'cover': _('no cover'),
    'content': _('text incomplete'), 'ru': _('RU incomplete'), 'one-source': _('one source'),
}


def _plural_forms(singular, plural, counter='%(n)s'):
    """Формы ngettext для JS: [одна, несколько, много] (RU) или [одна, много, много] (EN).
    Числа подставляет браузер: %(n)s, а счётчик формы — вместо `counter`."""
    return [ngettext(singular, plural, n) % {'counter': counter, 'n': '%(n)s', 'total': '%(total)s'}
            for n in (1, 2, 5)]


def _places_js_strings():
    """Строки places.js: статус, пустое состояние, чипы, кнопки шторки."""
    return {
        'places': _plural_forms('%(counter)s place', '%(counter)s places'),
        'of_total': _plural_forms('%(n)s of %(counter)s place', '%(n)s of %(counter)s places',
                                  counter='%(total)s'),
        'show': _plural_forms('Show %(counter)s place', 'Show %(counter)s places'),
        'empty_in_kind': str(_('Nothing for “%(q)s” in %(kind)s. Search looks in names, '
                               'descriptions and map numbers.')),
        'empty_query': str(_('Nothing for “%(q)s”. Search looks in names, descriptions and '
                             'map numbers.')),
        'filters': str(_('Filters')), 'filters_n': str(_('Filters, %(n)s')),
        'remove': str(_('Remove filter: %(name)s')),
        'close_icon': render_to_string('atlas/icons/close.svg').strip(),
    }


def _places_sort_options():
    return [('number', _('Map number')), ('name', _('Name A–Z')),
            ('confidence', pgettext('sort', 'Confidence'))]


@require_safe
def places(request):
    """Указатель мест (блок 06): все плитки в HTML в порядке номеров; поиск, фасеты,
    сортировка и вид — в places.js. ?audit=1 — режим владельца (noindex)."""
    # ?audit=1; старые ссылки владельца ?audit=photos|cover|content|ru|sources тоже (places.js
    # переводит их в ?audit=1&missing=…).
    audit = request.GET.get('audit') in ('1', 'photos', 'cover', 'content', 'ru', 'sources')
    features = list(
        Feature.objects.filter(object_type__in=('site', 'unplaced'))
        .annotate(evidence_count=Count('evidence'))
    )
    features.sort(key=_place_sort_key)

    photos_by_feature = {}
    for photo in Photo.objects.exclude(feature_key='').order_by('order', 'id'):
        photos_by_feature.setdefault(photo.feature_key, []).append(photo)
    covers_by_feature = {}
    for cover in PlaceCover.objects.order_by('feature_key', 'year'):
        covers_by_feature.setdefault(cover.feature_key, []).append(cover)

    cards = []
    kinds = Counter()
    sure_counts = Counter()
    media_counts = Counter()
    audit_counts = Counter()
    mapped_count = 0
    for order, feature in enumerate(features):
        mapped = feature.object_type == 'site'
        mapped_count += int(mapped)
        letter = feature.confidence or 'U'
        sure_counts[letter] += 1
        if feature.kind:
            kinds[feature.kind] += 1
        feature_photos = photos_by_feature.get(feature.key, [])
        feature_covers = covers_by_feature.get(feature.key, [])
        localized = _feature_place_content(feature)
        display_name = feature_name(feature)
        note = _feature_note(feature)
        ru = _feature_ru(feature)

        # Картинка плитки: обложка (1958, иначе самый ранний год) → первое фото → кадр карты.
        image = None
        if feature_covers:
            cover = next((c for c in feature_covers if c.year == 1958), feature_covers[0])
            context = _cover_context(cover)
            image = {'src': context['src'], 'srcset': context['srcset'], 'thumb': context['src'],
                     'width': context['width'], 'height': context['height']}
        elif feature_photos:
            photo = feature_photos[0]
            photo_image = _card_image(photo)
            image = {'src': photo_image['medium'], 'srcset': photo_image['srcset'],
                     'thumb': photo_image['thumb'], 'width': photo.width, 'height': photo.height}

        media = [name for name, present in (('photos', feature_photos), ('cover', feature_covers))
                 if present]
        media_counts.update(media)
        missing = [key for key, gap in (
            ('photos', not feature_photos), ('cover', not feature_covers),
            ('content', not (feature.note and feature.about and feature.confidence_explanation)),
            ('ru', not all(ru.get(field) for field in ('note', 'about', 'confidence_explanation'))),
            ('one-source', feature.evidence_count <= 1),  # 0 тоже: старый фильтр «Sources»
        ) if gap]
        audit_counts.update(missing)

        # Поиск широкий (D19): номер, имена EN/RU и алиасы, категория, период, все тексты.
        search_text = ' '.join(filter(None, (
            feature.key, *feature_search_terms(feature), feature.kind, feature.period,
            period_label(feature.period), str(kind_label(feature.kind)) if feature.kind else '',
            note, localized['about'], localized['confidence_explanation'],
        )))
        cards.append({
            'feature': feature, 'name': display_name, 'number': _place_number(feature),
            'url': reverse('place', args=[place_slug(feature)]),
            'mapped': mapped, 'note': note, 'image': image,
            'sure': letter.lower(), 'conf_meta': CONFIDENCE_META[letter],
            'kind_value': feature.kind.lower() if feature.kind else '',
            'kind_label': kind_label(feature.kind, short=True) if feature.kind else '',
            'period': period_label(feature.period),
            'media': media, 'missing': missing,
            'missing_labels': [AUDIT_TILE_NOTES[key] for key in missing],
            'search_text': search_text, 'order': order,
        })

    place_count = len(cards)
    unlocated_count = place_count - mapped_count
    kind_names = [kind for kind in KIND_ORDER if kinds[kind]]
    kind_names += sorted(kind for kind in kinds if kind not in KIND_ORDER)
    page_title = _('Places in Derry, Maine — Stephen King’s IT Literary Atlas')
    if _is_ru():
        place_noun = _ru_plural(place_count, 'место и ориентир', 'места и ориентира',
                                'мест и ориентиров')
        meta_description = (
            f'Просматривайте {place_count} {place_noun} вымышленного Дерри, штат Мэн, '
            'реконструированных по роману Стивена Кинга «Оно», с книжными свидетельствами, '
            'заметками о расположении и фотографиями.')
    else:
        meta_description = ngettext(
            'Browse %(count)s place and landmark in fictional Derry, Maine, reconstructed from '
            'Stephen King’s IT, with book evidence, location notes and photographs.',
            'Browse %(count)s places and landmarks in fictional Derry, Maine, reconstructed from '
            'Stephen King’s IT, with book evidence, location notes and photographs.',
            place_count) % {'count': place_count}
    context = {
        'cards': cards, 'audit': audit,
        'levels': [{'letter': level, 'label': CONFIDENCE_LABELS[level],
                    'count': sure_counts[level]} for level in 'ABCU'],
        'kinds': [{'value': kind.lower(), 'label': kind_label(kind), 'count': kinds[kind]}
                  for kind in kind_names],
        'media_counts': media_counts,
        'audit_counts': [{'key': key, 'label': label, 'count': audit_counts[key]}
                         for key, label in AUDIT_CHECKS],
        'sort_options': _places_sort_options(),
        'js_strings': _places_js_strings(),
        'place_count': place_count, 'mapped_count': mapped_count,
        'unlocated_count': unlocated_count,
        'page_title': page_title, 'meta_description': meta_description,
        # Режим владельца не индексируется (решение 23.10, D49).
        'robots_meta': 'noindex, nofollow' if audit else '',
    }
    context['jsonld'] = schema.places(request, page_title, meta_description, cards)
    response = render(request, 'atlas/places.html', context)
    response['Cache-Control'] = 'no-cache'
    if audit:
        response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


GALLERY_PAGE = 24  # «Show 24 more» (D25)


def _gallery_js_strings():
    """Строки gallery.js: статус, «Show more», кнопка шторки, чипы."""
    return {
        'photos': _plural_forms('%(n)s photograph', '%(n)s photographs', counter='%(n)s'),
        'of_total': _plural_forms('%(n)s of %(total)s photograph', '%(n)s of %(total)s photographs',
                                  counter='%(total)s'),
        'show': _plural_forms('Show %(counter)s photograph', 'Show %(counter)s photographs'),
        'more': str(_('Show %(n)s more')), 'shown': str(_('%(n)s of %(total)s')),
        'filters': str(_('Filters')), 'filters_n': str(_('Filters, %(n)s')),
        'remove': str(_('Remove filter: %(name)s')), 'heading': str(_('Photographs')),
        'close_icon': render_to_string('atlas/icons/close.svg').strip(),
        'page': GALLERY_PAGE,
    }


FACE_PX = 22


def _character_face(character):
    """Портрет персонажа в кружке 22 px: фон из снимка `avatar`, точка лица — в центре
    кружка. Без аватара — None (шаблон рисует букву)."""
    photo = character.avatar
    if photo is None:
        return None
    ratio = photo.height / photo.width
    zoom = max(character.avatar_zoom, 1, 1 / ratio)  # снимок закрывает кружок целиком

    def position(focal, scale):
        return 0.5 if scale <= 1 else min(1, max(0, (focal * scale - 0.5) / (scale - 1)))

    urls = _media_urls(photo)
    thumb_width, _ = _fitted_dimensions(photo.width, photo.height, THUMB_SIZE)
    # Кружку хватает плотности 1×: тяжёлый medium — только если превью совсем мало.
    src = urls['thumb'] if thumb_width >= FACE_PX * zoom else urls['medium']
    return (f'background-image:url({src});background-size:{zoom * 100:.0f}% auto;'
            f'background-position:{position(character.avatar_x, zoom) * 100:.1f}% '
            f'{position(character.avatar_y, zoom * ratio) * 100:.1f}%')


@require_safe
def gallery(request, filter_type='', filter_slug='', filter_year=None):
    """Галерея (блок 07) и индексируемые страницы одного фильтра.

    Внутри группы — ИЛИ, между группами — И (теги тоже ИЛИ, решение 23.10). Сервер
    принимает не больше двух значений (MAX_GALLERY_FILTERS): одно — лендинг со своим
    адресом, два — query-адрес под noindex. Ссылки панели ведут только на лендинги
    и /photos/, поэтому краулер не умножает адреса.
    """
    all_photos = list(Photo.objects.prefetch_related('characters', 'tags'))
    features = Feature.objects.in_bulk({p.feature_key for p in all_photos if p.feature_key})
    characters = {c.slug: c for c in Character.objects.filter(photo__isnull=False)
                  .select_related('avatar').distinct()}
    tags = {t.slug: t for t in Tag.objects.filter(photo__isnull=False).distinct()}
    items = [{
        'photo': p,
        'place': {p.feature_key} & features.keys(),
        'character': {c.slug for c in p.characters.all()},
        'tag': {t.slug for t in p.tags.all()},
        'year': {str(p.year)} if p.year else set(),
    } for p in all_photos]
    known = {group: set().union(*(item[group] for item in items)) for group in GALLERY_GROUPS}

    selection = {group: [] for group in GALLERY_GROUPS}
    landing = None
    if filter_type == 'place':
        feature = next((f for f in features.values() if gallery_place_slug(f) == filter_slug), None)
        if feature is None:
            raise Http404
        selection['place'] = [feature.key]
        landing = {'type': 'place', 'label': feature_name(feature), 'feature': feature}
    elif filter_type == 'character':
        if filter_slug not in characters:
            raise Http404
        selection['character'] = [filter_slug]
        landing = {'type': 'character', 'label': character_name(characters[filter_slug])}
    elif filter_type == 'tag':
        if filter_slug not in tags:
            raise Http404
        selection['tag'] = [filter_slug]
        landing = {'type': 'tag', 'label': tag_name(tags[filter_slug])}
    elif filter_type == 'year':
        if str(filter_year) not in known['year']:
            raise Http404
        selection['year'] = [str(filter_year)]
        landing = {'type': 'year', 'label': str(filter_year)}
    elif filter_type:
        raise Http404
    else:
        for group in GALLERY_GROUPS:
            for value in request.GET.get(group, '').split(','):
                if (value := value.strip()) and value not in selection[group]:
                    selection[group].append(value)
        # Неизвестные значения и больше MAX_GALLERY_FILTERS значений — 404 (инцидент
        # 17.10.2026). Посторонние параметры (utm_* и т. п.) на выдачу не влияют.
        count = sum(map(len, selection.values()))
        if count > MAX_GALLERY_FILTERS or any(
                value not in known[group] for group, values in selection.items() for value in values):
            raise Http404
        # Старые адреса одного фильтра навсегда сходятся на лендинг.
        if count == 1 and set(request.GET) <= set(GALLERY_GROUPS):
            return redirect(_selection_url(selection, features), permanent=True)
    selected = sum(map(len, selection.values()))

    def matches(item, skip=None):
        return all(not values or item[group] & set(values)
                   for group, values in selection.items() if group != skip)

    def option(group, value, label, **extra):
        """Пункт панели. Счётчик фасетный: сколько снимков даст этот пункт при прочих
        группах. Ссылка — на лендинг пункта, у отмеченного — отбор без него."""
        checked = value in selection[group]
        landing_url = _selection_url({group: [value]}, features)
        if checked:
            rest = {g: [v for v in values if (g, v) != (group, value)]
                    for g, values in selection.items()}
            url = _selection_url(rest, features)
        else:
            url = landing_url
        return {'group': group, 'value': value, 'label': label, 'checked': checked, 'url': url,
                'landing': landing_url,
                'count': sum(1 for item in items if value in item[group] and matches(item, group)),
                **extra}

    totals = {group: Counter(value for item in items for value in item[group])
              for group in GALLERY_GROUPS}
    place_options = [option('place', key, feature_name(features[key]))
                     for key in sorted(known['place'], key=lambda key: (
                         -totals['place'][key], feature_name(features[key]).casefold()))]
    groups = [
        {'name': 'character', 'title': _('Character'), 'options': sorted(
            (option('character', slug, character_name(c), face=_character_face(c),
                    initial=character_name(c)[:1])
             for slug, c in characters.items()), key=lambda o: o['label'].casefold())},
        {'name': 'place', 'title': _('Place'), 'options': place_options[:GALLERY_PLACES_SHOWN],
         'more': place_options[GALLERY_PLACES_SHOWN:], 'total': len(place_options),
         'more_open': any(o['checked'] for o in place_options[GALLERY_PLACES_SHOWN:])},
        {'name': 'year', 'title': _('Year'),
         'options': [option('year', year, year) for year in sorted(known['year'])]},
        {'name': 'tag', 'title': _('Tag'), 'options': sorted(
            (option('tag', slug, tag_name(t)) for slug, t in tags.items()),
            key=lambda o: o['label'].casefold())},
    ]
    labels = {(o['group'], o['value']): o for g in groups for o in g['options'] + g.get('more', [])}
    # Чипы выбранного — только у сочетаний; у лендинга фильтр снимается в панели.
    chips = [labels[(group, value)] for group in GALLERY_GROUPS for value in selection[group]
             ] if selected > 1 else []

    # В HTML — только подходящие фото (лендинг индексируется без чужих снимков);
    # gallery.js получает все фото в JSON и фильтрует дальше в браузере.
    cards, everything = [], []
    for item in items:
        photo = item['photo']
        feature = features.get(photo.feature_key)
        alt = _photo_alt(photo, feature)
        card = {
            'photo': photo, **_grid_image(photo), 'alt': alt, 'caption': _caption(photo) or alt,
            'meta': ' · '.join(filter(None, (str(photo.year or ''),
                                             feature_name(feature) if feature else ''))),
        }
        if matches(item):
            cards.append(card)
        everything.append({
            'id': photo.id, 'url': reverse('photo', args=[photo.id]), 'src': card['src'],
            'srcset': card['srcset'], 'w': photo.width, 'h': photo.height, 'alt': alt,
            'caption': card['caption'], 'meta': card['meta'],
            **{group: sorted(item[group]) for group in GALLERY_GROUPS},
        })
    total = len(items)
    if selected > 1:
        status = ngettext('%(n)s of %(total)s photograph', '%(n)s of %(total)s photographs',
                          total) % {'n': len(cards), 'total': total}
    else:
        status = ngettext('%(n)s photograph', '%(n)s photographs', len(cards)) % {'n': len(cards)}

    gallery_heading = _('Photographs')
    gallery_intro = ''
    place_links = None
    page_title = _('Photographs of Derry, Maine — Stephen King’s IT')
    meta_description = _(
        'Browse photographs of Derry, Maine places from a literary atlas of Stephen King’s IT, '
        'with filters by place, character, tag and year.')
    if landing:
        label = landing['label']
        if landing['type'] == 'place':
            gallery_heading = _('Photographs of %(name)s') % {'name': label}
            page_title = _('%(name)s photographs — Derry, Maine · Stephen King’s IT') % {
                'name': label}
            meta_description = _(
                'Browse photographs connected to %(name)s in this novel-based reconstruction '
                'of Derry, Maine.') % {'name': label}
            feature = landing['feature']
            # Страница места есть у точек и мест без координат; карта — только у точек.
            if feature.object_type in ('site', 'unplaced'):
                place_links = {'page': reverse('place', args=[place_slug(feature)]),
                               'map': (reverse('index') + '?place=' + feature.key
                                       if feature.object_type == 'site' else '')}
        elif landing['type'] == 'character':
            gallery_heading = _('%(name)s in Derry photographs') % {'name': label}
            page_title = _('%(name)s photographs — Derry, Maine · Stephen King’s IT') % {
                'name': label}
            meta_description = _(
                'Browse photographs featuring %(name)s in this literary atlas of '
                'Stephen King’s IT.') % {'name': label}
        elif landing['type'] == 'tag':
            gallery_heading = _('%(name)s photographs') % {'name': label}
            page_title = _('%(name)s photographs of Derry, Maine · Stephen King’s IT') % {
                'name': label}
            meta_description = _(
                'Browse Derry photographs grouped under the %(name)s theme in this literary '
                'atlas of Stephen King’s IT.') % {'name': label}
        else:
            gallery_heading = _('Derry photographs from %(year)s') % {'year': label}
            page_title = _('Derry photographs from %(year)s — Stephen King’s IT') % {
                'year': label}
            meta_description = _(
                'Browse photographs representing Derry in %(year)s in this literary atlas of '
                'Stephen King’s IT.') % {'year': label}
        # Одна строка под H1 у страниц одного фильтра (решение 23.10).
        gallery_intro = meta_description

    # Сочетания дублируют лендинги: не индексируются и ссылки не обходятся.
    robots_meta = 'noindex, nofollow' if selected > 1 else ''
    breadcrumb = landing['label'] if landing else ''
    gallery_state = {
        'photos': everything, 'selection': selection, 'base': reverse('gallery'),
        'landings': {f'{o["group"]}:{o["value"]}': o['landing'] for o in labels.values()},
        'strings': _gallery_js_strings(),
    }
    response = render(request, 'atlas/gallery.html', {
        'robots_meta': robots_meta, 'groups': groups, 'chips': chips, 'cards': cards,
        'gallery_state': gallery_state, 'total': total,
        'status': status, 'landing': landing, 'gallery_heading': gallery_heading,
        'gallery_breadcrumb': breadcrumb, 'gallery_intro': gallery_intro,
        'place_links': place_links, 'page_title': page_title,
        'meta_description': meta_description,
        'jsonld': schema.gallery(request, page_title, meta_description, breadcrumb),
    })
    response['Cache-Control'] = 'no-cache'
    if robots_meta:
        response['X-Robots-Tag'] = robots_meta
    return response


@require_safe
def photo_page(request, photo_id):
    photo = get_object_or_404(Photo.objects.prefetch_related('characters', 'tags'), pk=photo_id)
    feature = Feature.objects.filter(pk=photo.feature_key).first() if photo.feature_key else None
    # Карта выделяет точки и нелокализованные записи; у дорог и прочих
    # контуров маркера нет, поэтому ссылки на карту у таких фото нет.
    on_map = feature is not None and feature.object_type in ('site', 'unplaced')
    map_url = reverse('index') + '?place=' + feature.key if on_map else ''
    urls = _media_urls(photo)
    caption = _caption(photo)
    alt = _photo_alt(photo, feature)
    heading = caption or alt
    place_label = feature_name(feature) if feature else photo.feature_key or _('Derry')
    page_title = _('%(subject)s — Derry, Maine · Stephen King’s IT') % {'subject': heading}
    description_subject = heading if heading.endswith(('.', '!', '?')) else heading + '.'
    if photo.year:
        meta_description = _(
            '%(subject)s A photograph of %(place)s in the Derry, Maine literary atlas based on '
            'Stephen King’s IT, dated %(year)s.') % {
                'subject': description_subject, 'place': place_label, 'year': photo.year}
    else:
        meta_description = _(
            '%(subject)s A photograph of %(place)s in the Derry, Maine literary atlas based on '
            'Stephen King’s IT.') % {'subject': description_subject, 'place': place_label}
    og_width, og_height = _fitted_dimensions(photo.width, photo.height, MEDIUM_SIZE)
    context = {
        'photo': photo, 'urls': urls, 'caption': caption, 'alt': alt,
        'heading': heading, 'page_title': page_title, 'meta_description': meta_description,
        'srcset': _fitted_srcset(photo.width, photo.height,
                                 [(urls['medium'], MEDIUM_SIZE),
                                  (urls['original'], max(photo.width, photo.height))]),
        'og_image_width': og_width, 'og_image_height': og_height,
        'published_time': photo.created, 'modified_time': photo.modified,
        'place_page_url': reverse('place', args=[place_slug(feature)]) if on_map else '',
        'place_label': feature_name(feature) if feature else photo.feature_key,
        'place_gallery_url': (_gallery_url(place=photo.feature_key, place_feature=feature)
                              if photo.feature_key else ''),
        'map_url': map_url,
        'year_url': _gallery_url(year=str(photo.year)) if photo.year else '',
        'characters': [{'name': character_name(c), 'url': _gallery_url(character=c.slug)}
                       for c in photo.characters.order_by('name')],
        'tags': [{'slug': t.slug, 'name': tag_name(t),
                  'url': _gallery_url(tags=[t.slug])} for t in photo.tags.order_by('slug')]}
    context['jsonld'] = schema.photo(request, context)
    response = render(request, 'atlas/photo.html', context)
    response['Cache-Control'] = 'no-cache'
    return response


def place_slug(feature):
    """Слаг страницы места: ключ + английское название, `12-neibolt-street`.
    Не хранится в БД — собирается из текущего названия; устаревший слаг
    приводит к 301-редиректу на канонический."""
    name = slugify(feature.name)
    return feature.key.lower() + ('-' + name if name else '')


# Ключи, которые сменились при переводе места на карту; старые адреса ведут на новые.
# U5 Cycle Shoppe стал местом 84 по аудиту 27.09.
LEGACY_PLACE_KEYS = {'u5': '84'}


PLACE_PHOTOS_DESKTOP = 6
PLACE_PHOTOS_PHONE = 4


@require_safe
def place_page(request, slug):
    key = slug.split('-', 1)[0]
    key = LEGACY_PLACE_KEYS.get(key.lower(), key)
    feature = get_object_or_404(Feature, key__iexact=key, object_type__in=('site', 'unplaced'))
    canonical = place_slug(feature)
    if slug != canonical:
        return redirect(reverse('place', args=[canonical]), permanent=True)
    # «In the novel»: главы и интерлюдии подписями из таблицы глав, как в карточке на карте.
    evidence = list(Evidence.objects.filter(feature=feature).order_by('order', 'key'))
    refs = novel_reference_rows([e.reference for e in evidence])
    photos = Photo.objects.filter(feature_key=feature.key).order_by('order', 'id')
    # Обложки по годам; по умолчанию 1958, иначе самый ранний год (D12).
    covers = sorted((_cover_context(c) for c in PlaceCover.objects.filter(feature_key=feature.key)),
                    key=lambda c: c['year'])
    default_year = 1958 if any(c['year'] == 1958 for c in covers) else (
        covers[0]['year'] if covers else None)
    for cover in covers:
        cover['selected'] = cover['year'] == default_year
    latest_photo = photos.order_by('-modified').values_list('modified', flat=True).first()
    latest_cover = (PlaceCover.objects.filter(feature_key=feature.key)
                    .order_by('-modified').values_list('modified', flat=True).first())
    scene_modified = _scene_modified()
    modified_candidates = [value for value in (scene_modified, latest_photo, latest_cover) if value]
    modified_time = max(modified_candidates) if modified_candidates else None
    place_content = _feature_place_content(feature)
    nearby_places, same_chapter_places = _related_places(feature, evidence)
    display_name = feature_name(feature)
    page_title = _('%(name)s — Derry, Maine · Stephen King’s IT') % {'name': display_name}
    meta_description = _(
        'Explore %(name)s in Derry, Maine: its location, book evidence and mapping confidence '
        'in this literary atlas of Stephen King’s IT.') % {'name': display_name}
    cards = [{'photo': p, **_card_image(p), 'caption': _caption(p),
              'alt': _photo_alt(p, feature)} for p in photos]
    photo_total = len(cards)
    # До 6 фото на десктопе (при 7+ — пять и плитка «+N»), до 4 на телефоне (при 5+ — три и плитка).
    shown = cards[:PLACE_PHOTOS_DESKTOP if photo_total <= PLACE_PHOTOS_DESKTOP
                  else PLACE_PHOTOS_DESKTOP - 1]
    phone_limit = (PLACE_PHOTOS_PHONE if photo_total <= PLACE_PHOTOS_PHONE
                   else PLACE_PHOTOS_PHONE - 1)
    for index, card in enumerate(shown):
        card['phone_hidden'] = index >= phone_limit
    cover_og = next((c for c in covers if c['selected']), None)
    if cover_og:
        og_width, og_height = _fitted_dimensions(cover_og['width'], cover_og['height'],
                                                 COVER_LARGE_SIZE)
    elif cards:
        og_width, og_height = _fitted_dimensions(cards[0]['photo'].width, cards[0]['photo'].height,
                                                 MEDIUM_SIZE)
    else:
        og_width = og_height = None
    letter = feature.confidence or 'U'
    context = {
        'letter': letter,
        'feature': feature, 'feature_name': display_name, 'note': _feature_note(feature),
        'page_title': page_title, 'meta_description': meta_description,
        'confidence': confidence_label(feature.confidence) if feature.confidence else '',
        'confidence_label': CONFIDENCE_LABELS[letter],
        'confidence_line': CONFIDENCE_EXPLANATIONS[letter],
        'kind_class': feature.kind.lower() if feature.kind else '',
        'kind_short': kind_label(feature.kind, short=True) if feature.kind else '',
        'kind_full': kind_label(feature.kind) if feature.kind else '',
        'refs': refs, 'chapter_count': len({row['key'] for row in refs}),
        'period': period_label(feature.period),
        'place_about': place_content['about'],
        'confidence_explanation': place_content['confidence_explanation'],
        'nearby_places': nearby_places,
        'same_chapter_places': same_chapter_places,
        'same_chapter_heading': same_chapters_heading(
            [card['chapter_key'] for card in same_chapter_places]),
        'covers': covers, 'cards': shown, 'photo_total': photo_total,
        'more_desktop': photo_total - len(shown) if photo_total > PLACE_PHOTOS_DESKTOP else 0,
        'more_phone': photo_total - phone_limit if photo_total > PLACE_PHOTOS_PHONE else 0,
        # Кнопка U ведёт на список мест без точки. До фильтра карты (П20) — указатель.
        'unlocated_count': Feature.objects.filter(object_type='unplaced').count(),
        'unlocated_url': reverse('places') + '?sure=u',
        # Превью для соцсетей: заглавное фото, иначе первое фото места;
        # совсем без фото шаблон подставит общую карту.
        'og_photo': cover_og['large'] if cover_og else _media_urls(photos[0])['medium'] if photos else '',
        'og_image_width': og_width, 'og_image_height': og_height,
        'published_time': _feature_published(feature.key, scene_modified),
        'modified_time': modified_time,
        'places_url': reverse('places'),
        'map_url': reverse('index') + '?place=' + feature.key,
        'gallery_url': _gallery_url(place=feature.key, place_feature=feature)}
    context['jsonld'] = schema.place(request, context)
    response = render(request, 'atlas/place.html', context)
    response['Cache-Control'] = 'no-cache'
    return response


# Матрица «How sure is each pin»: что даёт текст и что добавляет атлас, пример на уровень.
METHOD_MATRIX = {
    'A': (_('The street, a neighbour or a named site'), _('The exact lot and the building outline')),
    'B': (_('Routes, distances, directions'), _('Which street, and the house itself')),
    'C': (_('Only a description'), _('The whole position, as a plausible option')),
    'U': (_('That the place exists'), _('Nothing: no point is drawn')),
}
# A/B/C — те же места, что кадры локаторов 'example' (locators.EXAMPLES); у U кадра нет.
METHOD_EXAMPLES = {**dict(zip('ABC', LOCATOR_EXAMPLES)), 'U': 'U3'}
# Роль внешнего источника (Source.metadata['role_type']) → чип на странице метода.
SOURCE_ROLES = {
    'inspiration': _('Inspiration'),
    'plausibility': _('Plausibility check'),
    'analogue': _('Analogue only'),
    'context': _('Context'),
    'excluded': _('Excluded as geography'),
}


def _method_levels():
    """Четыре строки матрицы: уровень, число мест из БД и пример (кадр локатора или U)."""
    places = Feature.objects.filter(object_type__in=('site', 'unplaced'))
    counts = dict(places.order_by().values_list('confidence').annotate(n=Count('key')))
    examples = {f.key: f for f in places.filter(key__in=METHOD_EXAMPLES.values())}
    levels = []
    for level in confidence_levels():
        letter = level['letter']
        gives, adds = METHOD_MATRIX[letter]
        example = examples.get(METHOD_EXAMPLES[letter])
        levels.append({**level, 'gives': gives, 'adds': adds, 'count': counts.get(letter, 0),
                       'example': example and {
                           'key': example.key, 'name': feature_name(example),
                           'url': reverse('place', args=[place_slug(example)])}})
    return levels


@require_safe
def method(request):
    """Страница «Sources & method»: шкала A/B/C/U с примерами, роман и геометрия,
    веб-источники из БД (роль — metadata['role_type']), «Using the map»."""
    setting = Setting.objects.filter(pk='atlas').first()
    cfg = setting.value if setting else {}
    geometry = cfg.get('method_geometry', '')
    if _is_ru():
        # Перевод настроек атласа живёт отдельной строкой settings (i18n_ru):
        # canonical-строку 'atlas' компилятор payload копирует целиком.
        ru = Setting.objects.filter(pk='i18n_ru').first()
        if ru and isinstance(ru.value, dict):
            geometry = ru.value.get('method_geometry') or geometry
    sources = []
    for s in Source.objects.filter(kind='web').order_by('key'):
        metadata = s.metadata if isinstance(s.metadata, dict) else {}
        ru = metadata.get('ru', {}) if _is_ru() else {}
        # «Stephen King - IT: Inspiration» → издатель над ссылкой и название ссылки.
        title = ru.get('title') or s.title
        publisher, _sep, short = title.partition(' - ')
        role_type = metadata.get('role_type')
        sources.append({'key': s.key, 'url': s.url,
                        'publisher': publisher if short else '', 'title': short or title,
                        'role': ru.get('role') or s.role,
                        'role_type': role_type if role_type in SOURCE_ROLES else '',
                        'role_label': SOURCE_ROLES.get(role_type, '')})
    page_title = _('Mapping Derry, Maine — Sources & Method · Stephen King’s IT')
    meta_description = _(
        'Learn how the map of Derry, Maine was reconstructed from Stephen King’s IT, including '
        'sources, evidence, confidence levels and mapping decisions.')
    breadcrumb = _('Sources & method')
    levels = _method_levels()
    response = render(request, 'atlas/method.html', {
        'method_geometry': geometry, 'sources': sources,
        'levels': levels, 'places_count': sum(level['count'] for level in levels),
        'breadcrumb': breadcrumb, 'current_hub': 'method',
        'page_title': page_title, 'meta_description': meta_description,
        'jsonld': schema.method(request, page_title, meta_description, breadcrumb)})
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def media(request, media_path):
    """Раздача медиа (фотографий). Имена файлов содержат хеш содержимого,
    поэтому ответ кешируется бессрочно; новые версии получают новые имена."""
    try:
        full = Path(safe_join(settings.MEDIA_ROOT, media_path))
    except ValueError:
        raise Http404
    if not full.is_file():
        raise Http404
    response = FileResponse(open(full, 'rb'))
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


@require_safe
def sitemap(request):
    """sitemap.xml вручную (django.contrib.sitemaps тянет фреймворк sites):
    все индексируемые страницы в обеих языковых версиях с hreflang-парами,
    стабильными датами изменения и image-sitemap для страниц с изображениями."""
    scene_modified = _scene_modified()
    photos = list(Photo.objects.prefetch_related('characters', 'tags').order_by('id'))
    covers = list(PlaceCover.objects.order_by('feature_key', 'year'))
    photos_by_feature = {}
    covers_by_feature = {}
    for photo in photos:
        photos_by_feature.setdefault(photo.feature_key, []).append(photo)
    for cover in covers:
        covers_by_feature.setdefault(cover.feature_key, []).append(cover)

    latest_photo = max((p.modified for p in photos), default=None)
    latest_cover = max((c.modified for c in covers), default=None)
    gallery_dates = [value for value in (scene_modified, latest_photo) if value]
    place_index_dates = [value for value in (scene_modified, latest_photo, latest_cover) if value]
    entries = [
        (reverse('index'), scene_modified, []),
        (reverse('places'), max(place_index_dates) if place_index_dates else None, []),
        (reverse('gallery'), max(gallery_dates) if gallery_dates else None, []),
        (reverse('method'), scene_modified, []),
        (reverse('articles'), HUB_LASTMOD, []),
        (reverse('derry_real'), HUB_LASTMOD, []),
        (reverse('derry_bangor'), HUB_LASTMOD, []),
        (reverse('derry_books'), HUB_LASTMOD, []),
        (reverse('printable_map'), HUB_LASTMOD, []),
    ]

    def add_photo_landing(path, landing_photos):
        entries.append((
            path,
            max(photo.modified for photo in landing_photos),
            [settings.MEDIA_URL + relative_paths(photo.sha256, photo.ext)['original']
             for photo in landing_photos],
        ))

    features_with_photos = Feature.objects.in_bulk(
        key for key in photos_by_feature if key)
    for key, feature_photos in sorted(photos_by_feature.items()):
        feature = features_with_photos.get(key)
        if feature:
            add_photo_landing(
                reverse('gallery_place', args=[gallery_place_slug(feature)]), feature_photos)

    photos_by_character = {}
    photos_by_tag = {}
    photos_by_year = {}
    for photo in photos:
        for character in photo.characters.all():
            photos_by_character.setdefault(character.slug, []).append(photo)
        for tag in photo.tags.all():
            photos_by_tag.setdefault(tag.slug, []).append(photo)
        if photo.year:
            photos_by_year.setdefault(photo.year, []).append(photo)
    for slug, landing_photos in sorted(photos_by_character.items()):
        add_photo_landing(reverse('gallery_character', args=[slug]), landing_photos)
    for slug, landing_photos in sorted(photos_by_tag.items()):
        add_photo_landing(reverse('gallery_tag', args=[slug]), landing_photos)
    for year, landing_photos in sorted(photos_by_year.items()):
        add_photo_landing(reverse('gallery_year', args=[year]), landing_photos)

    for feature in Feature.objects.filter(object_type__in=('site', 'unplaced')).order_by('key'):
        feature_photos = photos_by_feature.get(feature.key, [])
        feature_covers = covers_by_feature.get(feature.key, [])
        dates = [value for value in [scene_modified,
                 *(p.modified for p in feature_photos),
                 *(c.modified for c in feature_covers)] if value]
        images = [settings.MEDIA_URL + cover_relative_paths(c.sha256, c.ext)['original']
                  for c in feature_covers]
        images += [settings.MEDIA_URL + relative_paths(p.sha256, p.ext)['original']
                   for p in feature_photos]
        if not images:
            images = [settings.STATIC_URL + 'atlas/og-map.jpg']
        entries.append((reverse('place', args=[place_slug(feature)]),
                        max(dates) if dates else None, images))
    for photo in photos:
        entries.append((reverse('photo', args=[photo.id]), photo.modified,
                        [settings.MEDIA_URL + relative_paths(photo.sha256, photo.ext)['original']]))

    items = []
    for path, modified, image_paths in entries:
        en, ru = request.build_absolute_uri(path), request.build_absolute_uri(translate_url(path, 'ru'))
        alternates = (f'<xhtml:link rel="alternate" hreflang="en" href="{escape(en)}"/>'
                      f'<xhtml:link rel="alternate" hreflang="ru" href="{escape(ru)}"/>'
                      f'<xhtml:link rel="alternate" hreflang="x-default" href="{escape(en)}"/>')
        lastmod = f'<lastmod>{modified.isoformat()}</lastmod>' if modified else ''
        images = ''.join(f'<image:image><image:loc>{escape(request.build_absolute_uri(image_path))}'
                         f'</image:loc></image:image>' for image_path in image_paths)
        items += [f'<url><loc>{escape(en)}</loc>{lastmod}{alternates}{images}</url>',
                  f'<url><loc>{escape(ru)}</loc>{lastmod}{alternates}{images}</url>']
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:xhtml="http://www.w3.org/1999/xhtml" '
           'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
           + ''.join(items) + '</urlset>\n')
    return HttpResponse(xml, content_type='application/xml')


@require_safe
def robots(request):
    """Сочетания фильтров галереи закрыты: в индексе только лендинги из sitemap.
    Адреса без слеша тоже — краулеры отрезают его сами."""
    return HttpResponse('User-agent: *\nDisallow: /api/\n'
                        'Disallow: /photos?\nDisallow: /photos/?\n'
                        'Disallow: /ru/photos?\nDisallow: /ru/photos/?\n'
                        'Sitemap: ' + request.build_absolute_uri(reverse('sitemap')) + '\n',
                        content_type='text/plain')


@require_safe
def health(request):
    ready = MapState.objects.filter(pk=1, initialized=True).exists()
    return HttpResponse('ok\n' if ready else 'not initialized\n', status=200 if ready else 503,
                        content_type='text/plain')
