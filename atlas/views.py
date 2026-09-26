from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from django.conf import settings
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse, HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, translate_url
from django.utils._os import safe_join
from django.utils.text import slugify
from django.utils.translation import get_language, gettext_lazy as _
from django.views.decorators.http import require_safe
from .models import Character, Evidence, Feature, MapState, Photo, Setting, Source, Tag
from .photos import MEDIUM_SIZE, THUMB_SIZE, relative_paths
from .rendering import current_payload, RENDER_VERSION


@require_safe
def index(request):
    response = render(request, 'atlas/index.html')
    response['Cache-Control'] = 'no-cache'
    return response


# Русские тексты живут рядом с каноническими английскими: у Feature и Source —
# в metadata['ru'] (валидация датасета сознательно не заглядывает в metadata),
# у Photo — в колонке caption_ru. Пустой перевод откатывается на английский.

def _is_ru():
    return get_language() == 'ru'


def _feature_ru(feature):
    ru = (feature.metadata or {}).get('ru') if isinstance(feature.metadata, dict) else None
    return ru if isinstance(ru, dict) else {}


def _feature_note(feature):
    return (_feature_ru(feature).get('note') or feature.note) if _is_ru() else feature.note


def _caption(photo, ru=None):
    ru = _is_ru() if ru is None else ru
    return (photo.caption_ru or photo.caption) if ru else photo.caption


