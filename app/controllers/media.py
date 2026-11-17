from pathlib import PurePosixPath

from django.conf import settings
from django.http import Http404
from django.views.static import serve

from app.models import MealLog


def _can_view(request, path: str) -> bool:
    user = request.user
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    if path.startswith("uploads/"):
        pending = request.session.get("pending_scans", {}).values()
        if any(p.get("image") == path for p in pending):
            return True
        return MealLog.objects.filter(user=user, image_path=path).exists()
    return False


# ảnh trong media/ chỉ chủ ảnh hoặc admin mới xem được
def protected_media(request, path):
    if ".." in PurePosixPath(path.replace("\\", "/")).parts or not _can_view(request, path):
        raise Http404
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response["Cache-Control"] = "private, max-age=3600"
    return response
