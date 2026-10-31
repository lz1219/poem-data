from django.urls import path

from . import views

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
]
