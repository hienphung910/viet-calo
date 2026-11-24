from django.shortcuts import redirect
from django.urls import reverse

from app.signals import WEAK_PASSWORD_KEY


class WeakPasswordMiddleware:
    """Tài khoản đăng nhập bằng mật khẩu yếu chỉ vào được trang đổi mật khẩu (và đăng xuất) cho tới khi đổi xong."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get(WEAK_PASSWORD_KEY) and request.user.is_authenticated:
            allowed = (reverse("accounts:password_change"), reverse("accounts:logout"))
            if request.path not in allowed:
                return redirect("accounts:password_change")
        return self.get_response(request)
