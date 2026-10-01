from collections import Counter
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlencode
from xml.sax.saxutils import escape
from django.conf import settings
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse, HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, translate_url
from django.utils._os import safe_join
from django.utils.text import slugify
from django.utils.translation import get_language, gettext_lazy as _, ngettext
from django.views.decorators.http import require_safe
from . import schema
from .covers import COVER_LARGE_SIZE, COVER_MEDIUM_SIZE, relative_paths as cover_relative_paths
from .localized_names import (character_name, feature_name, feature_search_terms,
                              localize_map_payload, tag_name)
from .localized_photos import photo_caption
from .models import (Character, Evidence, Feature, MapState, Photo, PlaceCover,
                     Revision, Setting, Source, Tag)
from .photos import MEDIUM_SIZE, THUMB_SIZE, relative_paths
from .rendering import current_payload, RENDER_VERSION


HUB_LASTMOD = date(2026, 9, 29)
RU_MAP_PAYLOAD_VERSION = '2'
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
            'ru': ('Сравнение вымышленного Дерри с Бангором: канал, Kenduskeag Stream, '
                   'Thomas Hill Standpipe, библиотека и другие реальные истоки романа «Оно».'),
        },
        'breadcrumb': {'en': 'How Bangor inspired Derry', 'ru': 'Как Бангор вдохновил Дерри'},
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


def _hub_page(request, key):
    """Render a static editorial hub in either complete editorial language version."""
    config = HUB_PAGES[key]
    language = 'ru' if _is_ru() else 'en'
    page_title = config['title'][language]
    meta_description = config['description'][language]
    breadcrumb = config['breadcrumb'][language]
    context = {
        'page_title': page_title,
        'meta_description': meta_description,
        'breadcrumb': breadcrumb,
        'published_time': HUB_LASTMOD.isoformat(),
    }
    context['jsonld'] = schema.editorial(
        request, page_title, meta_description, breadcrumb, HUB_LASTMOD)
    response = render(request, config['template'], context)
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
        if ru:
            payload = _localized_payload(payload)
        etag = '"'+key+suffix+'"'
        response = JsonResponse(payload, json_dumps_params={'ensure_ascii':False,'separators':(',',':')})
    response['ETag'] = etag
    response['Cache-Control'] = 'no-cache'
    return response


def _localized_payload(payload):
    """Русская версия payload карты: поверх канонического английского
    накладываются имена, подписи, описания и заметки evidence."""
    payload = localize_map_payload(payload)
    meta = {f.key: ru for f in Feature.objects.exclude(metadata={})
            if (ru := _feature_ru(f))}
    if not meta:
        return payload
    ev_keys = {}
    for e in Evidence.objects.order_by('order', 'key').values_list('feature_id', 'key', named=False):
        ev_keys.setdefault(e[0], []).append(e[1])
    for group in ('sites', 'unplaced'):
        for s in payload['data'][group]:
            ru = meta.get(str(s['id']))
            if not ru:
                continue
            if ru.get('note'):
                s['note'] = ru['note']
            notes = ru.get('evidence') or {}
            # Порядок sources в payload повторяет сортировку Evidence по (order, key).
            for src, ekey in zip(s['sources'], ev_keys.get(str(s['id']), [])):
                if notes.get(ekey):
                    src['note'] = notes[ekey]
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
        result[key] = entry
    response = JsonResponse({'features': result},
                            json_dumps_params={'ensure_ascii': False, 'separators': (',', ':')})
    response['Cache-Control'] = 'no-cache'
    return response


def gallery_place_slug(feature):
    """Readable photo-landing slug for every Feature type, including roads."""
    return slugify(f'{feature.key}-{feature.name}')


def _gallery_url(place='', character='', tags=(), year='', place_feature=None):
    """Canonical landing URL for one filter; query URL for combinations.

    Query strings remain useful for combined filters, while every valid single
    dimension has a crawlable, self-canonical path.
    """
    active = sum((bool(place), bool(character), bool(tags), bool(year)))
    if active == 1:
        if place:
            feature = place_feature or Feature.objects.filter(pk=place).first()
            if feature:
                return reverse('gallery_place', args=[gallery_place_slug(feature)])
        elif character:
            return reverse('gallery_character', args=[character])
        elif len(tags) == 1:
            return reverse('gallery_tag', args=[tags[0]])
        elif year and str(year).isdigit():
            return reverse('gallery_year', args=[year])
    pairs = [('place', place), ('character', character), ('tag', ','.join(tags)), ('year', year)]
    query = urlencode([(k, v) for k, v in pairs if v], safe=',:')
    return reverse('gallery') + ('?' + query if query else '')


