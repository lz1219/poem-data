from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('corpus', '0006_stop_kind')]
    operations = [
        migrations.AddField(model_name='work', name='place_key', field=models.CharField(blank=True, max_length=120, verbose_name='作地标识')),
        migrations.AddField(model_name='apparatus', name='stable_id', field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name='commentary', name='stable_id', field=models.CharField(blank=True, max_length=80)),
        migrations.CreateModel(name='SourceRecord', fields=[('key', models.CharField(max_length=100, primary_key=True, serialize=False)), ('payload', models.JSONField(default=dict))], options={'verbose_name': '资料来源', 'verbose_name_plural': '资料来源'}),
        migrations.CreateModel(name='ResearchRevision', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('record_id', models.CharField(max_length=120)), ('revision', models.PositiveIntegerField()), ('payload', models.JSONField(default=dict))], options={'verbose_name': '研究修订', 'verbose_name_plural': '研究修订', 'ordering': ['record_id', 'revision'], 'constraints': [models.UniqueConstraint(fields=('record_id', 'revision'), name='research_unique_revision')]}),
    ]
