"""数据库 adapter：校验同一事务里的来源/原件，不偷读部署机仓库。"""
def database_context():
    from .models import ResearchArtifact, SourceRecord
    return {'source_ids': set(SourceRecord.objects.exclude(key='__registry__').values_list('key', flat=True)),
            'artifacts': dict(ResearchArtifact.objects.values_list('sha256', 'text'))}
