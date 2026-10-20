"""
Test luồng nhận diện bằng model GIẢ (trả xác suất cố định) -> kết quả xác định trước,
không cần file .pt thật, chạy nhanh.
"""
import io
import math

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from PIL import Image

torch = pytest.importorskip("torch")

from apps.diary.models import MealLog  # noqa: E402
from apps.feedback.models import FeedbackImage  # noqa: E402
from apps.recognition import services  # noqa: E402
from apps.recognition.models import ModelVersion  # noqa: E402
from apps.recognition.services import ModelLoadError, NoActiveModel, PredictionService  # noqa: E402

# Xác suất model giả trả về, theo tên file model.
PROBS = {
    "confident.pt": {"pho": 0.90, "bun_bo_hue": 0.06, "com_tam": 0.04},
    "unsure.pt": {"pho": 0.45, "bun_bo_hue": 0.35, "com_tam": 0.20},
    "v2.pt": {"pho": 0.10, "bun_bo_hue": 0.20, "com_tam": 0.70},
}


class FakeModel(torch.nn.Module):
    def __init__(self, probs: list[float]):
        super().__init__()
        self.logits = torch.nn.Parameter(torch.log(torch.tensor(probs)), requires_grad=False)

    def forward(self, x):
        return self.logits.expand(x.shape[0], -1)


def fake_loader(path, device):
    probs = PROBS[path.name]
    return FakeModel(list(probs.values())), {"class_list": list(probs), "img_size": 32}


def jpeg_bytes(size=(64, 48), exif=None) -> bytes:
    buf = io.BytesIO()
    kwargs = {"exif": exif} if exif else {}
    Image.new("RGB", size, (200, 120, 50)).save(buf, "JPEG", **kwargs)
    return buf.getvalue()


def upload(name="mon.jpg", data=None):
    return SimpleUploadedFile(name, data or jpeg_bytes(), content_type="image/jpeg")


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def foods(db):
    call_command("seed_foods", verbosity=0)


@pytest.fixture
def make_mv(tmp_path, foods):
    def _make(filename, version=None, active=True):
        f = tmp_path / filename
        f.write_bytes(b"fake")
        mv = ModelVersion.objects.create(
            version=version or filename, file_path=str(f), class_list=list(PROBS[filename]),
            trained_at=timezone.now(),
        )
        if active:
            mv.activate()
        return mv
    return _make


@pytest.fixture
def service(monkeypatch):
    svc = PredictionService(loader=fake_loader, check_interval=0)
    monkeypatch.setattr(services, "_service", svc)
    return svc


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client


def image():
    return Image.new("RGB", (50, 50))


# ---------- PredictionService ----------

class TestPredictionService:
    def test_no_active_model(self, db, service):
        with pytest.raises(NoActiveModel):
            service.predict(image())

    def test_missing_file(self, foods, service):
        ModelVersion.objects.create(version="x", file_path="khong/ton/tai.pt", trained_at=timezone.now(),
                                    is_active=True)
        with pytest.raises(ModelLoadError):
            service.predict(image())

    def test_top3_sorted_with_foods(self, make_mv, service):
        make_mv("confident.pt")
        r = service.predict(image())
        assert [c.label for c in r.candidates] == ["pho", "bun_bo_hue", "com_tam"]
        assert math.isclose(r.top1.confidence, 0.90, abs_tol=1e-5)
        assert r.top1.food.name_vi == "Phở"
        assert r.is_confident

    def test_threshold(self, make_mv, service, settings):
        make_mv("unsure.pt")
        assert not service.predict(image()).is_confident
        settings.CONFIDENCE_THRESHOLD = 0.4
        assert service.predict(image()).is_confident

    def test_hot_reload_when_active_model_changes(self, make_mv, service):
        make_mv("confident.pt")
        assert service.predict(image()).top1.label == "pho"
        make_mv("v2.pt")  # admin kích hoạt model khác
        r = service.predict(image())
        assert r.model_version == "v2.pt" and r.top1.label == "com_tam"

    def test_check_interval_caches_model(self, make_mv, monkeypatch):
        svc = PredictionService(loader=fake_loader, check_interval=3600)
        make_mv("confident.pt")
        assert svc.predict(image()).model_version == "confident.pt"
        make_mv("v2.pt")
        assert svc.predict(image()).model_version == "confident.pt"  # chưa tới lúc kiểm tra lại
        assert svc.reload().version == "v2.pt"                      # reload ép nạp ngay


