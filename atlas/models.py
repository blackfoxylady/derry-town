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
    paragraph = models.PositiveIntegerField(null=True, blank=True)
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
