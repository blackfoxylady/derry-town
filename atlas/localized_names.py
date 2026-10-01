"""Russian display names for stable atlas and gallery identifiers.

Canonical English names and slugs remain the source of URLs and dataset identity.
This module only supplies presentation labels and search aliases.
"""
from functools import lru_cache
import copy
import json
from pathlib import Path

from django.conf import settings
from django.utils.text import slugify
from django.utils.translation import get_language


@lru_cache(maxsize=1)
def _glossary():
    path = Path(settings.BASE_DIR) / 'data' / 'proper_names_ru.json'
    return json.loads(path.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def _place_names():
    path = Path(settings.BASE_DIR) / 'data' / 'place_editorial.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    return {key: value['name_ru'] for key, value in data['places'].items()}


def _is_ru(russian=None):
    return get_language() == 'ru' if russian is None else russian


def feature_name(feature, russian=None):
    if _is_ru(russian):
        if name := _place_names().get(str(feature.key)):
            return name
        entry = _glossary()['features'].get(str(feature.key), {})
        if entry.get('name'):
            return entry['name']
    return feature.name


def feature_search_terms(feature):
    entry = _glossary()['features'].get(str(feature.key), {})
    return [feature.name, feature.short, _place_names().get(str(feature.key), entry.get('name', '')),
            *(entry.get('aliases') or [])]


def localize_map_payload(payload):
    """Return an RU presentation copy without changing canonical EN map data.

    Map identifiers, coordinates and English URL slugs remain stable.  Only
    reader-facing names, compact labels and search aliases are added/replaced.
    """
    localized = copy.deepcopy(payload)
    glossary = _glossary()
    features = glossary['features']
    short_names = glossary.get('short_names', {})
    for group in ('sites', 'unplaced'):
        for item in localized['data'][group]:
            entry = features.get(str(item['id']))
            if not entry or not entry.get('name'):
                continue
            english_name = item['name']
            english_short = item.get('short', english_name)
            item['slug'] = slugify(english_name)
            item['search_aliases'] = list(dict.fromkeys(filter(None, (
                english_name, english_short, *(entry.get('aliases') or [])))))
            item['name'] = entry['name']
            if 'short' in item:
                item['short'] = short_names.get(str(item['id']), entry['name'])
    labels = glossary.get('labels', {})
    for label in localized['labels']:
        label['text'] = labels.get(label['text'], label['text'])
    return localized


def character_name(character, russian=None):
    if _is_ru(russian):
        return _glossary()['characters'].get(character.slug, character.name)
    return character.name


def tag_name(tag_or_slug, russian=None):
    slug = tag_or_slug.slug if hasattr(tag_or_slug, 'slug') else str(tag_or_slug)
    if _is_ru(russian):
        return _glossary()['tags'].get(slug, slug.replace('-', ' '))
    return slug.replace('-', ' ').title()
