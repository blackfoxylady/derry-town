"""Russian display names for stable atlas and gallery identifiers.

Canonical English names and slugs remain the source of URLs and dataset identity.
This module only supplies presentation labels and search aliases.
"""
from functools import lru_cache
import json
from pathlib import Path

from django.conf import settings
from django.utils.translation import get_language


@lru_cache(maxsize=1)
def _glossary():
    path = Path(settings.BASE_DIR) / 'data' / 'proper_names_ru.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _is_ru(russian=None):
    return get_language() == 'ru' if russian is None else russian


def feature_name(feature, russian=None):
    if _is_ru(russian):
        entry = _glossary()['features'].get(str(feature.key), {})
        if entry.get('name'):
            return entry['name']
    return feature.name


def feature_search_terms(feature):
    entry = _glossary()['features'].get(str(feature.key), {})
    return [feature.name, feature.short, entry.get('name', ''), *(entry.get('aliases') or [])]


def character_name(character, russian=None):
    if _is_ru(russian):
        return _glossary()['characters'].get(character.slug, character.name)
    return character.name


def tag_name(tag_or_slug, russian=None):
    slug = tag_or_slug.slug if hasattr(tag_or_slug, 'slug') else str(tag_or_slug)
    if _is_ru(russian):
        return _glossary()['tags'].get(slug, slug.replace('-', ' '))
    return slug.replace('-', ' ').title()
