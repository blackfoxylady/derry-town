from django.db import migrations, models
import django.db.models.deletion

# Точки лица (доли снимка) и зум для фильтра галереи, подобраны по снимкам (K7).
# Привязка по содержимому фото: на свежей установке без этих фото ничего не задаётся.
AVATARS = {
    'ben-hanscom': ('4ab92e0e1c29fd8efe496259e88ffd9ccc9623c92b357199e9b9697d6957c91b', 0.5, 0.15, 5.0),
    'beverly-marsh': ('db9871246a4ad77d1216f439ca7c143f0ac8bb2c7b74006e821b77894961943e', 0.35, 0.27, 10.0),
    'bill-denbrough': ('f7f2b173363153f3bfba7668e2159fe3003160af40ca36c95ce6eb42b61e1676', 0.49, 0.1, 4.5),
    'eddie-kaspbrak': ('0e0703380180f22ca9500dd91a780d4bab49486106bcfad490db707507a84afb', 0.21, 0.36, 8.5),
    'mike-hanlon': ('2bf2d3d56b461c867fcdf8e7b960fb7066ccb62fd93c1d7ff0c737e66174a508', 0.334, 0.2, 11.0),
    'richie-tozier': ('f12b7108d1d16dfb2a70be27208c7d8a218a627944b93144428aebaf5bc2131f', 0.366, 0.256, 6.5),
    'stan-uris': ('a0cce1f0a41adf686ff80fac6e2438341b3144ebee6f31971c68b15784cd0a56', 0.246, 0.41, 8.0),
    'pennywise': ('8937b088b7ec95f6592fdcb0865370c55e8be518fefdeeb0c1af9955d3a656f6', 0.527, 0.368, 9.0),
}


def seed_avatars(apps, schema_editor):
    Character = apps.get_model('atlas', 'Character')
    Photo = apps.get_model('atlas', 'Photo')
    for slug, (sha256, x, y, zoom) in AVATARS.items():
        photo = Photo.objects.filter(sha256=sha256).first()
        if photo is not None:
            Character.objects.filter(slug=slug, avatar__isnull=True).update(
                avatar=photo, avatar_x=x, avatar_y=y, avatar_zoom=zoom)


class Migration(migrations.Migration):

    dependencies = [
        ('atlas', '0009_photo_placecover_modified'),
    ]

    operations = [
        migrations.AddField(
            model_name='character',
            name='avatar',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='+', to='atlas.photo'),
        ),
        migrations.AddField(
            model_name='character',
            name='avatar_x',
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name='character',
            name='avatar_y',
            field=models.FloatField(default=0.3),
        ),
        migrations.AddField(
            model_name='character',
            name='avatar_zoom',
            field=models.FloatField(default=3.0),
        ),
        migrations.RunPython(seed_avatars, migrations.RunPython.noop),
    ]