def _place_sort_key(feature):
    """Stable atlas order: numbered sites first, then named unlocated entries."""
    return (0, int(feature.key)) if feature.key.isdigit() else (1, feature.key.casefold())


def _place_number(feature):
    return f'{int(feature.key):02d}' if feature.key.isdigit() else feature.key.upper()


def _kind_label(feature):
    if feature.object_type == 'unplaced':
        return _('Unlocated')
    return {
        'Homes': _('Homes'), 'Civic': _('Civic'), 'Barrens': _('Barrens'),
        'Encounters': _('Encounters'), 'Historical': _('Historical'),
        'Outlying': _('Outlying'),
    }.get(feature.kind, feature.kind)


_CHAPTER = re.compile(r'^Ch\.\s*\d+\s*-\s*.+$', re.IGNORECASE)
_INTERLUDE = re.compile(r'^(?:First|Second|Third|Fourth|Fifth)\s+Interlude$', re.IGNORECASE)
_REFERENCE_SECTION = re.compile(r'\s*/\s*\d+\s*$')


def _chapter_reference(reference):
    """Return a stable key and display label for a novel chapter reference.

    Evidence stores editorial strings such as ``Ch. 11 - Walking Tours / 4``.
    The trailing section is intentionally removed so related places are joined
    by chapter. Bare page/location references such as ``[1771]`` are ignored.
    """
    label = _REFERENCE_SECTION.sub('', ' '.join(reference.split()))
    if not (_CHAPTER.fullmatch(label) or _INTERLUDE.fullmatch(label)):
        return None
    return label.casefold(), label


def _reference_key(reference):
    return ' '.join(reference.split()).casefold()


