from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.urls import reverse

from app.services import diary_stats as stats
from app.forms.diary import initial_portion
from app.models import MealLog
from app.services.meal_log import create_meal_log
from app.models import FeedbackImage
from app.models import Food

VN = ZoneInfo("Asia/Ho_Chi_Minh")
MON = date(2026, 10, 12)


def at(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=VN)


@pytest.fixture
def foods(db):
    call_command("seed_foods", verbosity=0)
    return {f.class_label: f for f in Food.objects.all()}


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


def log(user, food, grams=None, when=None, meal_type="lunch", **kw):
    return create_meal_log(user=user, food=food, grams=grams or food.default_portion_g, meal_type=meal_type,
                           eaten_at=when or at(MON, 12), **kw)


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(email="other@example.com", password="x" * 12)


class TestStats:
    def test_day_summary(self, user, foods, other_user):
        log(user, foods["pho"])
        log(user, foods["banh_mi"], when=at(MON, 7))
        log(other_user, foods["com_tam"])
        s = stats.day_summary(user, MON)
        assert s["totals"]["kcal"] == 1060 and s["totals"]["count"] == 2
        assert [x.food.class_label for x in s["logs"]] == ["banh_mi", "pho"]

    def test_day_boundary_uses_vietnam_time(self, user, foods):
        log(user, foods["pho"], when=at(MON, 23, 30))
        log(user, foods["pho"], when=at(MON, 0, 30))
        assert stats.day_summary(user, MON)["totals"]["count"] == 2

    def test_daily_series_fills_empty_days(self, user, foods):
        log(user, foods["pho"], when=at(MON, 12))
        log(user, foods["pho"], when=at(date(2026, 10, 14), 12), grams=300)
        log(user, foods["pho"], when=at(date(2026, 10, 19), 12))
        series = stats.daily_series(user, MON)
        assert [d["date"].day for d in series] == [12, 13, 14, 15, 16, 17, 18]
        assert [d["kcal"] for d in series] == [540, 0, 270, 0, 0, 0, 0]

    def test_period_summary(self, user, foods):
        log(user, foods["pho"], when=at(MON, 12), grams=1100)
        log(user, foods["pho"], when=at(date(2026, 10, 13), 12), grams=1500)
        ps = stats.period_summary(user, MON)
        assert ps["total"]["kcal"] == 2340 and ps["days_logged"] == 2
        assert ps["avg_kcal"] == 1170
        assert ps["meal_count"] == 2

    def test_top_foods(self, user, foods):
        for _ in range(3):
            log(user, foods["pho"])
        log(user, foods["banh_mi"]), log(user, foods["banh_mi"])
        log(user, foods["com_tam"])
        top = stats.top_foods(user, MON, MON)
        assert [(t["food__name_vi"], t["times"]) for t in top] == [("Phở", 3), ("Bánh mì", 2), ("Cơm tấm", 1)]

    def test_meal_type_breakdown(self, user, foods):
        log(user, foods["banh_mi"], meal_type="breakfast")
        log(user, foods["pho"], meal_type="dinner")
        rows = {r["meal_type"]: r["kcal"] for r in stats.meal_type_breakdown(user, MON, MON)}
        assert rows == {"breakfast": 520, "lunch": 0, "dinner": 540, "snack": 0}

    def test_week_start(self):
        assert stats.week_start(date(2026, 10, 18)) == MON


def test_initial_portion(db, foods):
    pho = foods["pho"]
    assert initial_portion(pho, 600) == {"portion_choice": "medium", "portion_g": None}
    assert initial_portion(pho, 420) == {"portion_choice": "small", "portion_g": None}
    assert initial_portion(pho, 555) == {"portion_choice": "custom", "portion_g": 555}


