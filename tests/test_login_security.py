import time

import pytest
from django.test import Client
from django.urls import reverse

from app.models import User
from app.services import login_guard
from app.signals import WEAK_PASSWORD_KEY

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def attempt(client, email, password, ip="10.0.0.1", url="accounts:login"):
    return client.post(reverse(url), {"username": email, "password": password}, REMOTE_ADDR=ip)


def logged_in(client) -> bool:
    return "_auth_user_id" in client.session


class TestLoginLimit:
    def test_blocks_after_too_many_failures_even_with_right_password(self, client, user, settings):
        for _ in range(settings.LOGIN_LIMITS["ip_email"]):
            assert attempt(client, user.email, "sai-mat-khau").status_code == 200
        resp = attempt(client, user.email, PASSWORD)
        assert resp.status_code == 200 and "quá nhiều lần" in resp.content.decode()
        assert not logged_in(client)

    def test_other_ip_and_other_account_are_not_blocked(self, client, user, settings):
        other = User.objects.create_user(email="khac@example.com", password=PASSWORD)
        for _ in range(settings.LOGIN_LIMITS["ip_email"]):
            attempt(client, user.email, "sai-mat-khau")
        assert attempt(Client(), user.email, PASSWORD, ip="10.0.0.2").status_code == 302  # chủ tài khoản ở IP khác
        assert attempt(Client(), other.email, PASSWORD).status_code == 302  # tài khoản khác, cùng IP
        assert not logged_in(client) and attempt(client, user.email, PASSWORD).status_code == 200  # IP cũ vẫn bị khoá

    def test_success_resets_counter(self, user, settings):
        for _ in range(2):
            for _ in range(settings.LOGIN_LIMITS["ip_email"] - 1):
                attempt(Client(), user.email, "sai-mat-khau")
            assert attempt(Client(), user.email, PASSWORD).status_code == 302

    def test_lock_expires(self, client, user, settings, monkeypatch):
        for _ in range(settings.LOGIN_LIMITS["ip_email"]):
            attempt(client, user.email, "sai-mat-khau")
        assert attempt(client, user.email, PASSWORD).status_code == 200
        # tua đồng hồ tới sau khi hết thời gian khoá (không chờ thật 15 phút)
        later = time.time() + settings.LOGIN_LOCK_SECONDS + 1
        monkeypatch.setattr(time, "time", lambda: later)
        assert attempt(client, user.email, PASSWORD).status_code == 302

    def test_one_ip_trying_many_accounts_is_blocked(self, client, user, settings):
        settings.LOGIN_LIMITS = {"ip_email": 5, "ip": 3, "email": 20}
        for i in range(3):
            attempt(client, f"nguoi{i}@example.com", "sai-mat-khau")
        assert attempt(client, user.email, PASSWORD).status_code == 200 and not logged_in(client)

    def test_many_ips_on_one_account_are_blocked(self, user, settings):
        settings.LOGIN_LIMITS = {"ip_email": 5, "ip": 30, "email": 3}
        for i in range(3):
            attempt(Client(), user.email, "sai-mat-khau", ip=f"10.0.1.{i}")
        client = Client()
        assert attempt(client, user.email, PASSWORD, ip="10.0.9.9").status_code == 200 and not logged_in(client)

    def test_admin_login_form_is_limited_too(self, client, settings):
        admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        for _ in range(settings.LOGIN_LIMITS["ip_email"]):
            attempt(client, admin.email, "sai-mat-khau", url="admin:login")
        assert attempt(client, admin.email, PASSWORD, url="admin:login").status_code == 200
        assert not logged_in(client)
        # chưa quá ngưỡng thì form admin vẫn đăng nhập bình thường
        other_ip = Client()
        assert attempt(other_ip, admin.email, PASSWORD, ip="10.0.0.2", url="admin:login").status_code == 302

    def test_real_ip_header_is_only_trusted_on_railway(self, rf, settings):
        request = rf.get("/", HTTP_X_REAL_IP="1.2.3.4", REMOTE_ADDR="10.0.0.9")
        settings.RAILWAY_PUBLIC_DOMAIN = ""
        assert login_guard.client_ip(request) == "10.0.0.9"
        settings.RAILWAY_PUBLIC_DOMAIN = "ten-app.up.railway.app"
        assert login_guard.client_ip(request) == "1.2.3.4"


class TestWeakExistingPassword:
    CHANGE = "accounts:password_change"

    def test_weak_password_must_be_changed_before_using_the_site(self, client):
        # tài khoản tạo từ trước khi có quy tắc mật khẩu
        User.objects.create_user(email="yeu@example.com", password="123456")
        assert attempt(client, "yeu@example.com", "123456").status_code == 302 and logged_in(client)

        for name in ("diary:home", "diary:week", "recognition:upload", "admin:index"):
            resp = client.get(reverse(name))
            assert resp.status_code == 302 and resp.url == reverse(self.CHANGE)
        page = client.get(reverse(self.CHANGE))
        assert page.status_code == 200 and "quá yếu" in page.content.decode()

        # mật khẩu mới cũng phải đạt quy tắc
        weak = {"old_password": "123456", "new_password1": "654321", "new_password2": "654321"}
        assert client.post(reverse(self.CHANGE), weak).status_code == 200
        good = {"old_password": "123456", "new_password1": PASSWORD, "new_password2": PASSWORD}
        assert client.post(reverse(self.CHANGE), good).status_code == 302
        assert client.get(reverse("diary:home")).status_code == 200  # vẫn đăng nhập, không còn bị giữ lại
        assert User.objects.get().check_password(PASSWORD)

    def test_weak_admin_password_is_caught_on_admin_login(self, client):
        User.objects.create_superuser(email="admin@example.com", password="admin123")
        assert attempt(client, "admin@example.com", "admin123", url="admin:login").status_code == 302
        resp = client.get(reverse("admin:index"))
        assert resp.status_code == 302 and resp.url == reverse(self.CHANGE)

    def test_can_still_log_out(self, client):
        User.objects.create_user(email="yeu@example.com", password="123456")
        attempt(client, "yeu@example.com", "123456")
        client.post(reverse("accounts:logout"))
        assert not logged_in(client)

    def test_strong_password_is_not_interrupted(self, client, user):
        attempt(client, user.email, PASSWORD)
        assert WEAK_PASSWORD_KEY not in client.session
        assert client.get(reverse("diary:home")).status_code == 200
        assert client.get(reverse(self.CHANGE)).status_code == 200  # tự đổi mật khẩu khi muốn

    def test_password_change_requires_login(self, client):
        resp = client.get(reverse(self.CHANGE))
        assert resp.status_code == 302 and reverse("accounts:login") in resp.url
