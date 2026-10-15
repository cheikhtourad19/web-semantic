from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "backoffice"
urlpatterns = [
    path("connexion/", views.StaffLoginView.as_view(), name="login"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("<str:kind>/", views.entity_list, name="list"),
    path("<str:kind>/nouveau/", views.entity_edit, name="create"),
    path("<str:kind>/<slug:identifier>/", views.entity_detail, name="detail"),
    path("<str:kind>/<slug:identifier>/modifier/", views.entity_edit, name="edit"),
    path("<str:kind>/<slug:identifier>/supprimer/", views.entity_delete, name="delete"),
    path("ressources/<slug:identifier>/fichier/", views.resource_file, name="file"),
]
