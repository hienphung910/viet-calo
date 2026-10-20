import io
import os
import time

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from apps.diary.services import create_meal_log
from apps.feedback.models import FeedbackImage

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


def save(name, age_hours=48):
    path = default_storage.save(name, ContentFile(b"img"))
    old = time.time() - age_hours * 3600
    os.utime(default_storage.path(path), (old, old))
    return path


def test_cleanup_removes_only_old_orphans(user, pho, media):
    used = save("uploads/2026/10/used.jpg")
    create_meal_log(user=user, food=pho, grams=600, meal_type="lunch", image_path=used)
    fb_used = save("feedback/2026/10/fb.jpg")
    FeedbackImage.objects.create(true_food=pho, image_path=fb_used)
    orphan_old = save("uploads/2026/09/old.jpg")
    orphan_new = save("uploads/2026/10/new.jpg", age_hours=1)  # có thể đang ở trang xác nhận
    fb_orphan = save("feedback/2026/10/lost.jpg")

    out = io.StringIO()
    call_command("cleanup_uploads", "--dry-run", stdout=out)
    assert "Sẽ xóa (dry-run) 2 ảnh" in out.getvalue() and default_storage.exists(orphan_old)

    call_command("cleanup_uploads", stdout=io.StringIO())
    assert not default_storage.exists(orphan_old) and not default_storage.exists(fb_orphan)
    assert default_storage.exists(used) and default_storage.exists(fb_used) and default_storage.exists(orphan_new)
    assert not (media / "uploads" / "2026" / "09").exists()  # thư mục rỗng được dọn


def test_cleanup_without_media_folder():
    out = io.StringIO()
    call_command("cleanup_uploads", stdout=out)
    assert "Đã xóa 0 ảnh" in out.getvalue()
