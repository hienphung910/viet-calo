"""Giai đoạn 5: thống kê độ chính xác model, xuất ảnh phản hồi, trang admin."""
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.diary.services import create_meal_log
from apps.feedback.models import FeedbackImage
from apps.feedback.services import export_feedback
from apps.foods.models import Food
from apps.recognition import stats
from apps.recognition.models import ModelVersion

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_dirs(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.FEEDBACK_EXPORT_DIR = tmp_path / "raw"
    return tmp_path


@pytest.fixture
def foods(db):
    call_command("seed_foods", verbosity=0)
    return {f.class_label: f for f in Food.objects.all()}


@pytest.fixture
def versions(db):
    mk = lambda v, val, test, days: ModelVersion.objects.create(  # noqa: E731
        version=v, file_path=f"models/{v}/model.pt", class_list=[], val_accuracy=val, test_accuracy=test,
        trained_at=timezone.now() - timezone.timedelta(days=days))
    return mk("v1", 0.90, 0.88, 2), mk("v2", 0.93, 0.91, 1)


def ai_log(user, foods, mv, true, top3):
    """Bữa ăn do AI nhận diện: top3 = [(nhãn, độ tin cậy), ...], `true` = món người dùng xác nhận."""
    return create_meal_log(user=user, food=foods[true], grams=100, meal_type="lunch", model_version_id=mv.pk,
                           top3=[{"label": lbl, "confidence": c} for lbl, c in top3])


@pytest.fixture
def scenario(user, foods, versions):
    v1, v2 = versions
    ai_log(user, foods, v1, "pho", [("pho", 0.9), ("bun_bo_hue", 0.05), ("com_tam", 0.05)])        # đúng
    ai_log(user, foods, v1, "banh_mi", [("pho", 0.7), ("banh_mi", 0.2), ("com_tam", 0.1)])         # sai, có trong top-3
    ai_log(user, foods, v1, "com_tam", [("pho", 0.5), ("banh_mi", 0.3), ("bun_bo_hue", 0.2)])      # sai, ngoài top-3
    ai_log(user, foods, v1, "pho", [("pho", 0.3), ("bun_rieu", 0.3), ("hu_tieu", 0.2)])            # đúng, tin cậy thấp
    ai_log(user, foods, v2, "bun_bo_hue", [("bun_bo_hue", 0.95), ("pho", 0.03), ("bun_rieu", 0.02)])  # đúng
    create_meal_log(user=user, food=foods["xoi_xeo"], grams=200, meal_type="breakfast")           # thủ công: không tính
    return versions


# ---------- Thống kê độ chính xác ----------

class TestModelStats:
    def test_overview(self, scenario):
        o = stats.overview()
        assert (o["n"], o["correct"], o["wrong"]) == (5, 3, 2)
        assert o["top1_acc"] == 0.6 and o["top3_acc"] == 0.8
        assert o["low_rate"] == 0.4  # 0.5 và 0.3 dưới ngưỡng 0.6

    def test_model_comparison(self, scenario):
        rows = {r["mv"].version: r for r in stats.model_comparison()}
        assert (rows["v1"]["n"], rows["v1"]["real_top1"], rows["v1"]["real_top3"]) == (4, 0.5, 0.75)
        assert (rows["v2"]["n"], rows["v2"]["real_top1"], rows["v2"]["real_top3"]) == (1, 1.0, 1.0)
        assert [r["mv"].version for r in stats.model_comparison()] == ["v1", "v2"]  # theo thời gian train

    def test_model_without_usage(self, versions):
        rows = stats.model_comparison()
        assert all(r["n"] == 0 and r["real_top1"] is None for r in rows)

    def test_confidence_buckets(self, scenario):
        b = stats.confidence_buckets()
        assert [x["n"] for x in b] == [0, 1, 1, 1, 2]
        assert [x["acc"] for x in b] == [None, 1.0, 0.0, 0.0, 1.0]
        assert b[3]["label"] == "60%–80%"
        assert [x["n"] for x in stats.confidence_buckets(model_version=scenario[1])] == [0, 0, 0, 0, 1]

    def test_confusions_and_per_food(self, scenario):
        pairs = {(c["predicted_label"], c["food__class_label"]): c["n"] for c in stats.top_confusions()}
        assert pairs == {("pho", "banh_mi"): 1, ("pho", "com_tam"): 1}
        worst = stats.per_food_accuracy()
        assert {w["food__class_label"] for w in worst[:2]} == {"banh_mi", "com_tam"}
        assert worst[-1]["acc"] == 1.0

    def test_popular_foods_all_users(self, scenario, foods):
        other = get_user_model().objects.create_user(email="o@example.com", password="x" * 12)
        create_meal_log(user=other, food=foods["pho"], grams=100, meal_type="lunch")
        top = stats.popular_foods()[0]
        assert (top["food__name_vi"], top["times"], top["users"]) == ("Phở", 3, 2)


# ---------- Xuất ảnh phản hồi ----------

def fb(food, consented=True, used=False, predicted="", with_file=True):
    name = default_storage.save("feedback/x.jpg", ContentFile(b"jpeg-bytes")) if with_file else "feedback/mat.jpg"
    return FeedbackImage.objects.create(true_food=food, image_path=name, predicted_label=predicted,
                                        user_consented=consented, used_in_training=used)


class TestExportFeedback:
    def test_export_copies_and_marks(self, foods, isolated_dirs):
        a = fb(foods["pho"], predicted="pho")
        b = fb(foods["banh_mi"], predicted="pho")
        no_consent = fb(foods["pho"], consented=False)
        already = fb(foods["pho"], used=True)
        r = export_feedback(isolated_dirs / "raw")
        assert dict(r.exported) == {"pho": 1, "banh_mi": 1}
        # Nhãn lấy từ món người dùng xác nhận, không phải nhãn model đoán.
        assert (isolated_dirs / "raw" / "banh_mi" / f"feedback_{b.pk}.jpg").read_bytes() == b"jpeg-bytes"
        assert (isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg").exists()
        assert set(FeedbackImage.objects.filter(used_in_training=True).values_list("pk", flat=True)) == {
            a.pk, b.pk, already.pk}
        no_consent.refresh_from_db()
        assert not no_consent.used_in_training
        assert export_feedback(isolated_dirs / "raw").total == 0  # chạy lại: không xuất lần hai

    def test_dry_run_changes_nothing(self, foods, isolated_dirs):
        fb(foods["pho"])
        r = export_feedback(isolated_dirs / "raw", dry_run=True)
        assert r.total == 1 and not (isolated_dirs / "raw").exists()
        assert not FeedbackImage.objects.filter(used_in_training=True).exists()

    def test_only_corrected(self, foods, isolated_dirs):
        fb(foods["pho"], predicted="pho")
        wrong = fb(foods["banh_mi"], predicted="pho")
        r = export_feedback(isolated_dirs / "raw", only_corrected=True)
        assert dict(r.exported) == {"banh_mi": 1}
        assert list(FeedbackImage.objects.filter(used_in_training=True).values_list("pk", flat=True)) == [wrong.pk]

    def test_missing_file_and_inactive_food(self, foods, isolated_dirs):
        lost = fb(foods["pho"], with_file=False)
        Food.objects.filter(class_label="com_tam").update(is_active=False)
        fb(Food.objects.get(class_label="com_tam"))
        r = export_feedback(isolated_dirs / "raw")
        assert r.total == 0 and r.missing == [lost.pk] and r.skipped_inactive == 1

    def test_command(self, foods, isolated_dirs):
        fb(foods["pho"])
        out = io.StringIO()
        call_command("export_feedback", stdout=out)
        assert "Đã xuất 1 ảnh" in out.getvalue()
        assert len(list((isolated_dirs / "raw" / "pho").iterdir())) == 1


# ---------- Trang thống kê + admin ----------

@pytest.fixture
def admin_client(client, db):
    client.force_login(get_user_model().objects.create_superuser(email="admin@example.com", password="x" * 12))
    return client


class TestAdminPages:
    def test_stats_page_staff_only(self, client, user, scenario):
        client.force_login(user)
        assert client.get(reverse("recognition:stats")).status_code == 302

    def test_stats_page(self, admin_client, scenario):
        resp = admin_client.get(reverse("recognition:stats"))
        assert resp.status_code == 200
        assert resp.context["chart"]["real_top1"] == [50.0, 100.0]
        assert resp.context["overview"]["n"] == 5

    @pytest.mark.parametrize("name", [
        "accounts_user", "foods_food", "recognition_modelversion", "diary_meallog", "feedback_feedbackimage",
    ])
    def test_changelists_render(self, admin_client, scenario, foods, name):
        fb(foods["pho"], predicted="bun_bo_hue")
        assert admin_client.get(reverse(f"admin:{name}_changelist")).status_code == 200

    def test_feedback_filter_wrong(self, admin_client, foods):
        fb(foods["pho"], predicted="pho")
        wrong = fb(foods["banh_mi"], predicted="pho")
        resp = admin_client.get(reverse("admin:feedback_feedbackimage_changelist"), {"prediction": "wrong"})
        assert [o.pk for o in resp.context["cl"].result_list] == [wrong.pk]

    def test_feedback_actions(self, admin_client, foods, isolated_dirs):
        a, b = fb(foods["pho"]), fb(foods["banh_mi"])
        url = reverse("admin:feedback_feedbackimage_changelist")
        admin_client.post(url, {"action": "export_selected", "_selected_action": [a.pk]})
        a.refresh_from_db()
        assert a.used_in_training and (isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg").exists()
        admin_client.post(url, {"action": "exclude_from_training", "_selected_action": [a.pk, b.pk]})
        assert not FeedbackImage.objects.filter(user_consented=True).exists()

    def test_exclude_removes_exported_file(self, admin_client, foods, isolated_dirs):
        a = fb(foods["pho"])
        export_feedback(isolated_dirs / "raw")
        exported = isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg"
        assert exported.exists()
        admin_client.post(reverse("admin:feedback_feedbackimage_changelist"),
                          {"action": "exclude_from_training", "_selected_action": [a.pk]})
        assert not exported.exists()  # không còn bị train ở lần prepare_data sau

    def test_relabel_exported_image_in_list(self, admin_client, foods, isolated_dirs):
        a = fb(foods["pho"], predicted="pho")
        export_feedback(isolated_dirs / "raw")
        old_file = isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg"
        # Sửa nhãn ngay trong danh sách (list_editable).
        resp = admin_client.post(reverse("admin:feedback_feedbackimage_changelist"), {
            "form-TOTAL_FORMS": 1, "form-INITIAL_FORMS": 1, "form-0-id": a.pk,
            "form-0-true_food": foods["banh_mi"].pk, "_save": "Lưu lại",
        })
        assert resp.status_code == 302
        a.refresh_from_db()
        assert a.true_food == foods["banh_mi"] and not a.used_in_training and not old_file.exists()
        export_feedback(isolated_dirs / "raw")  # xuất lại -> vào đúng thư mục nhãn mới
        assert (isolated_dirs / "raw" / "banh_mi" / f"feedback_{a.pk}.jpg").exists()

    def test_delete_removes_exported_file(self, admin_client, foods, isolated_dirs):
        a = fb(foods["pho"])
        export_feedback(isolated_dirs / "raw")
        admin_client.post(reverse("admin:feedback_feedbackimage_changelist"),
                          {"action": "delete_selected", "_selected_action": [a.pk], "post": "yes"})
        assert not FeedbackImage.objects.exists()
        assert not (isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg").exists()

    def test_activate_action(self, admin_client, versions, monkeypatch):
        from apps.recognition import admin as rec_admin

        reloaded = []
        monkeypatch.setattr(rec_admin, "get_service", lambda: type("S", (), {"reload": lambda s: reloaded.append(1)})())
        v1, v2 = versions
        admin_client.post(reverse("admin:recognition_modelversion_changelist"),
                          {"action": "activate_selected", "_selected_action": [v2.pk]})
        v2.refresh_from_db()
        assert v2.is_active and reloaded == [1]

    def test_seed_button(self, admin_client):
        resp = admin_client.post(reverse("admin:foods_food_seed"))
        assert resp.status_code == 302 and Food.objects.count() == 30

    def test_reload_with_next_redirects(self, admin_client, db):
        resp = admin_client.post(reverse("recognition:reload"), {"next": "/recognition/stats/"})
        assert resp.status_code == 302 and resp.url == "/recognition/stats/"  # chưa có model -> báo lỗi rồi quay lại
        bad = admin_client.post(reverse("recognition:reload"), {"next": "https://evil.example.com/"})
        assert bad.status_code == 503  # next trỏ ra ngoài bị bỏ qua -> trả JSON
