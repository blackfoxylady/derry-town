"""Фотографии: валидация, хранение файлов и производные размеры.

Отдельный контур данных вне ревизий атласа (см. Photo в models.py). Все
поддерживаемые записи фотографий проходят через add()/edit()/remove() этого
модуля; каталог media — производное хранилище, руками файлы не кладутся.

Имена файлов — по SHA-256 содержимого, поэтому они неизменяемы и отдаются
с бессрочным кешем. Оригинал сохраняется байт в байт; miniature (thumb) и
средний размер (medium) генерируются как JPEG.
"""
import hashlib
import os
import re
import tempfile
from pathlib import Path
from django.conf import settings
from django.db import transaction
from PIL import Image, ImageOps
from .models import Character, Feature, Photo, Tag

# Справочник разрешённых лет: эпохи романа. Расширяется правкой списка,
# схема БД не меняется.
ALLOWED_YEARS = (1906, 1929, 1930, 1958, 1985)

# Максимальная сторона производных размеров, пиксели.
THUMB_SIZE = 320
MEDIUM_SIZE = 1600
JPEG_QUALITY = 85
MAX_FILE_BYTES = 50_000_000
ALLOWED_FORMATS = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}
SLUG = re.compile(r'[a-z0-9][a-z0-9-]{0,99}')


def photo_root():
    return Path(settings.MEDIA_ROOT) / 'photos'


def relative_paths(sha256, ext):
    return {'original': f'photos/original/{sha256}.{ext}',
            'medium': f'photos/medium/{sha256}.jpg',
            'thumb': f'photos/thumb/{sha256}.jpg'}


def paths_for(photo):
    return {k: Path(settings.MEDIA_ROOT) / v for k, v in relative_paths(photo.sha256, photo.ext).items()}


def slug_name(slug):
    return ' '.join(part.capitalize() for part in slug.split('-'))


def check_slugs(values, what):
    result = []
    for v in values:
        if not isinstance(v, str) or not SLUG.fullmatch(v):
            raise ValueError(f'Invalid {what} slug: {v!r} (lowercase letters, digits, hyphens).')
        if v not in result:
            result.append(v)
    return result


def check_year(year):
    if year is None:
        return None
    if not isinstance(year, int) or isinstance(year, bool) or year not in ALLOWED_YEARS:
        raise ValueError(f'Year {year!r} is not in the allowed set {ALLOWED_YEARS}.')
    return year


def check_feature(feature_key):
    if not feature_key:
        return ''
    if not Feature.objects.filter(pk=feature_key).exists():
        raise ValueError(f'Feature {feature_key!r} does not exist in the atlas.')
    return feature_key


