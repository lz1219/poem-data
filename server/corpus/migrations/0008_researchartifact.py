from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('corpus', '0007_research')]
    operations = [migrations.CreateModel(name='ResearchArtifact', fields=[
        ('sha256', models.CharField(max_length=64, primary_key=True, serialize=False)),
        ('text', models.TextField()),
    ])]
