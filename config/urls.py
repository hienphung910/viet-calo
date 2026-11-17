from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from app.controllers.media import protected_media

admin.site.site_header = "VietCalo - Quản trị"
admin.site.site_title = "VietCalo"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("app.urls")),
    re_path(rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.+)$", protected_media, name="media"),
]
