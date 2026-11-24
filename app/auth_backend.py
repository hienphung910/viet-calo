from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError

from app.services import login_guard


class GuardedModelBackend(ModelBackend):
    """Đăng nhập bằng email + mật khẩu như mặc định, thêm hai việc cho MỌI form đăng nhập (kể cả /admin):

    1. Từ chối khi đã sai quá nhiều lần (xem login_guard), kể cả lúc mật khẩu đúng.
    2. Đánh dấu tài khoản có mật khẩu không đạt quy tắc hiện tại. Đây là chỗ duy nhất còn thấy mật khẩu gốc
       (CSDL chỉ lưu mã băm), nên tài khoản tạo trước khi có quy tắc chỉ phát hiện được ở đây.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if login_guard.is_blocked(request, username):
            raise PermissionDenied  # dừng luôn, Django không thử backend nào khác
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is not None and password is not None:
            try:
                validate_password(password, user)
            except ValidationError:
                user.weak_password = True
        return user
