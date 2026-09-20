from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from django.conf import settings
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse, HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404, render
from django.utils._os import safe_join
from django.views.decorators.http import require_safe
from .models import Character, Feature, MapState, Photo, Tag
from .photos import relative_paths
from .rendering import current_payload, RENDER_VERSION


@require_safe
def index(request):
    response = render(request, 'atlas/index.html')
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def map_data(request):
    state = MapState.objects.select_related('revision').only('initialized','revision_id','revision__digest','revision__id').get(pk=1)
    if not state.initialized:
        return JsonResponse({'error':'Atlas is not initialized.'}, status=503)
    etag = f'"{state.revision.digest}-r{state.revision_id}-v{RENDER_VERSION}"'
    if request.headers.get('If-None-Match') == etag:
        response = HttpResponseNotModified()
    else:
        payload, key = current_payload()
        etag = '"'+key+'"'
        response = JsonResponse(payload, json_dumps_params={'ensure_ascii':False,'separators':(',',':')})
    response['ETag'] = etag
    response['Cache-Control'] = 'no-cache'
    return response


def _media_urls(photo):
    return {k: settings.MEDIA_URL + v for k, v in relative_paths(photo.sha256, photo.ext).items()}


def _gallery_url(place='', character='', tags=(), year=''):
    """URL галереи; запятая и двоеточие не экранируются, чтобы ссылками
    вида ?place=road:02&tag=library,summer было удобно делиться."""
    pairs = [('place', place), ('character', character), ('tag', ','.join(tags)), ('year', year)]
    query = urlencode([(k, v) for k, v in pairs if v], safe=',:')
    return '/photos/' + ('?' + query if query else '')


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
        {'title': 'Place', 'options': single(place_values, place, lambda v: _gallery_url(v, character, tags, year))},
        {'title': 'Character', 'options': single(character_values, character,
                                                 lambda v: _gallery_url(place, v, tags, year))},
        {'title': 'Tags', 'options':
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
        groups.append({'title': 'Year', 'options': single(year_values, year,
                                                          lambda v: _gallery_url(place, character, tags, v))})

    cards = []
    for p in photos:
        f = features.get(p.feature_key)
        cards.append({'photo': p, 'thumb': _media_urls(p)['thumb'],
                      'place_label': f.name if f else p.feature_key,
                      'place_url': _gallery_url(place=p.feature_key) if p.feature_key else '',
                      'year_url': _gallery_url(year=str(p.year)) if p.year else ''})
    response = render(request, 'atlas/gallery.html', {
        'groups': groups, 'cards': cards, 'clear_url': '/photos/',
        'filtered': bool(place or character or tags or year)})
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def photo_page(request, photo_id):
    photo = get_object_or_404(Photo.objects.prefetch_related('characters', 'tags'), pk=photo_id)
    feature = Feature.objects.filter(pk=photo.feature_key).first() if photo.feature_key else None
    # Карта выделяет точки и нелокализованные записи; у дорог и прочих
    # контуров маркера нет, поэтому ссылки на карту у таких фото нет.
    map_url = '/?place=' + feature.key if feature and feature.object_type in ('site', 'unplaced') else ''
    response = render(request, 'atlas/photo.html', {
        'photo': photo, 'urls': _media_urls(photo),
        'place_label': feature.name if feature else photo.feature_key,
        'place_url': _gallery_url(place=photo.feature_key) if photo.feature_key else '',
        'map_url': map_url,
        'year_url': _gallery_url(year=str(photo.year)) if photo.year else '',
        'characters': [{'name': c.name, 'url': _gallery_url(character=c.slug)}
                       for c in photo.characters.order_by('name')],
        'tags': [{'slug': t.slug, 'url': _gallery_url(tags=[t.slug])} for t in photo.tags.order_by('slug')]})
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
def health(request):
    ready = MapState.objects.filter(pk=1, initialized=True).exists()
    return HttpResponse('ok\n' if ready else 'not initialized\n', status=200 if ready else 503,
                        content_type='text/plain')
