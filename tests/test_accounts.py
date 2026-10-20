import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.accounts.models import User

from .conftest import PASSWORD


@pytest.mark.django_db
class TestUserModel:
    def test_email_is_normalized_and_password_hashed(self):
        u = User.objects.create_user(email="Binh@Example.COM", password=PASSWORD)
        assert u.email == "binh@example.com"
        assert u.password != PASSWORD and u.check_password(PASSWORD)
        assert u.daily_calorie_target == 2000

    def test_email_unique(self, user):
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user(email=user.email, password=PASSWORD)

    def test_calorie_target_check_constraint_in_db(self, user):
        # Bỏ qua validator của form, ghi thẳng xuống CSDL -> CHECK constraint phải chặn.
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(daily_calorie_target=100)

    def test_create_superuser(self):
        admin = User.objects.create_superuser(email="admin@example.com", password=PASSWORD)
        assert admin.is_staff and admin.is_superuser


@pytest.mark.django_db
class TestAuthViews:
    def test_register_logs_user_in(self, client):
        resp = client.post(
            reverse("accounts:register"),
            {"email": "moi@example.com", "daily_calorie_target": 1800, "password1": PASSWORD, "password2": PASSWORD},
        )
        assert resp.status_code == 302
        u = User.objects.get(email="moi@example.com")
        assert u.daily_calorie_target == 1800
        assert client.get(reverse("diary:home")).status_code == 200

    def test_register_rejects_target_out_of_range(self, client):
        resp = client.post(
            reverse("accounts:register"),
            {"email": "x@example.com", "daily_calorie_target": 100, "password1": PASSWORD, "password2": PASSWORD},
        )
        assert resp.status_code == 200
        assert not User.objects.filter(email="x@example.com").exists()

    def test_login_with_email(self, client, user):
        resp = client.post(reverse("accounts:login"), {"username": user.email, "password": PASSWORD})
        assert resp.status_code == 302 and resp.url == reverse("diary:home")

    def test_login_wrong_password(self, client, user):
        resp = client.post(reverse("accounts:login"), {"username": user.email, "password": "sai"})
        assert resp.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_home_requires_login(self, client):
        resp = client.get(reverse("diary:home"))
        assert resp.status_code == 302 and reverse("accounts:login") in resp.url

    def test_profile_update(self, client, user):
        client.force_login(user)
        client.post(reverse("accounts:profile"), {"first_name": "An", "daily_calorie_target": 2200})
        user.refresh_from_db()
        assert (user.first_name, user.daily_calorie_target) == ("An", 2200)

    def test_logout_requires_post(self, client, user):
        client.force_login(user)
        assert client.get(reverse("accounts:logout")).status_code == 405
        client.post(reverse("accounts:logout"))
        assert "_auth_user_id" not in client.session