def _related_place_card(feature, chapter=''):
    return {
        'feature': feature,
        'name': feature_name(feature),
        'number': _place_number(feature),
        'url': reverse('place', args=[place_slug(feature)]),
        'kind': _kind_label(feature),
        'chapter': chapter,
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
        parsed = _chapter_reference(evidence.reference)
        if parsed:
            key, label = parsed
            current_chapters.setdefault(key, label)
            reference_chapters[_reference_key(evidence.reference)] = key

    semantic = {}
    if current_chapters:
        evidence_rows = (Evidence.objects.filter(
            feature__object_type__in=('site', 'unplaced')).exclude(feature=feature)
            .select_related('feature').order_by('feature_id', 'order', 'key'))
        for evidence in evidence_rows:
            parsed = _chapter_reference(evidence.reference)
            if not parsed or parsed[0] not in current_chapters:
                continue
            entry = semantic.setdefault(evidence.feature_id, {
                'feature': evidence.feature, 'references': set(), 'chapters': set(),
            })
            entry['references'].add(_reference_key(evidence.reference))
            entry['chapters'].add(parsed[0])

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
            card['chapter'] = primary_chapter(entry)

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


@require_safe
def places(request):
    """Server-rendered directory of every place, progressively enhanced with local filters."""
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
    mapped_count = 0
    for order, feature in enumerate(features):
        mapped = feature.object_type == 'site'
        mapped_count += int(mapped)
        if mapped and feature.kind:
            kinds[feature.kind] += 1
        feature_photos = photos_by_feature.get(feature.key, [])
        feature_covers = covers_by_feature.get(feature.key, [])
        localized = _feature_place_content(feature)
        display_name = feature_name(feature)
        note = _feature_note(feature)
        ru = _feature_ru(feature)
        content_complete = bool(feature.note and feature.about and feature.confidence_explanation)
        ru_complete = all(ru.get(field) for field in
                          ('note', 'about', 'confidence_explanation'))

        image = None
        if feature_covers:
            cover = _cover_context(feature_covers[0])
            image = {'src': cover['src'], 'srcset': cover['srcset'],
                     'alt': cover['alt'], 'width': cover['width'], 'height': cover['height']}
        elif feature_photos:
            photo = feature_photos[0]
            photo_image = _card_image(photo)
            image = {**photo_image, 'src': photo_image['thumb'],
                     'alt': _photo_alt(photo, feature),
                     'width': photo.width, 'height': photo.height}

        search_text = ' '.join(filter(None, (
            feature.key, *feature_search_terms(feature), feature.kind, feature.period,
            note, localized['about'], localized['confidence_explanation'],
        )))
        cards.append({
            'feature': feature, 'name': display_name,
            'number': _place_number(feature),
            'url': reverse('place', args=[place_slug(feature)]),
            'map_url': reverse('index') + '?place=' + feature.key if mapped else '',
            'gallery_url': (_gallery_url(place=feature.key, place_feature=feature)
                            if feature_photos else ''),
            'mapped': mapped, 'note': note,
            'confidence_label': CONFIDENCE.get(feature.confidence, ''),
            'photo_count': len(feature_photos), 'cover_count': len(feature_covers),
            'evidence_count': feature.evidence_count, 'image': image,
            'content_complete': content_complete, 'ru_complete': ru_complete,
            'search_text': search_text, 'order': order,
        })

    place_count = len(cards)
    unlocated_count = place_count - mapped_count
    kind_order = ('Homes', 'Civic', 'Barrens', 'Encounters', 'Historical', 'Outlying')
    kind_names = [kind for kind in kind_order if kinds[kind]]
    kind_names += sorted(kind for kind in kinds if kind not in kind_order)
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
        'cards': cards, 'kinds': [(kind, kinds[kind]) for kind in kind_names],
        'place_count': place_count, 'mapped_count': mapped_count,
        'unlocated_count': unlocated_count,
        'confidence_counts': Counter(feature.confidence for feature in features),
        'page_title': page_title, 'meta_description': meta_description,
    }
    context['jsonld'] = schema.places(request, page_title, meta_description, cards)
    response = render(request, 'atlas/places.html', context)
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def gallery(request, filter_type='', filter_slug='', filter_year=None):
    """Photograph gallery and crawlable single-filter landing pages.

    One valid filter has a readable path. Combined filters stay in the query
    string and canonicalize to the main gallery. Tags remain OR within their
    dimension; the other dimensions combine with them as AND.
    """
    place_counts = Counter(Photo.objects.exclude(feature_key='').values_list('feature_key', flat=True))
    features = Feature.objects.in_bulk(place_counts)
    characters = list(Character.objects.filter(photo__isnull=False)
                      .annotate(n=Count('photo')).order_by('name'))
    tag_rows = list(Tag.objects.filter(photo__isnull=False)
                    .annotate(n=Count('photo')).order_by('slug'))
    year_counts = Counter(Photo.objects.exclude(year=None).values_list('year', flat=True))
    characters_by_slug = {character.slug: character for character in characters}
    tags_by_slug = {tag.slug: tag for tag in tag_rows}

    place = character = year = ''
    tags = []
    landing = None
    if filter_type == 'place':
        feature = next((candidate for candidate in features.values()
                        if gallery_place_slug(candidate) == filter_slug), None)
        if feature is None:
            raise Http404
        place = feature.key
        landing = {'type': 'place', 'label': feature_name(feature)}
    elif filter_type == 'character':
        character_object = characters_by_slug.get(filter_slug)
        if character_object is None:
            raise Http404
        character = character_object.slug
        landing = {'type': 'character', 'label': character_name(character_object)}
    elif filter_type == 'tag':
        tag = tags_by_slug.get(filter_slug)
        if tag is None:
            raise Http404
        tags = [tag.slug]
        landing = {'type': 'tag', 'label': tag_name(tag)}
    elif filter_type == 'year':
        if filter_year not in year_counts:
            raise Http404
        year = str(filter_year)
        landing = {'type': 'year', 'label': year}
    elif filter_type:
        raise Http404
    else:
        place = request.GET.get('place', '').strip()
        character = request.GET.get('character', '').strip()
        year = request.GET.get('year', '').strip()
        for value in request.GET.get('tag', '').split(','):
            if (value := value.strip()) and value not in tags:
                tags.append(value)

        # Old, valid single-filter query URLs permanently converge on the
        # crawlable landing. Invalid values keep the existing empty-result UX.
        known_parameters = {'place', 'character', 'tag', 'year'}
        dimensions = sum((bool(place), bool(character), bool(tags), bool(year)))
        valid_single = (
            (place in place_counts if place else False)
            or (character in characters_by_slug if character else False)
            or (len(tags) == 1 and tags[0] in tags_by_slug)
            or (year.isdigit() and int(year) in year_counts)
        )
        if (dimensions == 1 and valid_single and set(request.GET) <= known_parameters
                and (not tags or len(tags) == 1)):
            return redirect(_gallery_url(
                place, character, tags, year, place_feature=features.get(place)), permanent=True)

    photos = Photo.objects.prefetch_related('characters', 'tags')
    if place:
        photos = photos.filter(feature_key=place)
    if character:
        photos = photos.filter(characters__slug=character)
    if tags:
        photos = photos.filter(tags__slug__in=tags).distinct()
    if year:
        photos = photos.filter(year=int(year)) if year.isdigit() else photos.none()

    def option(label, count, active, url):
        return {'label': label, 'count': count, 'active': active, 'url': url}

    def single(values, current, build):
        """Clicking the active option clears it; an invalid query value stays removable."""
        options = [option(label, n, value == current,
                          build('' if value == current else value))
                   for value, label, n in values]
        if current and all(value != current for value, _, _ in values):
            options.append(option(current, 0, True, build('')))
        return options

    place_values = sorted(
        ((key, feature_name(features[key]) if key in features else key, count)
         for key, count in place_counts.items()), key=lambda item: item[1])
    character_values = sorted(
        ((item.slug, character_name(item), item.n) for item in characters),
        key=lambda item: item[1].casefold())
    tag_values = sorted(
        ((item.slug, tag_name(item), item.n) for item in tag_rows),
        key=lambda item: item[1].casefold())
    year_values = [(str(value), str(value), count)
                   for value, count in sorted(year_counts.items())]

    groups = [
        {'title': _('Place'), 'options': single(
            place_values, place, lambda value: _gallery_url(
                value, character, tags, year, place_feature=features.get(value)))},
        {'title': _('Character'), 'options': single(
            character_values, character,
            lambda value: _gallery_url(place, value, tags, year,
                                       place_feature=features.get(place)))},
        {'title': _('Tags'), 'options': [
            option(label, count, value in tags, _gallery_url(
                place, character,
                [tag for tag in tags if tag != value] if value in tags else tags + [value],
                year, place_feature=features.get(place)))
            for value, label, count in tag_values
        ] + [
            option(tag_name(value), 0, True, _gallery_url(
                place, character, [tag for tag in tags if tag != value], year,
                place_feature=features.get(place)))
            for value in tags if value not in tags_by_slug
        ]},
    ]
    if len(year_values) > 1 or (year and all(value != year for value, _, _ in year_values)):
        groups.append({'title': _('Year'), 'options': single(
            year_values, year, lambda value: _gallery_url(
                place, character, tags, value, place_feature=features.get(place)))})

    cards = []
    for photo in photos:
        feature = features.get(photo.feature_key)
        place_page_url = (reverse('place', args=[place_slug(feature)])
                          if feature and feature.object_type in ('site', 'unplaced') else '')
        place_gallery_url = (_gallery_url(place=photo.feature_key, place_feature=feature)
                             if photo.feature_key else '')
        cards.append({
            'photo': photo, **_card_image(photo), 'caption': _caption(photo),
            'alt': _photo_alt(photo, feature),
            'place_label': feature_name(feature) if feature else photo.feature_key,
            'place_url': place_page_url or place_gallery_url,
            'place_gallery_url': (place_gallery_url
                                  if place_page_url and place != photo.feature_key else ''),
            'year_url': _gallery_url(year=str(photo.year)) if photo.year else '',
        })

    gallery_heading = _('Photographs')
    gallery_intro = ''
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
        gallery_intro = meta_description

    response = render(request, 'atlas/gallery.html', {
        'groups': groups, 'cards': cards, 'clear_url': reverse('gallery'),
        'filtered': bool(place or character or tags or year),
        'landing': landing, 'gallery_heading': gallery_heading,
        'gallery_breadcrumb': gallery_heading if landing else '',
        'gallery_intro': gallery_intro,
        'page_title': page_title, 'meta_description': meta_description,
        'jsonld': schema.gallery(
            request, page_title, meta_description, gallery_heading if landing else ''),
    })
    response['Cache-Control'] = 'no-cache'
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


