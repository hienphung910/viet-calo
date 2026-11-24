"""Chặn dò mật khẩu: đếm số lần đăng nhập sai trong cache, quá ngưỡng thì khoá tạm.

Có 3 bộ đếm, cùng hết hạn sau settings.LOGIN_LOCK_SECONDS kể từ lần sai đầu tiên:
  - ip_email: một IP dò một tài khoản (ngưỡng thấp nhất, đây là trường hợp thường gặp)
  - ip:       một IP thử nhiều tài khoản khác nhau
  - email:    nhiều IP cùng dò một tài khoản. Ngưỡng đặt cao vì bộ đếm này khoá cả chủ tài khoản,
              kẻ xấu có thể lợi dụng để không cho người khác đăng nhập.
"""
import hashlib

from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    if request is None:
        return ""
    # Sau proxy của Railway, REMOTE_ADDR là địa chỉ của proxy; IP thật của khách nằm trong header X-Real-IP.
    # Chỉ đọc header này khi chạy trên Railway, vì ở nơi khác khách tự gửi header đó được.
    if settings.RAILWAY_PUBLIC_DOMAIN:
        ip = request.META.get("HTTP_X_REAL_IP", "").strip()
        if ip:
            return ip
    return request.META.get("REMOTE_ADDR", "")


def _keys(request, email) -> dict[str, str]:
    ip = client_ip(request)
    email = (email or "").strip().lower()
    raw = {"ip_email": f"{ip}|{email}", "ip": ip, "email": email}
    # băm để khoá cache không chứa ký tự lạ và không dài quá giới hạn của backend cache
    return {name: f"login-fail:{name}:{hashlib.sha256(value.encode()).hexdigest()}" for name, value in raw.items()}


def is_blocked(request, email) -> bool:
    keys = _keys(request, email)
    return any(cache.get(keys[name], 0) >= limit for name, limit in settings.LOGIN_LIMITS.items())


def record_failure(request, email) -> None:
    for key in _keys(request, email).values():
        if cache.add(key, 1, timeout=settings.LOGIN_LOCK_SECONDS):
            continue
        try:
            cache.incr(key)  # incr giữ nguyên thời điểm hết hạn, nên khoá tự mở sau LOGIN_LOCK_SECONDS
        except ValueError:  # khoá vừa hết hạn giữa hai lệnh
            cache.set(key, 1, timeout=settings.LOGIN_LOCK_SECONDS)


def reset(request, email) -> None:
    # Không xoá bộ đếm theo IP: nếu xoá, kẻ dò mật khẩu chỉ cần đăng nhập vào tài khoản của chính mình
    # xen giữa các lần thử để đếm lại từ đầu.
    keys = _keys(request, email)
    cache.delete_many([keys["ip_email"], keys["email"]])
