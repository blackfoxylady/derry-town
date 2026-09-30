"""Versioned Russian captions for published photographs.

The SHA-256 key follows image content across databases and imports. Database
``caption_ru`` remains the editable fallback for photographs not curated here.
"""
from functools import lru_cache
import json
from pathlib import Path

from django.conf import settings
from django.utils.translation import get_language


@lru_cache(maxsize=1)
def _captions():
    path = Path(settings.BASE_DIR) / 'data' / 'photo_captions_ru.json'
    return json.loads(path.read_text(encoding='utf-8'))


def photo_caption(photo, russian=None):
    russian = get_language() == 'ru' if russian is None else russian
    if russian:
        return _captions().get(photo.sha256) or photo.caption_ru or photo.caption
    return photo.caption
