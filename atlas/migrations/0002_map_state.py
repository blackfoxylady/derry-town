from django.db import migrations


def initialize_state(apps, schema_editor):
    apps.get_model('atlas', 'MapState').objects.get_or_create(id=1)


class Migration(migrations.Migration):
    dependencies = [('atlas', '0001_initial')]
    operations = [migrations.RunPython(initialize_state, migrations.RunPython.noop)]