def _atomic_write(path, write):
    """Записывает файл через временный + os.replace, возвращает path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix='.partial')
    try:
        with os.fdopen(fd, 'wb') as f:
            write(f)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    return path


def _derivative(image, max_side, target):
    copy = image.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    if copy.mode != 'RGB':
        # Прозрачность кладётся на белый фон, а не на чёрный по умолчанию.
        background = Image.new('RGB', copy.size, (255, 255, 255))
        background.paste(copy, mask=copy.getchannel('A') if 'A' in copy.getbands() else None)
        copy = background
    return _atomic_write(target, lambda f: copy.save(f, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True))


class _Prepared:
    """Проверенный исходный файл: хеш, размеры и данные, готовые к записи."""

    def __init__(self, source):
        source = Path(source)
        if not source.is_file():
            raise ValueError(f'File not found: {source}')
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f'{source.name} exceeds {MAX_FILE_BYTES // 1_000_000} MB.')
        data = source.read_bytes()
        try:
            with Image.open(source) as probe:
                probe.verify()
            image = Image.open(source)
            image.load()
        except Exception as e:
            raise ValueError(f'{source.name} is not a readable image: {e}') from e
        if image.format not in ALLOWED_FORMATS:
            raise ValueError(f'{source.name}: unsupported format {image.format}; allowed: {sorted(ALLOWED_FORMATS)}.')
        self.name = source.name
        self.ext = ALLOWED_FORMATS[image.format]
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.data = data
        self.image = ImageOps.exif_transpose(image)
        self.width, self.height = self.image.size

    def write_files(self, created):
        """Пишет оригинал и производные; created собирает новые файлы для отката."""
        targets = {k: Path(settings.MEDIA_ROOT) / v for k, v in relative_paths(self.sha256, self.ext).items()}
        for path in targets.values():
            if not path.exists():
                created.append(path)
        _atomic_write(targets['original'], lambda f: f.write(self.data))
        _derivative(self.image, MEDIUM_SIZE, targets['medium'])
        _derivative(self.image, THUMB_SIZE, targets['thumb'])


def _cleanup(created):
    for path in created:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _apply_links(photo, characters, tags):
    photo.characters.set([Character.objects.get_or_create(slug=s, defaults={'name': slug_name(s)})[0]
                          for s in characters])
    photo.tags.set([Tag.objects.get_or_create(slug=s)[0] for s in tags])


def _validated(entry):
    """Нормализует атрибуты одной фотографии из аргументов команды/манифеста."""
    allowed = {'file', 'caption', 'feature', 'year', 'characters', 'tags', 'order'}
    unknown = set(entry) - allowed
    if unknown:
        raise ValueError(f'Unknown photo fields: {sorted(unknown)}.')
    caption = entry.get('caption', '')
    if not isinstance(caption, str):
        raise ValueError('Caption must be a string.')
    order = entry.get('order', 0)
    if not isinstance(order, int) or isinstance(order, bool) or order < 0:
        raise ValueError(f'Order must be a non-negative integer, got {order!r}.')
    return {'caption': caption,
            'year': check_year(entry.get('year')),
            'feature_key': check_feature(entry.get('feature') or ''),
            'order': order,
            'characters': check_slugs(entry.get('characters') or [], 'character'),
            'tags': check_slugs(entry.get('tags') or [], 'tag')}


def add_many(entries):
    """Добавляет партию фотографий атомарно: все или ни одной.

    entries — список словарей: file (путь) + атрибуты как в манифесте.
    Возвращает созданные Photo.
    """
    if not entries:
        raise ValueError('Nothing to import.')
    prepared = []
    for entry in entries:
        if 'file' not in entry:
            raise ValueError('Each photo entry needs a "file".')
        prepared.append((_Prepared(entry['file']), _validated(entry)))
    seen = {}
    for source, _ in prepared:
        if source.sha256 in seen:
            raise ValueError(f'{source.name} duplicates {seen[source.sha256]} in the same batch.')
        seen[source.sha256] = source.name
    existing = dict(Photo.objects.filter(sha256__in=seen).values_list('sha256', 'id'))
    for source, _ in prepared:
        if source.sha256 in existing:
            raise ValueError(f'{source.name} already imported as photo {existing[source.sha256]} (same content hash).')
    created_files, photos = [], []
    try:
        with transaction.atomic():
            for source, attrs in prepared:
                fields = {k: v for k, v in attrs.items() if k not in ('characters', 'tags')}
                photo = Photo.objects.create(sha256=source.sha256, ext=source.ext, original_name=source.name,
                                             width=source.width, height=source.height, **fields)
                _apply_links(photo, attrs['characters'], attrs['tags'])
                source.write_files(created_files)
                photos.append(photo)
    except BaseException:
        _cleanup(created_files)
        raise
    return photos


def add(file, **attrs):
    return add_many([{'file': file, **attrs}])[0]


def edit(photo_id, **changes):
    """Меняет атрибуты фотографии; файлы не трогает. None = не менять."""
    with transaction.atomic():
        try:
            photo = Photo.objects.select_for_update().get(pk=photo_id)
        except Photo.DoesNotExist:
            raise ValueError(f'Photo {photo_id} does not exist.') from None
        entry = {'caption': photo.caption, 'year': photo.year,
                 'feature': photo.feature_key, 'order': photo.order,
                 'characters': list(photo.characters.values_list('slug', flat=True)),
                 'tags': list(photo.tags.values_list('slug', flat=True))}
        entry.update({k: v for k, v in changes.items() if v is not None})
        attrs = _validated(entry)
        for field in ('caption', 'year', 'feature_key', 'order'):
            setattr(photo, field, attrs[field])
        photo.save(update_fields=['caption', 'year', 'feature_key', 'order'])
        _apply_links(photo, attrs['characters'], attrs['tags'])
    return photo


def remove(photo_id):
    """Удаляет запись и её файлы. Файлы удаляются после успешной транзакции."""
    with transaction.atomic():
        try:
            photo = Photo.objects.select_for_update().get(pk=photo_id)
        except Photo.DoesNotExist:
            raise ValueError(f'Photo {photo_id} does not exist.') from None
        files = list(paths_for(photo).values())
        photo.delete()
    _cleanup(files)


def check():
    """Проверка целостности контура: файлы, привязки, ничейные файлы."""
    problems = []
    known = set()
    features = set(Feature.objects.values_list('key', flat=True))
    for photo in Photo.objects.all():
        for kind, path in paths_for(photo).items():
            known.add(path)
            if not path.is_file():
                problems.append(f'photo {photo.id}: missing {kind} file {path.name}')
        if photo.feature_key and photo.feature_key not in features:
            problems.append(f'photo {photo.id}: feature {photo.feature_key!r} no longer exists in the atlas')
        if photo.year is not None and photo.year not in ALLOWED_YEARS:
            problems.append(f'photo {photo.id}: year {photo.year} is outside the allowed set')
    root = photo_root()
    if root.is_dir():
        for path in sorted(root.rglob('*')):
            if path.is_file() and path not in known:
                problems.append(f'orphan file: {path.relative_to(settings.MEDIA_ROOT)}')
    return problems
