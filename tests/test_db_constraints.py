"""Kiểm tra các ràng buộc toàn vẹn ở tầng CSDL (khóa ngoại, CHECK, UNIQUE)."""
from datetime import datetime, timezone as dt_timezone

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.diary.models import MealLog
from apps.feedback.models import FeedbackImage
from apps.recognition.models import ModelVersion

pytestmark = pytest.mark.django_db


def make_log(user, food, **kw):
    data = {"portion_g": 600, "kcal": 540, **kw}
    return MealLog.objects.create(user=user, food=food, **data)


class TestModelVersion:
    def test_only_one_active_model(self, make_model_version):
        make_model_version("v1", is_active=True)
        make_model_version("v2")  # nhiều dòng không active thì được
        make_model_version("v3")
        with pytest.raises(IntegrityError), transaction.atomic():
            make_model_version("v4", is_active=True)

    def test_activate_switches_active_model(self, make_model_version):
        v1 = make_model_version("v1", is_active=True)
        v2 = make_model_version("v2")
        v2.activate()
        assert list(ModelVersion.objects.filter(is_active=True)) == [v2]
        v1.refresh_from_db()
        assert v1.is_active is False


class TestMealLog:
    def test_eaten_date_uses_vietnam_timezone(self, user, pho):
        # 20:00 UTC ngày 18/10 = 03:00 sáng 19/10 giờ VN.
        log = make_log(user, pho, eaten_at=datetime(2026, 10, 18, 20, 0, tzinfo=dt_timezone.utc))
        assert str(log.eaten_date) == "2026-10-19"

    def test_cannot_delete_food_used_in_log(self, user, pho):
        make_log(user, pho)
        with pytest.raises(ProtectedError):
            pho.delete()

    def test_deleting_user_cascades_logs(self, user, pho):
        make_log(user, pho)
        user.delete()
        assert MealLog.objects.count() == 0

    def test_deleting_model_version_keeps_logs(self, user, pho, make_model_version):
        mv = make_model_version("v1")
        log = make_log(user, pho, model_version=mv)
        mv.delete()
        log.refresh_from_db()
        assert log.model_version is None

    @pytest.mark.parametrize("field, value", [("portion_g", 0), ("kcal", -5), ("confidence", 1.5)])
    def test_check_constraints(self, user, pho, field, value):
        with pytest.raises(IntegrityError), transaction.atomic():
            make_log(user, pho, **{field: value})


class TestFeedbackImage:
    def test_training_requires_consent(self, pho):
        with pytest.raises(IntegrityError), transaction.atomic():
            FeedbackImage.objects.create(
                true_food=pho, image_path="feedback/x.jpg", user_consented=False, used_in_training=True
            )

    def test_feedback_survives_meal_log_deletion(self, user, pho):
        log = make_log(user, pho, predicted_label="bun_bo_hue", was_corrected=True)
        fb = FeedbackImage.objects.create(
            meal_log=log, true_food=pho, image_path="feedback/x.jpg", predicted_label="bun_bo_hue"
        )
        log.delete()
        fb.refresh_from_db()
        assert fb.meal_log is None and fb.was_wrong
