import pytest
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from app.models import User

from .conftest import PASSWORD


@pytest.mark.django_db
class TestUserModel:
    def test_email_is_normalized_and_password_hashed(self):
        u = User.objects.create_user(email="Binh@Example.COM", password=PASSWORD)
        assert u.email == "binh@example.com"
        assert u.password != PASSWORD and u.check_password(PASSWORD)

    def test_email_unique(self, user):
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user(email=user.email, password=PASSWORD)

    def test_create_superuser(self):
        admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        assert admin.is_staff and admin.is_superuser


@pytest.mark.django_db
class TestAuthViews:
    def test_register_logs_user_in(self, client):
        resp = client.post(
            reverse("accounts:register"),
            {"email": "moi@example.com", "password1": PASSWORD, "password2": PASSWORD},
        )
        assert resp.status_code == 302
        assert User.objects.filter(email="moi@example.com").exists()
        assert client.get(reverse("diary:home")).status_code == 200

    def test_login_with_email(self, client, user):
        resp = client.post(reverse("accounts:login"), {"username": user.email, "password": PASSWORD})
        assert resp.status_code == 302 and resp.url == reverse("diary:home")

    def test_login_wrong_password(self, client, user):
        resp = client.post(reverse("accounts:login"), {"username": user.email, "password": "sai"})
        assert resp.status_code == 200
        assert "_auth_user_id" not in client.session

    @pytest.mark.parametrize("weak", ["abc12", "12345678", "password", "yeu@example.com"])
    def test_register_rejects_weak_password(self, client, weak):
        resp = client.post(reverse("accounts:register"),
                           {"email": "yeu@example.com", "password1": weak, "password2": weak})
        assert resp.status_code == 200 and resp.context["form"].errors
        assert not User.objects.exists()

    def test_register_page_hides_password_rules_but_still_reports_errors(self, client):
        form = client.get(reverse("accounts:register")).context["form"]
        assert form.fields["password1"].help_text == ""
        resp = client.post(reverse("accounts:register"),
                           {"email": "yeu@example.com", "password1": "abc12", "password2": "abc12"})
        assert "8" in str(resp.context["form"].errors)  # vẫn báo "ít nhất 8 ký tự"

    def test_register_and_login_ignore_email_case(self, client):
        data = {"email": "Hoa@Example.COM", "password1": PASSWORD, "password2": PASSWORD}
        assert client.post(reverse("accounts:register"), data).status_code == 302
        assert User.objects.get().email == "hoa@example.com"

        other = Client()
        resp = other.post(reverse("accounts:login"), {"username": "HOA@example.com", "password": PASSWORD})
        assert resp.status_code == 302
        # không tạo được tài khoản thứ hai chỉ khác chữ hoa/thường
        resp = Client().post(reverse("accounts:register"), {**data, "email": "hoa@EXAMPLE.com"})
        assert resp.status_code == 200 and "email" in resp.context["form"].errors
        assert User.objects.count() == 1

    def test_home_requires_login(self, client):
        resp = client.get(reverse("diary:home"))
        assert resp.status_code == 302 and reverse("accounts:login") in resp.url

    def test_logout_requires_post(self, client, user):
        client.force_login(user)
        assert client.get(reverse("accounts:logout")).status_code == 405
        client.post(reverse("accounts:logout"))
        assert "_auth_user_id" not in client.session
