"""
Phục vụ file trong media/ CÓ KIỂM TRA QUYỀN (chạy cả khi DEBUG=False, ví dụ lúc demo bằng waitress).

Ảnh món ăn là dữ liệu cá nhân, nên không cho ai biết URL cũng xem được:
  - admin (is_staff): xem mọi ảnh (để duyệt ảnh phản hồi);
  - người dùng: chỉ xem ảnh bữa ăn của chính mình, hoặc ảnh vừa tải lên còn trong phiên (trang xác nhận);
  - còn lại: 404 (không tiết lộ là file có tồn tại).
Ở môi trường production thật, việc gửi file nên giao cho web server (nginx X-Accel-Redirect...),
còn Django chỉ kiểm tra quyền như ở đây.
"""
from pathlib import PurePosixPath

from django.conf import settings
from django.http import Http404
from django.views.static import serve

from apps.diary.models import MealLog


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
    return False  # feedback/ và thư mục khác: chỉ admin


def protected_media(request, path):
    # Chặn sớm đường dẫn thoát khỏi media/ (../); serve() cũng chặn nhưng trả 400 kèm log lỗi bảo mật.
    if ".." in PurePosixPath(path.replace("\\", "/")).parts or not _can_view(request, path):
        raise Http404
    response = serve(request, path, document_root=settings.MEDIA_ROOT)
    response["Cache-Control"] = "private, max-age=3600"  # không cho proxy dùng chung lưu cache
    return response
