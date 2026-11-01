from django.urls import path

from . import views, views_corpus

urlpatterns = [
    path("health", views.health),
    path("meta", views.meta),
    path("index", views.index),
    path("works", views.works),
    path("works/<str:key>", views.work_detail),
    path("persons", views.persons),
    path("persons/<str:key>", views.person_detail),
    path("journeys", views.journeys),
    path("journeys/<str:key>", views.journey_detail),
    path("comments/<str:work_key>", views.comments),
    path("search", views.search),
    # 语料层
    path("corpus/authors", views_corpus.authors),
    path("corpus/authors/<str:name>", views_corpus.author_detail),
    path("corpus/poems/<int:poem_id>", views_corpus.poem_detail),
    path("persons/<str:key>/career", views_corpus.person_career),
    path("persons/<str:key>/timeline", views_corpus.person_timeline),
    path("persons/<str:key>/relations", views_corpus.person_relations),
    path("works/<str:key>/corpus", views_corpus.work_corpus_text),
    path("texts", views_corpus.texts),
    path("texts/<int:book_id>", views_corpus.book_detail),
    path("texts/juan/<int:unit_id>", views_corpus.juan_detail),
]
