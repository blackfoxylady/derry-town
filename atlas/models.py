from django.db import models
from django.db.models import Q


class Setting(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField()


class Geometry(models.Model):
    """Local metres; never EPSG:4326. A shape is stored once, reused by components."""
    key = models.CharField(max_length=100, primary_key=True)
    shape = models.JSONField()


class Feature(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    object_type = models.CharField(max_length=20)
    name = models.CharField(max_length=300, blank=True)
    short = models.CharField(max_length=150, blank=True)
    kind = models.CharField(max_length=40, blank=True)
    confidence = models.CharField(max_length=1, blank=True)
    rank = models.PositiveSmallIntegerField(default=3)
    period = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)
    geometry = models.ForeignKey(Geometry, null=True, blank=True, on_delete=models.PROTECT)
    metadata = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(rank__gte=1, rank__lte=3), name='feature_rank_1_3'),
            models.CheckConstraint(condition=Q(confidence__in=['', 'A', 'B', 'C', 'U']), name='feature_confidence'),
            models.CheckConstraint(condition=(Q(object_type='unplaced', geometry__isnull=True, confidence='U') |
                (~Q(object_type='unplaced') & Q(geometry__isnull=False))), name='feature_geometry_presence'),
        ]


class Style(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField()


class Component(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    feature = models.ForeignKey(Feature, null=True, blank=True, on_delete=models.CASCADE)
    geometry = models.ForeignKey(Geometry, null=True, blank=True, on_delete=models.PROTECT)
    style = models.ForeignKey(Style, on_delete=models.PROTECT)
    z = models.PositiveIntegerField()
    recipe = models.JSONField(default=dict)

    class Meta:
        ordering = ['z', 'key']


class Label(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    feature = models.ForeignKey(Feature, null=True, blank=True, on_delete=models.CASCADE)
    text = models.CharField(max_length=300, blank=True)
    dx = models.FloatField(default=0)
    dy = models.FloatField(default=0)
    spec = models.JSONField(default=dict)


class Source(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    title = models.CharField(max_length=500)
    kind = models.CharField(max_length=20)
    url = models.URLField(max_length=2000, blank=True)
    role = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)


class Evidence(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.PROTECT)
    reference = models.TextField()
    note = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)


class MapView(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    title = models.CharField(max_length=150)
    subtitle = models.CharField(max_length=300)
    scale = models.PositiveIntegerField()
    bounds = models.JSONField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(scale__gt=0), name='positive_map_scale')]


class Revision(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    author = models.CharField(max_length=150)
    reason = models.TextField()
    before = models.JSONField()
    after = models.JSONField()
    digest = models.CharField(max_length=64)


class MapState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    initialized = models.BooleanField(default=False)
    revision = models.ForeignKey(Revision, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name='singleton_map_state')]


class Character(models.Model):
    """Справочник персонажей для фотографий; пополняется командой photos."""
    slug = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=150)


class Tag(models.Model):
    slug = models.CharField(max_length=100, primary_key=True)


class PlaceCover(models.Model):
    """Заглавные фото страниц мест — контур вне ревизий атласа, как Photo.

    Привязка к месту строковым ключом (см. Photo о причинах). У места ноль,
    одно или два фото разных лет; год и alt обязательны, alt_ru — перевод
    с откатом на английский. Файлы живут в media/covers/, отдельно от
    фотогалереи, и в её выдачах (галерея, карта, sitemap) не участвуют.
    """
    sha256 = models.CharField(max_length=64, unique=True)
    ext = models.CharField(max_length=8)
    original_name = models.CharField(max_length=255)
    feature_key = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    alt = models.TextField()
    alt_ru = models.TextField(blank=True, default='')
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['feature_key', 'year']
        constraints = [
            models.UniqueConstraint(fields=['feature_key', 'year'], name='cover_unique_feature_year'),
            models.CheckConstraint(condition=Q(year__gte=1850, year__lte=2100), name='cover_year_range'),
            models.CheckConstraint(condition=~Q(feature_key=''), name='cover_feature_required'),
            models.CheckConstraint(condition=~Q(alt=''), name='cover_alt_required'),
        ]


class Photo(models.Model):
    """Фотографии — отдельный контур вне ревизий атласа.

    Привязка к месту хранится строковым ключом, а не FK: commit() атласа
    полностью заменяет строки feature (replace_tables), и FK-каскад стирал бы
    привязки при каждой правке карты. Целостность ключа проверяют photos.py
    при записи и `photos check` после правок атласа.
    """
    sha256 = models.CharField(max_length=64, unique=True)
    ext = models.CharField(max_length=8)
    original_name = models.CharField(max_length=255)
    caption = models.TextField(blank=True)
    caption_ru = models.TextField(blank=True, default='')
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    feature_key = models.CharField(max_length=100, blank=True, default='')
    order = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)
    characters = models.ManyToManyField(Character, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.CheckConstraint(condition=Q(year__isnull=True) | Q(year__gte=1850, year__lte=2100),
                                   name='photo_year_range'),
        ]
