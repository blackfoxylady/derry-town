"""Заглавные фото мест: валидация, хранение файлов и производные размеры.

Отдельный контур данных вне ревизий атласа (см. PlaceCover в models.py),
устроен как фотогалерея (photos.py) и переиспользует её файловые хелперы.
Каталог media/covers — производное хранилище, руками файлы не кладутся.

У места не больше двух заглавных фото и не больше одного на год; год и alt
обязательны. Original сохраняется байт в байт; medium и large — JPEG.
"""
from pathlib import Path
from django.conf import settings
from django.db import transaction
from .models import Feature, PlaceCover
from .photos import ALLOWED_YEARS, _atomic_write, _cleanup, _derivative, _Prepared, check_year

# Максимальная сторона производных, пиксели: medium покрывает мобильные и
# десктопную колонку (~640px), large — retina-экраны.
COVER_MEDIUM_SIZE = 768
COVER_LARGE_SIZE = 1536
MAX_COVERS_PER_PLACE = 2


def cover_root():
    return Path(settings.MEDIA_ROOT) / 'covers'


def relative_paths(sha256, ext):
    return {'original': f'covers/original/{sha256}.{ext}',
            'large': f'covers/large/{sha256}.jpg',
            'medium': f'covers/medium/{sha256}.jpg'}


def paths_for(cover):
    return {k: Path(settings.MEDIA_ROOT) / v for k, v in relative_paths(cover.sha256, cover.ext).items()}


def _check_alt(alt, what='alt'):
    if not isinstance(alt, str):
        raise ValueError(f'Cover {what} must be a string.')
    return alt.strip()


def _check_feature(feature_key):
    feature = Feature.objects.filter(pk=feature_key).first() if feature_key else None
    if feature is None:
        raise ValueError(f'Feature {feature_key!r} does not exist in the atlas.')
    if feature.object_type not in ('site', 'unplaced'):
        raise ValueError(f'Feature {feature_key!r} is {feature.object_type!r}; '
                         'covers belong to places (site or unplaced) only.')
    return feature.key


def _check_slot(feature_key, year, exclude_id=None):
    """Не больше MAX_COVERS_PER_PLACE фото у места и не больше одного на год."""
    others = PlaceCover.objects.filter(feature_key=feature_key)
    if exclude_id is not None:
        others = others.exclude(pk=exclude_id)
    if others.filter(year=year).exists():
        raise ValueError(f'Feature {feature_key!r} already has a cover for {year}.')
    if others.count() >= MAX_COVERS_PER_PLACE:
        raise ValueError(f'Feature {feature_key!r} already has {MAX_COVERS_PER_PLACE} covers.')


def _validated(feature, year, alt, alt_ru):
    if year is None:
        raise ValueError('Cover year is required.')
    alt = _check_alt(alt)
    if not alt:
        raise ValueError('Cover alt text is required.')
    return {'feature_key': _check_feature(feature), 'year': check_year(year),
            'alt': alt, 'alt_ru': _check_alt(alt_ru, 'alt_ru')}


def _write_files(source, created):
    """Пишет оригинал и производные; created собирает новые файлы для отката."""
    targets = {k: Path(settings.MEDIA_ROOT) / v for k, v in relative_paths(source.sha256, source.ext).items()}
    for path in targets.values():
        if not path.exists():
            created.append(path)
    _atomic_write(targets['original'], lambda f: f.write(source.data))
    _derivative(source.image, COVER_LARGE_SIZE, targets['large'])
    _derivative(source.image, COVER_MEDIUM_SIZE, targets['medium'])


def _validated_entry(entry):
    """Нормализует атрибуты одного фото из аргументов команды/манифеста."""
    allowed = {'file', 'feature', 'year', 'alt', 'alt_ru'}
    unknown = set(entry) - allowed
    if unknown:
        raise ValueError(f'Unknown cover fields: {sorted(unknown)}.')
    return _validated(entry.get('feature') or '', entry.get('year'),
                      entry.get('alt', ''), entry.get('alt_ru', ''))


