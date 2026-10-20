"""Ảnh trong media/ chỉ người có quyền mới xem được (kể cả khi DEBUG=False)."""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.diary.services import create_meal_log

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DEBUG = False


@pytest.fixture
def meal_image(user, pho):
    name = default_storage.save("uploads/2026/10/a.jpg", ContentFile(b"jpeg"))
    create_meal_log(user=user, food=pho, grams=600, meal_type="lunch", image_path=name)
    return name


def make_user(email, **kw):
    return get_user_model().objects.create_user(email=email, password="x" * 12, **kw)


def test_owner_can_view(client, user, meal_image):
    client.force_login(user)
    resp = client.get(f"/media/{meal_image}")
    assert resp.status_code == 200 and b"".join(resp.streaming_content) == b"jpeg"
    assert "private" in resp["Cache-Control"]


def test_anonymous_and_other_user_get_404(client, meal_image):
    assert client.get(f"/media/{meal_image}").status_code == 404
    client.force_login(make_user("b@example.com"))
    assert client.get(f"/media/{meal_image}").status_code == 404


def test_staff_can_view_feedback(client, user):
    name = default_storage.save("feedback/2026/10/f.jpg", ContentFile(b"fb"))
    client.force_login(user)
    assert client.get(f"/media/{name}").status_code == 404  # người dùng thường không xem ảnh feedback
    client.force_login(make_user("admin@example.com", is_staff=True))
    assert client.get(f"/media/{name}").status_code == 200


def test_pending_scan_image_visible_to_uploader(client, user):
    name = default_storage.save("uploads/2026/10/p.jpg", ContentFile(b"p"))
    client.force_login(user)
    session = client.session
    session["pending_scans"] = {"tok": {"image": name}}
    session.save()
    assert client.get(f"/media/{name}").status_code == 200


def test_path_traversal_blocked(client):
    client.force_login(make_user("admin@example.com", is_staff=True))
    assert client.get("/media/../manage.py").status_code == 404
    assert client.get("/media/uploads/%2e%2e/%2e%2e/manage.py").status_code == 404


def test_custom_404_page(client, user):
    client.force_login(user)
    resp = client.get("/khong-ton-tai/")
    assert resp.status_code == 404 and "Không tìm thấy trang" in resp.content.decode()