@pytest.mark.django_db
class TestPages:
    def test_day_page(self, client, user, foods, other_user):
        log(user, foods["pho"])
        log(other_user, foods["banh_mi"])
        client.force_login(user)
        resp = client.get(reverse("diary:home"), {"date": "2026-10-12"})
        html = resp.content.decode()
        assert resp.status_code == 200 and "Phở" in html and "Bánh mì" not in html
        assert resp.context["totals"]["kcal"] == 540

    def test_invalid_date_falls_back_to_today(self, client, user):
        client.force_login(user)
        assert client.get(reverse("diary:home"), {"date": "khong-phai-ngay"}).context["is_today"]

    def test_week_page(self, client, user, foods):
        log(user, foods["pho"], when=at(date(2026, 10, 15), 12))
        client.force_login(user)
        resp = client.get(reverse("diary:week"), {"start": "2026-10-15"})
        assert resp.context["start"] == MON
        chart = resp.context["chart"]
        assert chart["kcal"] == [0, 0, 0, 540, 0, 0, 0] and chart["labels"][0] == "T2 12/10"
        assert resp.context["top_foods"][0]["food__name_vi"] == "Phở"
        assert "chart.js" in resp.content.decode()

    def test_pages_require_login(self, client):
        for name in ("diary:home", "diary:week", "diary:meal_add"):
            assert client.get(reverse(name)).status_code == 302


@pytest.mark.django_db
class TestEditDelete:
    def test_manual_add(self, client, user, foods):
        client.force_login(user)
        resp = client.post(reverse("diary:meal_add"), {
            "food": foods["com_tam"].pk, "portion_choice": "large", "meal_type": "dinner",
            "eaten_at": "2026-10-12T19:30",
        })
        m = MealLog.objects.get()
        assert resp.status_code == 302 and resp.url.endswith("?date=2026-10-12")
        assert m.portion_g == 585 and m.kcal == 1111.5 and m.eaten_date == MON
        assert m.predicted_label == "" and m.model_version is None

    def test_edit_recomputes_nutrition(self, client, user, foods):
        m = log(user, foods["pho"], predicted_label="pho", image_path="uploads/a.jpg")
        fb = FeedbackImage.objects.create(meal_log=m, true_food=foods["pho"], image_path="feedback/a.jpg",
                                          predicted_label="pho")
        client.force_login(user)
        client.post(reverse("diary:meal_edit", args=[m.pk]), {
            "food": foods["bun_bo_hue"].pk, "portion_choice": "custom", "portion_g": 500, "meal_type": "lunch",
            "eaten_at": "2026-10-13T12:00",
        })
        m.refresh_from_db()
        fb.refresh_from_db()
        assert m.food == foods["bun_bo_hue"] and m.kcal == 500 and m.protein_g == 35
        assert m.eaten_date == date(2026, 10, 13)
        assert fb.true_food == foods["bun_bo_hue"]

    def test_edit_keeps_feedback_used_in_training(self, client, user, foods):
        m = log(user, foods["pho"], predicted_label="pho")
        fb = FeedbackImage.objects.create(meal_log=m, true_food=foods["pho"], image_path="feedback/a.jpg",
                                          used_in_training=True)
        client.force_login(user)
        client.post(reverse("diary:meal_edit", args=[m.pk]), {
            "food": foods["com_tam"].pk, "portion_choice": "medium", "meal_type": "lunch",
            "eaten_at": "2026-10-12T12:00",
        })
        fb.refresh_from_db()
        assert fb.true_food == foods["pho"]

    def test_edit_form_initial(self, client, user, foods):
        m = log(user, foods["pho"], grams=420)
        client.force_login(user)
        form = client.get(reverse("diary:meal_edit", args=[m.pk])).context["form"]
        assert form["portion_choice"].value() == "small" and form["food"].value() == foods["pho"].pk

    def test_delete_removes_log_and_image_keeps_feedback(self, client, user, foods, django_capture_on_commit_callbacks):
        name = default_storage.save("uploads/x.jpg", ContentFile(b"img"))
        m = log(user, foods["pho"], image_path=name)
        fb = FeedbackImage.objects.create(meal_log=m, true_food=foods["pho"], image_path="feedback/x.jpg")
        client.force_login(user)
        assert client.get(reverse("diary:meal_delete", args=[m.pk])).status_code == 200
        with django_capture_on_commit_callbacks(execute=True):
            resp = client.post(reverse("diary:meal_delete", args=[m.pk]))
        assert resp.status_code == 302 and not MealLog.objects.exists()
        assert not default_storage.exists(name)
        fb.refresh_from_db()
        assert fb.meal_log is None

    def test_cannot_touch_other_users_meal(self, client, user, foods, other_user):
        m = log(other_user, foods["pho"])
        client.force_login(user)
        assert client.get(reverse("diary:meal_edit", args=[m.pk])).status_code == 404
        assert client.post(reverse("diary:meal_delete", args=[m.pk])).status_code == 404
        assert MealLog.objects.filter(pk=m.pk).exists()