# ---------- Trang upload + xác nhận ----------

@pytest.mark.django_db
class TestScanFlow:
    def scan(self, client, data=None):
        return client.post(reverse("recognition:upload"), {"image": upload(data=data)})

    def test_requires_login(self, client):
        assert client.get(reverse("recognition:upload")).status_code == 302

    def test_rejects_non_image(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        resp = logged_client.post(reverse("recognition:upload"),
                                  {"image": SimpleUploadedFile("a.jpg", b"khong phai anh", "image/jpeg")})
        assert resp.status_code == 200 and resp.context["form"].errors

    def test_no_model_shows_error(self, logged_client, foods, service):
        resp = self.scan(logged_client)
        assert resp.status_code == 200
        assert "Chưa nhận diện được" in resp.content.decode()

    def test_upload_saves_image_without_exif(self, logged_client, make_mv, service, media):
        make_mv("confident.pt")
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # Make
        resp = self.scan(logged_client, jpeg_bytes(exif=exif))
        assert resp.status_code == 302
        pending = next(iter(logged_client.session["pending_scans"].values()))
        saved = media / pending["image"]
        assert saved.exists() and pending["image"].startswith("uploads/")
        assert not Image.open(saved).getexif()  # metadata đã bị loại bỏ

    def test_confident_result_preselects_top1(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        page = logged_client.get(self.scan(logged_client).url)
        html = page.content.decode()
        assert "Nhận diện được" in html
        pho_id = page.context["candidates"][0]["food"].pk
        assert page.context["form"]["choice"].value() == str(pho_id)

    def test_unsure_result_asks_user(self, logged_client, make_mv, service):
        make_mv("unsure.pt")
        page = logged_client.get(self.scan(logged_client).url)
        assert "Model chưa chắc chắn" in page.content.decode()
        assert page.context["form"]["choice"].value() == ""

    def test_confirm_top1_saves_log_and_feedback(self, logged_client, user, make_mv, service, media):
        mv = make_mv("confident.pt")
        url = self.scan(logged_client).url
        pho = MealLog._meta.get_field("food").related_model.objects.get(class_label="pho")
        resp = logged_client.post(url, {"choice": pho.pk, "portion_choice": "medium", "meal_type": "lunch",
                                        "consent": "on"})
        assert resp.status_code == 302
        log = MealLog.objects.get()
        assert (log.user, log.food, log.portion_g, log.kcal) == (user, pho, 600, 540)
        assert (log.protein_g, log.carb_g, log.fat_g) == (36, 72, 12)
        assert log.model_version == mv and log.predicted_label == "pho" and not log.was_corrected
        assert [p["label"] for p in log.top3_predictions] == ["pho", "bun_bo_hue", "com_tam"]
        fb = FeedbackImage.objects.get()
        assert fb.true_food == pho and fb.meal_log == log and fb.image_path.name != log.image_path.name
        assert (media / fb.image_path.name).exists()
        assert logged_client.get(url).status_code == 404  # kết quả tạm đã được xóa khỏi session

    def test_correct_label_with_custom_grams_no_consent(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        url = self.scan(logged_client).url
        Food = MealLog._meta.get_field("food").related_model
        banh_mi = Food.objects.get(class_label="banh_mi")  # không nằm trong top-3
        logged_client.post(url, {"choice": "other", "other_food": banh_mi.pk, "portion_choice": "custom",
                                 "portion_g": 150, "meal_type": "breakfast"})
        log = MealLog.objects.get()
        assert log.food == banh_mi and log.portion_g == 150 and log.kcal == 390  # 260 * 1.5
        assert log.was_corrected and log.predicted_label == "pho"
        assert not FeedbackImage.objects.exists()

    def test_small_portion_uses_multiplier(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        url = self.scan(logged_client).url
        com_tam = MealLog._meta.get_field("food").related_model.objects.get(class_label="com_tam")
        logged_client.post(url, {"choice": com_tam.pk, "portion_choice": "small", "meal_type": "dinner"})
        log = MealLog.objects.get()
        assert log.portion_g == 315 and log.was_corrected  # 450 * 0.7, chọn top-3 nhưng không phải top-1

    @pytest.mark.parametrize("data, field", [
        ({"choice": "999999", "portion_choice": "medium", "meal_type": "lunch"}, "choice"),
        ({"choice": "other", "portion_choice": "medium", "meal_type": "lunch"}, "other_food"),
        ({"choice": "other", "other_food": "", "portion_choice": "custom", "meal_type": "lunch"}, "other_food"),
    ])
    def test_invalid_confirm(self, logged_client, make_mv, service, data, field):
        make_mv("confident.pt")
        resp = logged_client.post(self.scan(logged_client).url, data)
        assert resp.status_code == 200 and field in resp.context["form"].errors
        assert not MealLog.objects.exists()

    def test_unknown_token(self, logged_client):
        assert logged_client.get(reverse("recognition:confirm", args=["khongco"])).status_code == 404

    def test_other_user_cannot_see_pending(self, logged_client, make_mv, service):
        from django.test import Client

        make_mv("confident.pt")
        url = self.scan(logged_client).url
        other = Client()
        other.force_login(get_user_model().objects.create_user(email="b@example.com", password="x" * 12))
        assert other.get(url).status_code == 404  # kết quả nằm trong session của người upload


# ---------- API + reload ----------

@pytest.mark.django_db
class TestApi:
    def test_api_predict(self, logged_client, make_mv, service):
        make_mv("unsure.pt")
        data = logged_client.post(reverse("recognition:api_predict"), {"image": upload()}).json()
        assert data["is_confident"] is False
        assert [p["label"] for p in data["predictions"]] == ["pho", "bun_bo_hue", "com_tam"]
        assert data["predictions"][0]["name_vi"] == "Phở"
        assert not MealLog.objects.exists()

    def test_api_preview_does_not_save_image(self, logged_client, make_mv, service, media):
        make_mv("confident.pt")
        for _ in range(3):  # camera gửi nhiều khung hình liên tục
            data = logged_client.post(reverse("recognition:api_predict") + "?preview=1", {"image": upload()}).json()
            assert data["image"] is None and data["predictions"][0]["label"] == "pho"
        assert not (media / "uploads").exists()

    def test_upload_page_has_camera(self, logged_client, settings):
        settings.CONFIDENCE_THRESHOLD = 0.7
        resp = logged_client.get(reverse("recognition:upload"))
        html = resp.content.decode()
        assert 'id="cam-video"' in html and "getUserMedia" in html and "?preview=1" in html
        assert '<script id="threshold" type="application/json">0.7</script>' in html

    def test_api_requires_post(self, logged_client):
        assert logged_client.get(reverse("recognition:api_predict")).status_code == 405

    def test_reload_staff_only(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        assert logged_client.post(reverse("recognition:reload")).status_code == 302  # về trang đăng nhập admin

    def test_reload_by_staff(self, client, make_mv, service):
        make_mv("confident.pt")
        admin = get_user_model().objects.create_superuser(email="admin@example.com", password="x" * 12)
        client.force_login(admin)
        data = client.post(reverse("recognition:reload")).json()
        assert data == {"ok": True, "model_version": "confident.pt", "num_classes": 3}