@require_safe
def map_data(request):
    state = MapState.objects.select_related('revision').only('initialized','revision_id','revision__digest','revision__id').get(pk=1)
    if not state.initialized:
        return JsonResponse({'error':'Atlas is not initialized.'}, status=503)
    # API живёт вне языкового префикса; язык приходит явным параметром ?lang=ru
    # и попадает в ETag, чтобы версии не перепутались в кеше браузера.
    ru = request.GET.get('lang') == 'ru'
    suffix = '-ru' if ru else ''
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
    накладываются описания и заметки evidence из Feature.metadata['ru'].
    Названия мест сознательно остаются английскими."""
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
    longest = max(photo.width, photo.height)

    def fitted_width(max_side):
        return photo.width if longest <= max_side else max(1, round(photo.width * max_side / longest))

    sources = [(urls['thumb'], fitted_width(THUMB_SIZE)),
               (urls['medium'], fitted_width(MEDIUM_SIZE))]
    # Very small originals produce identical thumb and medium widths. Keep the
    # srcset valid by listing each width only once.
    unique = []
    for url, width in sources:
        if all(existing_width != width for _, existing_width in unique):
            unique.append((url, width))
    return {'thumb': urls['thumb'], 'medium': urls['medium'],
            'srcset': ', '.join(f'{url} {width}w' for url, width in unique)}


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
        entry = {'name': feature.name, 'object_type': feature.object_type,
                 'photos': [{'id': p.id, 'thumb': _media_urls(p)['thumb'],
                             'caption': _caption(p, ru), 'year': p.year} for p in group]}
        if feature.geometry_id:
            entry['anchor'] = _photo_anchor(feature.geometry.shape)
        result[key] = entry
    response = JsonResponse({'features': result},
                            json_dumps_params={'ensure_ascii': False, 'separators': (',', ':')})
    response['Cache-Control'] = 'no-cache'
    return response


def _gallery_url(place='', character='', tags=(), year=''):
    """URL галереи; запятая и двоеточие не экранируются, чтобы ссылками
    вида ?place=road:02&tag=library,summer было удобно делиться."""
    pairs = [('place', place), ('character', character), ('tag', ','.join(tags)), ('year', year)]
    query = urlencode([(k, v) for k, v in pairs if v], safe=',:')
    return reverse('gallery') + ('?' + query if query else '')


@require_safe
def gallery(request):
    """Фильтры в query-параметрах: place/character/year — одно значение,
    tag — несколько через запятую, «хотя бы один из»; измерения сочетаются как И."""
    place = request.GET.get('place', '').strip()
    character = request.GET.get('character', '').strip()
    year = request.GET.get('year', '').strip()
    tags = []
    for t in request.GET.get('tag', '').split(','):
        if (t := t.strip()) and t not in tags:
            tags.append(t)
    photos = Photo.objects.prefetch_related('characters', 'tags')
    if place:
        photos = photos.filter(feature_key=place)
    if character:
        photos = photos.filter(characters__slug=character)
    if tags:
        photos = photos.filter(tags__slug__in=tags).distinct()
    if year:
        photos = photos.filter(year=int(year)) if year.isdigit() else photos.none()

    place_counts = Counter(Photo.objects.exclude(feature_key='').values_list('feature_key', flat=True))
    features = Feature.objects.in_bulk(set(place_counts) | ({place} if place else set()))

    def option(label, count, active, url):
        return {'label': label, 'count': count, 'active': active, 'url': url}

    def single(values, current, build):
        """Опции одиночного измерения: клик по активной снимает фильтр.
        Значение из URL, которого нет среди опций, добавляется, чтобы его
        было видно и можно было снять."""
        options = [option(label, n, v == current, build('' if v == current else v)) for v, label, n in values]
        if current and all(v != current for v, _, _ in values):
            options.append(option(current, 0, True, build('')))
        return options

    place_values = sorted(((k, features[k].name if k in features else k, n) for k, n in place_counts.items()),
                          key=lambda t: t[1])
    character_values = [(c.slug, c.name, c.n) for c in
                        Character.objects.filter(photo__isnull=False).annotate(n=Count('photo')).order_by('name')]
    tag_values = [(t.slug, t.slug, t.n) for t in
                  Tag.objects.filter(photo__isnull=False).annotate(n=Count('photo')).order_by('slug')]
    year_values = [(str(y), str(y), n) for y, n in
                   sorted(Counter(Photo.objects.exclude(year=None).values_list('year', flat=True)).items())]

    groups = [
        {'title': _('Place'), 'options': single(place_values, place, lambda v: _gallery_url(v, character, tags, year))},
        {'title': _('Character'), 'options': single(character_values, character,
                                                 lambda v: _gallery_url(place, v, tags, year))},
        {'title': _('Tags'), 'options':
            [option(label, n, v in tags,
                    _gallery_url(place, character,
                                 [t for t in tags if t != v] if v in tags else tags + [v], year))
             for v, label, n in tag_values] +
            [option(t, 0, True, _gallery_url(place, character, [x for x in tags if x != t], year))
             for t in tags if all(v != t for v, _, _ in tag_values)]},
    ]
    # Год появляется в панели, только когда лет больше одного (или в URL
    # пришёл год, которого нет среди фото, — иначе его нечем снять).
    if len(year_values) > 1 or (year and all(v != year for v, _, _ in year_values)):
        groups.append({'title': _('Year'), 'options': single(year_values, year,
                                                          lambda v: _gallery_url(place, character, tags, v))})

    cards = []
    for p in photos:
        f = features.get(p.feature_key)
        cards.append({'photo': p, **_card_image(p), 'caption': _caption(p),
                      'place_label': f.name if f else p.feature_key,
                      'place_url': _gallery_url(place=p.feature_key) if p.feature_key else '',
                      'year_url': _gallery_url(year=str(p.year)) if p.year else ''})
    response = render(request, 'atlas/gallery.html', {
        'groups': groups, 'cards': cards, 'clear_url': reverse('gallery'),
        'filtered': bool(place or character or tags or year)})
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
    response = render(request, 'atlas/photo.html', {
        'photo': photo, 'urls': _media_urls(photo), 'caption': _caption(photo),
        'place_page_url': reverse('place', args=[place_slug(feature)]) if on_map else '',
        'place_label': feature.name if feature else photo.feature_key,
        'place_url': _gallery_url(place=photo.feature_key) if photo.feature_key else '',
        'map_url': map_url,
        'year_url': _gallery_url(year=str(photo.year)) if photo.year else '',
        'characters': [{'name': c.name, 'url': _gallery_url(character=c.slug)}
                       for c in photo.characters.order_by('name')],
        'tags': [{'slug': t.slug, 'url': _gallery_url(tags=[t.slug])} for t in photo.tags.order_by('slug')]})
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
    for e in Evidence.objects.filter(feature=feature).order_by('order', 'key'):
        note = notes_ru.get(e.key) or e.note
        group = next((r for r in refs if r['reference'] == e.reference), None)
        if group is None:
            refs.append({'reference': e.reference, 'notes': [note] if note else []})
        elif note:
            group['notes'].append(note)
    photos = Photo.objects.filter(feature_key=feature.key)
    response = render(request, 'atlas/place.html', {
        'feature': feature, 'note': _feature_note(feature),
        'confidence': CONFIDENCE.get(feature.confidence, ''), 'refs': refs,
        'cards': [{'photo': p, **_card_image(p), 'caption': _caption(p)} for p in photos],
        # Превью для соцсетей: первое фото места; без фото шаблон подставит общую карту.
        'og_photo': _media_urls(photos[0])['medium'] if photos else '',
        'map_url': reverse('index') + '?place=' + feature.key,
        'gallery_url': _gallery_url(place=feature.key)})
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
    response = render(request, 'atlas/method.html', {'method_geometry': geometry, 'sources': sources})
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
    все индексируемые страницы в обеих языковых версиях с hreflang-парами."""
    paths = [reverse('index'), reverse('gallery'), reverse('method')]
    for f in Feature.objects.filter(object_type__in=('site', 'unplaced')).order_by('key'):
        paths.append(reverse('place', args=[place_slug(f)]))
    for pid in Photo.objects.order_by('id').values_list('id', flat=True):
        paths.append(reverse('photo', args=[pid]))
    items = []
    for path in paths:
        en, ru = request.build_absolute_uri(path), request.build_absolute_uri(translate_url(path, 'ru'))
        alternates = (f'<xhtml:link rel="alternate" hreflang="en" href="{en}"/>'
                      f'<xhtml:link rel="alternate" hreflang="ru" href="{ru}"/>'
                      f'<xhtml:link rel="alternate" hreflang="x-default" href="{en}"/>')
        items += [f'<url><loc>{en}</loc>{alternates}</url>', f'<url><loc>{ru}</loc>{alternates}</url>']
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:xhtml="http://www.w3.org/1999/xhtml">' + ''.join(items) + '</urlset>\n')
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