def add_many(entries):
    """Добавляет партию заглавных фото атомарно: все или ни одного.

    entries — список словарей: file (путь) + атрибуты как в манифесте
    (feature, year, alt, alt_ru). Возвращает созданные PlaceCover.
    """
    if not entries:
        raise ValueError('Nothing to import.')
    prepared = []
    for entry in entries:
        if 'file' not in entry:
            raise ValueError('Each cover entry needs a "file".')
        prepared.append((_Prepared(entry['file']), _validated_entry(entry)))
    seen = {}
    for source, attrs in prepared:
        if source.sha256 in seen:
            raise ValueError(f'{source.name} duplicates {seen[source.sha256]} in the same batch.')
        seen[source.sha256] = source.name
    created_files, result = [], []
    try:
        with transaction.atomic():
            for source, attrs in prepared:
                existing = PlaceCover.objects.filter(sha256=source.sha256).first()
                if existing is not None:
                    raise ValueError(f'{source.name} already imported as cover {existing.id} (same content hash).')
                _check_slot(attrs['feature_key'], attrs['year'])
                cover = PlaceCover.objects.create(sha256=source.sha256, ext=source.ext,
                                                  original_name=source.name,
                                                  width=source.width, height=source.height, **attrs)
                _write_files(source, created_files)
                result.append(cover)
    except BaseException:
        _cleanup(created_files)
        raise
    return result


def add(file, feature='', year=None, alt='', alt_ru=''):
    """Добавляет одно заглавное фото места. Возвращает созданный PlaceCover."""
    return add_many([{'file': file, 'feature': feature, 'year': year,
                      'alt': alt, 'alt_ru': alt_ru}])[0]


def edit(cover_id, feature=None, year=None, alt=None, alt_ru=None):
    """Меняет атрибуты заглавного фото; файлы не трогает. None = не менять."""
    with transaction.atomic():
        try:
            cover = PlaceCover.objects.select_for_update().get(pk=cover_id)
        except PlaceCover.DoesNotExist:
            raise ValueError(f'Cover {cover_id} does not exist.') from None
        attrs = _validated(cover.feature_key if feature is None else feature,
                           cover.year if year is None else year,
                           cover.alt if alt is None else alt,
                           cover.alt_ru if alt_ru is None else alt_ru)
        _check_slot(attrs['feature_key'], attrs['year'], exclude_id=cover.id)
        for field, value in attrs.items():
            setattr(cover, field, value)
        cover.save(update_fields=list(attrs))
    return cover


def remove(cover_id):
    """Удаляет запись и её файлы. Файлы удаляются после успешной транзакции."""
    with transaction.atomic():
        try:
            cover = PlaceCover.objects.select_for_update().get(pk=cover_id)
        except PlaceCover.DoesNotExist:
            raise ValueError(f'Cover {cover_id} does not exist.') from None
        files = list(paths_for(cover).values())
        cover.delete()
    _cleanup(files)


def check():
    """Проверка целостности контура: файлы, привязки, ничейные файлы."""
    problems = []
    known = set()
    features = {f.key: f.object_type for f in Feature.objects.only('key', 'object_type')}
    for cover in PlaceCover.objects.all():
        for kind, path in paths_for(cover).items():
            known.add(path)
            if not path.is_file():
                problems.append(f'cover {cover.id}: missing {kind} file {path.name}')
        if cover.feature_key not in features:
            problems.append(f'cover {cover.id}: feature {cover.feature_key!r} no longer exists in the atlas')
        elif features[cover.feature_key] not in ('site', 'unplaced'):
            problems.append(f'cover {cover.id}: feature {cover.feature_key!r} is no longer a place')
        if cover.year not in ALLOWED_YEARS:
            problems.append(f'cover {cover.id}: year {cover.year} is outside the allowed set')
        if not cover.alt.strip():
            problems.append(f'cover {cover.id}: alt text is empty')
    root = cover_root()
    if root.is_dir():
        for path in sorted(root.rglob('*')):
            if path.is_file() and path not in known:
                problems.append(f'orphan file: {path.relative_to(settings.MEDIA_ROOT)}')
    return problems
