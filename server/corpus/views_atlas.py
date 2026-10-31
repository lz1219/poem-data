"""托管江山行止（纯静态站点）到 /atlas/ 子路径。

为什么不用 nginx/caddy：目标只是把两个站点放在同一来源下，少一个组件。
站点约 27 MB，绝大多数是懒加载的地形图与疆域快照；gunicorn 直接发文件
在个人站点规模下够用，且加了长缓存头，重复访问不会重复传输。

路径全部是相对引用（js/…、css/…、assets/…），所以必须保证 URL 以 /atlas/ 结尾，
否则相对路径会解析到根目录。
"""
import mimetypes
import os
from pathlib import Path

from django.http import FileResponse, Http404, HttpResponseRedirect
from django.views.decorators.cache import cache_control

ATLAS_DIR = Path(os.getenv("ATLAS_DIR") or "")


def _resolve(rel: str) -> Path:
    base = ATLAS_DIR.resolve()
    target = (base / rel).resolve()
    if base != target and base not in target.parents:
        raise Http404("路径越界")
    return target


@cache_control(public=True, max_age=300)
def atlas_index(request):
    """访问 /atlas 时补一个斜杠，否则相对资源会解析错。"""
    return HttpResponseRedirect("/atlas/")


def atlas_file(request, path=""):
    if not ATLAS_DIR or not ATLAS_DIR.exists():
        raise Http404("未配置江山行止目录（ATLAS_DIR）")

    if not path or path.endswith("/"):
        path = (path or "") + "index.html"

    f = _resolve(path)
    if not f.is_file():
        raise Http404(f"未找到 {path}")

    ctype, _ = mimetypes.guess_type(str(f))
    resp = FileResponse(open(f, "rb"), content_type=ctype or "application/octet-stream")

    # 带 ?v= 版本戳的资源长缓存；其余短缓存
    if "v=" in (request.META.get("QUERY_STRING") or ""):
        resp["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        resp["Cache-Control"] = "public, max-age=300"
    resp["X-Atlas-File"] = path
    return resp
