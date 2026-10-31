"""
江山行止 · 文献 后端（Django）

环境变量
  DJANGO_DEBUG      1/0，默认 1
  DJANGO_SECRET     生产必填
  DATA_DIR          策展数据目录（导入用），默认 ../data
  PUBLIC_DIR        前端目录，默认 ..
  DATABASE_URL      PostgreSQL 连接串；不设则用本地 SQLite
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = Path(os.getenv("PUBLIC_DIR") or BASE_DIR.parent)
DATA_DIR = Path(os.getenv("DATA_DIR") or (REPO_DIR / "data"))

SECRET_KEY = os.getenv("DJANGO_SECRET", "dev-only-insecure-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corpus",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "atlas.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(REPO_DIR)],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "atlas.wsgi.application"

_db_url = os.getenv("DATABASE_URL", "")
if _db_url.startswith("postgres"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "jiangshan",
            "USER": os.getenv("PGUSER", "lz9527"),
            "PASSWORD": os.getenv("PGPASSWORD", ""),
            "HOST": os.getenv("PGHOST", "127.0.0.1"),
            "PORT": os.getenv("PGPORT", "5432"),
            "OPTIONS": {"connect_timeout": 5},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": None,
    "UNAUTHENTICATED_USER": None,
}

# 后台外观（django-unfold）
UNFOLD = {
    "SITE_TITLE": "江山行止 · 文献",
    "SITE_HEADER": "江山行止 · 文献",
    "SITE_SUBHEADER": "每条叙述带出处",
    "SITE_URL": "/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "ENVIRONMENT": None,
    "COLORS": {
        "primary": {
            "50": "250 247 240",
            "100": "243 238 228",
            "200": "229 220 202",
            "300": "214 200 174",
            "400": "196 176 142",
            "500": "176 141 90",
            "600": "157 124 76",
            "700": "132 103 62",
            "800": "106 82 49",
            "900": "80 62 37",
            "950": "48 37 22",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "文献",
                "separator": True,
                "items": [
                    {"title": "作品", "icon": "menu_book", "link": "/admin/corpus/work/"},
                    {"title": "人物", "icon": "person", "link": "/admin/corpus/person/"},
                    {"title": "行迹", "icon": "route", "link": "/admin/corpus/journey/"},
                ],
            },
            {
                "title": "考据",
                "separator": True,
                "items": [
                    {"title": "校记", "icon": "difference", "link": "/admin/corpus/apparatus/"},
                    {"title": "历代评点", "icon": "comment", "link": "/admin/corpus/commentary/"},
                    {"title": "系年考辨", "icon": "history", "link": "/admin/corpus/dating/"},
                    {"title": "版本", "icon": "book", "link": "/admin/corpus/edition/"},
                ],
            },
            {
                "title": "行迹细节",
                "separator": True,
                "items": [
                    {"title": "站点", "icon": "place", "link": "/admin/corpus/stop/"},
                    {"title": "承接语", "icon": "arrow_forward", "link": "/admin/corpus/journeylink/"},
                ],
            },
            {
                "title": "系统",
                "separator": True,
                "items": [
                    {"title": "用户", "icon": "people", "link": "/admin/auth/user/"},
                    {"title": "组", "icon": "group", "link": "/admin/auth/group/"},
                ],
            },
        ],
    },
}

ADMIN_SITE_HEADER = "江山行止 · 文献"
