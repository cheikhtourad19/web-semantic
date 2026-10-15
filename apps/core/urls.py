from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("catalogue/", views.catalogue_list, name="catalogue"),
    path("catalogue/<str:kind>/", views.catalogue_list, name="list"),
    path("catalogue/<str:kind>/<str:identifier>/", views.entity_detail, name="detail"),
    path("explorer/sparql/", views.sparql_lab, name="sparql"),
    path("recherche/", views.intelligent_search, name="search"),
    path("ressources/<str:identifier>/fichier/", views.resource_file, name="resource-file"),
    path("health/", views.health, name="health"),
]
