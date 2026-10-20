from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from .media import protected_media

admin.site.site_header = "VietCalo - Quản trị"
admin.site.site_title = "VietCalo"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.recognition.urls")),
    path("", include("apps.diary.urls")),
    # Ảnh trong media/: luôn đi qua view kiểm tra quyền (cả khi DEBUG=True lẫn False).
    re_path(rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.+)$", protected_media, name="media"),
]