# Подписи уровней достоверности; совпадают с карточкой места на карте.
CONFIDENCE = {'A': _('A · Text-anchored relationship'), 'B': _('B · Inferred position'),
              'C': _('C · Proposed location'), 'U': _('U · Unlocated / off map')}


def place_slug(feature):
    """Слаг страницы места: ключ + английское название, `12-neibolt-street`.
    Не хранится в БД — собирается из текущего названия; устаревший слаг
    приводит к 301-редиректу на канонический."""
    name = slugify(feature.name)
    return feature.key.lower() + ('-' + name if name else '')


@require_safe
def place_page(request, slug):
    key = slug.split('-', 1)[0]
    feature = get_object_or_404(Feature, key__iexact=key, object_type__in=('site', 'unplaced'))
    canonical = place_slug(feature)
    if slug != canonical:
        return redirect(reverse('place', args=[canonical]), permanent=True)
    notes_ru = (_feature_ru(feature).get('evidence') or {}) if _is_ru() else {}
    # Цитаты группируются по референсу, как в карточке на карте.
    refs = []
    evidence = list(Evidence.objects.filter(feature=feature).order_by('order', 'key'))
    for e in evidence:
        note = notes_ru.get(e.key) or e.note
        group = next((r for r in refs if r['reference'] == e.reference), None)
        if group is None:
            refs.append({'reference': e.reference, 'notes': [note] if note else []})
        elif note:
            group['notes'].append(note)
    photos = Photo.objects.filter(feature_key=feature.key)
    covers = [_cover_context(c) for c in PlaceCover.objects.filter(feature_key=feature.key)]
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
    if covers:
        og_width, og_height = _fitted_dimensions(covers[0]['width'], covers[0]['height'],
                                                 COVER_LARGE_SIZE)
    elif cards:
        og_width, og_height = _fitted_dimensions(cards[0]['photo'].width, cards[0]['photo'].height,
                                                 MEDIUM_SIZE)
    else:
        og_width = og_height = None
    context = {
        'feature': feature, 'feature_name': display_name, 'note': _feature_note(feature),
        'page_title': page_title, 'meta_description': meta_description,
        'confidence': CONFIDENCE.get(feature.confidence, ''), 'refs': refs,
        'place_about': place_content['about'],
        'confidence_explanation': place_content['confidence_explanation'],
        'nearby_places': nearby_places,
        'same_chapter_places': same_chapter_places,
        'covers': covers, 'cards': cards,
        # Превью для соцсетей: заглавное фото, иначе первое фото места;
        # совсем без фото шаблон подставит общую карту.
        'og_photo': covers[0]['large'] if covers else _media_urls(photos[0])['medium'] if photos else '',
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


@require_safe
def method(request):
    """Страница «Sources & method»: те же тексты, что раньше жили в диалоге
    на карте, плюс method_geometry и веб-источники из настроек атласа."""
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
        ru = (s.metadata or {}).get('ru', {}) if _is_ru() and isinstance(s.metadata, dict) else {}
        sources.append({'key': s.key, 'url': s.url, 'title': ru.get('title') or s.title,
                        'role': ru.get('role') or s.role})
    page_title = _('Mapping Derry, Maine — Sources & Method · Stephen King’s IT')
    meta_description = _(
        'Learn how the map of Derry, Maine was reconstructed from Stephen King’s IT, including '
        'sources, evidence, confidence levels and mapping decisions.')
    response = render(request, 'atlas/method.html', {
        'method_geometry': geometry, 'sources': sources,
        'page_title': page_title, 'meta_description': meta_description,
        'jsonld': schema.method(request, page_title, meta_description)})
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
    return HttpResponse('User-agent: *\nDisallow: /api/\nSitemap: '
                        + request.build_absolute_uri(reverse('sitemap')) + '\n',
                        content_type='text/plain')


@require_safe
def health(request):
    ready = MapState.objects.filter(pk=1, initialized=True).exists()
    return HttpResponse('ok\n' if ready else 'not initialized\n', status=200 if ready else 503,
                        content_type='text/plain')
