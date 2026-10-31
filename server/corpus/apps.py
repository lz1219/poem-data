from django.apps import AppConfig


class CorpusConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "corpus"
    verbose_name = "文献"

    def ready(self):
        # 语料库连接池（56,968 首诗 / 1,301 卷原文所在的 PostgreSQL）
        from . import db

        db.init_pool()