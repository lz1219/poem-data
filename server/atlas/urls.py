"""路由：/admin 后台，/api 只读接口，/ 静态前端。"""
import os
from pathlib import Path

from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from corpus import views_atlas

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = Path(os.getenv("PUBLIC_DIR") or BASE_DIR.parent)

urlpatterns = [
    path('research.html', serve, {'path': 'web/research.html', 'document_root': str(REPO_DIR)}),
    path("admin/", admin.site.urls),
    path("api/", include("corpus.urls")),
    # 江山行止（静态站点）挂到 /atlas/，与本站同源
    path("atlas", views_atlas.atlas_index),
    re_path(r"^atlas/(?P<path>.*)$", views_atlas.atlas_file),
    # 前端首页（web/）；静态数据仍在仓库根，故 /data/*.json 由下面的 catch-all 提供
    path("", serve, {"path": "web/index.html", "document_root": str(REPO_DIR)}),
    # 静态资源与 data/*.json
    re_path(r"^(?P<path>.*)$", serve, {"document_root": str(REPO_DIR)}),
]
