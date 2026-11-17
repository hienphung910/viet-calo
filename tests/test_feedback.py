import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from app.services.meal_log import create_meal_log
from app.models import FeedbackImage
from app.services.feedback import export_feedback
from app.models import Food
from app.models import ModelVersion
from ml.common import ROOT, read_nutrition_labels

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


@pytest.fixture
def scenario(user, foods, versions):
    v1, _ = versions
    create_meal_log(user=user, food=foods["pho"], grams=100, meal_type="lunch", model_version_id=v1.pk,
                    predicted_label="pho")
    create_meal_log(user=user, food=foods["xoi_xeo"], grams=200, meal_type="breakfast")
    return versions


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
        assert (isolated_dirs / "raw" / "banh_mi" / f"feedback_{b.pk}.jpg").read_bytes() == b"jpeg-bytes"
        assert (isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg").exists()
        assert set(FeedbackImage.objects.filter(used_in_training=True).values_list("pk", flat=True)) == {
            a.pk, b.pk, already.pk}
        no_consent.refresh_from_db()
        assert not no_consent.used_in_training
        assert export_feedback(isolated_dirs / "raw").total == 0

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


@pytest.fixture
def admin_client(client, db):
    client.force_login(get_user_model().objects.create_superuser(email="admin@example.com", password="x" * 12))
    return client


class TestAdminPages:
    @pytest.mark.parametrize("name", [
        "app_user", "app_food", "app_modelversion", "app_meallog", "app_feedbackimage",
    ])
    def test_changelists_render(self, admin_client, scenario, foods, name):
        fb(foods["pho"], predicted="bun_bo_hue")
        assert admin_client.get(reverse(f"admin:{name}_changelist")).status_code == 200

    def test_feedback_filter_wrong(self, admin_client, foods):
        fb(foods["pho"], predicted="pho")
        wrong = fb(foods["banh_mi"], predicted="pho")
        resp = admin_client.get(reverse("admin:app_feedbackimage_changelist"), {"prediction": "wrong"})
        assert [o.pk for o in resp.context["cl"].result_list] == [wrong.pk]

    def test_feedback_actions(self, admin_client, foods, isolated_dirs):
        a, b = fb(foods["pho"]), fb(foods["banh_mi"])
        url = reverse("admin:app_feedbackimage_changelist")
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
        admin_client.post(reverse("admin:app_feedbackimage_changelist"),
                          {"action": "exclude_from_training", "_selected_action": [a.pk]})
        assert not exported.exists()

    def test_relabel_exported_image_in_list(self, admin_client, foods, isolated_dirs):
        a = fb(foods["pho"], predicted="pho")
        export_feedback(isolated_dirs / "raw")
        old_file = isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg"
        resp = admin_client.post(reverse("admin:app_feedbackimage_changelist"), {
            "form-TOTAL_FORMS": 1, "form-INITIAL_FORMS": 1, "form-0-id": a.pk,
            "form-0-true_food": foods["banh_mi"].pk, "_save": "Lưu lại",
        })
        assert resp.status_code == 302
        a.refresh_from_db()
        assert a.true_food == foods["banh_mi"] and not a.used_in_training and not old_file.exists()
        export_feedback(isolated_dirs / "raw")
        assert (isolated_dirs / "raw" / "banh_mi" / f"feedback_{a.pk}.jpg").exists()

    def test_delete_removes_exported_file(self, admin_client, foods, isolated_dirs):
        a = fb(foods["pho"])
        export_feedback(isolated_dirs / "raw")
        admin_client.post(reverse("admin:app_feedbackimage_changelist"),
                          {"action": "delete_selected", "_selected_action": [a.pk], "post": "yes"})
        assert not FeedbackImage.objects.exists()
        assert not (isolated_dirs / "raw" / "pho" / f"feedback_{a.pk}.jpg").exists()

    def test_activate_action(self, admin_client, versions, monkeypatch):
        from app.admin import recognition as rec_admin

        reloaded = []
        monkeypatch.setattr(rec_admin, "get_service", lambda: type("S", (), {"reload": lambda s: reloaded.append(1)})())
        v1, v2 = versions
        admin_client.post(reverse("admin:app_modelversion_changelist"),
                          {"action": "activate_selected", "_selected_action": [v2.pk]})
        v2.refresh_from_db()
        assert v2.is_active and reloaded == [1]

    def test_seed_button(self, admin_client):
        resp = admin_client.post(reverse("admin:app_food_seed"))
        assert resp.status_code == 302 and Food.objects.count() == len(read_nutrition_labels(ROOT / "data" / "nutrition.csv"))

    def test_reload_with_next_redirects(self, admin_client, db):
        resp = admin_client.post(reverse("recognition:reload"), {"next": "/admin/app/modelversion/"})
        assert resp.status_code == 302 and resp.url == "/admin/app/modelversion/"
        bad = admin_client.post(reverse("recognition:reload"), {"next": "https://evil.example.com/"})
        assert bad.status_code == 503
