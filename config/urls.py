from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("backoffice/", include("apps.backoffice.urls")),
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Administration Web Semantic"
admin.site.site_title = "Web Semantic"
admin.site.index_title = "Administration"

