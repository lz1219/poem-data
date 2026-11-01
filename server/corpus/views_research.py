"""研究区与事实接口隔离。明确 revision 的引用不随最新修订漂移。"""
import re
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import ResearchRevision, SourceRecord
from .research_rules import publishable
from .research_storage import database_context


@api_view(['GET'])
def research_index(request):
    latest = {}
    for row in ResearchRevision.objects.order_by('record_id', 'revision'):
        latest[row.record_id] = row.payload
    keys = ['id', 'revision', 'subject', 'kind', 'status', 'title', 'provenance']
    context = database_context()
    return Response({'schemaVersion': '1.0', 'records': [{k: d[k] for k in keys} for d in latest.values() if publishable(d, **context)]})


@api_view(['GET'])
def research_detail(request, record_id, revision=None):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,119}', record_id):
        return Response({'detail': '未找到记录'}, status=404)
    qs = ResearchRevision.objects.filter(record_id=record_id)
    row = qs.filter(revision=revision).first() if revision else qs.order_by('-revision').first()
    if not row or not publishable(row.payload, **database_context()):
        return Response({'detail': '未找到公开记录'}, status=404)
    return Response(row.payload)


@api_view(['GET'])
def sources(request):
    return Response({'schemaVersion': '1.0', 'sources': [s.payload for s in SourceRecord.objects.exclude(key='__registry__').order_by('key')]})
