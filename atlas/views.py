from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse, HttpResponse, HttpResponseNotModified
from django.shortcuts import render
from django.utils._os import safe_join
from django.views.decorators.http import require_safe
from .models import MapState
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
