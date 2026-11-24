from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from app.services import login_guard

WEAK_PASSWORD_KEY = "weak_password"


@receiver(user_login_failed)
def count_failed_login(sender, credentials, request=None, **kwargs):
    login_guard.record_failure(request, credentials.get("username") or credentials.get("email"))


@receiver(user_logged_in)
def after_login(sender, request, user, **kwargs):
    login_guard.reset(request, user.email)
    # GuardedModelBackend gắn cờ này khi mật khẩu vừa nhập không đạt quy tắc; WeakPasswordMiddleware sẽ
    # giữ người dùng ở trang đổi mật khẩu cho tới khi đổi xong
    if getattr(user, "weak_password", False):
        request.session[WEAK_PASSWORD_KEY] = True
