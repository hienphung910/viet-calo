import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from PIL import Image

torch = pytest.importorskip("torch")

from app.models import FeedbackImage, Food, MealLog  # noqa: E402
from app.services import prediction as services  # noqa: E402
from app.models import ModelVersion  # noqa: E402
from app.services.prediction import ModelLoadError, NoActiveModel, PredictionService  # noqa: E402

PROBS = {
    "confident.pt": {"pho": 0.90, "bun_bo_hue": 0.06, "com_tam": 0.04},
    "unsure.pt": {"pho": 0.45, "bun_bo_hue": 0.35, "com_tam": 0.20},
    "v2.pt": {"pho": 0.10, "bun_bo_hue": 0.20, "com_tam": 0.70},
    "unknown.pt": {"mon_la": 0.80, "pho": 0.20},
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


class TestPredictionService:
    def test_no_active_model(self, db, service):
        with pytest.raises(NoActiveModel):
            service.predict(image())

    def test_missing_file(self, foods, service):
        ModelVersion.objects.create(version="x", file_path="khong/ton/tai.pt", trained_at=timezone.now(),
                                    is_active=True)
        with pytest.raises(ModelLoadError):
            service.predict(image())

    def test_returns_highest_probability(self, make_mv, service):
        make_mv("confident.pt")
        r = service.predict(image())
        assert r.label == "pho" and r.food.name_vi == "Phở"

    def test_low_probability_still_picks_top1(self, make_mv, service):
        make_mv("unsure.pt")
        assert service.predict(image()).label == "pho"

    def test_label_without_food(self, make_mv, service):
        make_mv("unknown.pt")
        r = service.predict(image())
        assert r.label == "mon_la" and r.food is None

    def test_hot_reload_when_active_model_changes(self, make_mv, service):
        make_mv("confident.pt")
        assert service.predict(image()).label == "pho"
        make_mv("v2.pt")
        r = service.predict(image())
        assert r.model_version == "v2.pt" and r.label == "com_tam"

    def test_check_interval_caches_model(self, make_mv, monkeypatch):
        svc = PredictionService(loader=fake_loader, check_interval=3600)
        make_mv("confident.pt")
        assert svc.predict(image()).model_version == "confident.pt"
        make_mv("v2.pt")
        assert svc.predict(image()).model_version == "confident.pt"
        assert svc.reload().version == "v2.pt"


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

    def test_rejects_image_with_too_many_pixels(self, logged_client, make_mv, service, media, settings):
        make_mv("confident.pt")
        settings.MAX_UPLOAD_PIXELS = 1000  # ảnh thử 64x48 = 3072 điểm ảnh
        resp = self.scan(logged_client)
        assert resp.status_code == 200
        assert "megapixel" in str(resp.context["form"].errors)
        assert not (media / "uploads").exists()

    def test_model_load_error_hides_server_path_from_users(self, client, user, foods, service):
        ModelVersion.objects.create(version="hong", file_path="duong/dan/bi-mat.pt", trained_at=timezone.now(),
                                    is_active=True)
        client.force_login(user)
        page = self.scan(client).content.decode()
        api = client.post(reverse("recognition:api_predict"), {"image": upload()})
        assert "Chưa nhận diện được" in page and api.status_code == 503
        assert "bi-mat.pt" not in page and "bi-mat.pt" not in api.json()["error"]

        # quản trị viên vẫn thấy chi tiết để biết file nào hỏng
        client.force_login(get_user_model().objects.create_superuser(email="admin@example.com", password="x" * 12))
        assert "bi-mat.pt" in client.post(reverse("recognition:api_predict"), {"image": upload()}).json()["error"]

    def test_upload_saves_image_without_exif(self, logged_client, make_mv, service, media):
        make_mv("confident.pt")
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"
        resp = self.scan(logged_client, jpeg_bytes(exif=exif))
        assert resp.status_code == 302
        pending = next(iter(logged_client.session["pending_scans"].values()))
        saved = media / pending["image"]
        assert saved.exists() and pending["image"].startswith("uploads/")
        assert not Image.open(saved).getexif()

    def test_confirm_page_preselects_top1(self, logged_client, make_mv, service):
        make_mv("unsure.pt")
        page = logged_client.get(self.scan(logged_client).url)
        pho = Food.objects.get(class_label="pho")
        assert page.context["predicted"] == pho
        assert f'id="food" value="{pho.pk}"' in page.content.decode()

    def test_label_without_food_asks_user(self, logged_client, make_mv, service):
        make_mv("unknown.pt")
        page = logged_client.get(self.scan(logged_client).url)
        assert page.context["predicted"] is None
        assert "chưa có dữ liệu dinh dưỡng" in page.content.decode()

    def test_confirm_saves_log_and_feedback(self, logged_client, user, make_mv, service, media):
        mv = make_mv("confident.pt")
        url = self.scan(logged_client).url
        pho = Food.objects.get(class_label="pho")
        resp = logged_client.post(url, {"food": pho.pk, "portion_choice": "medium", "meal_type": "lunch",
                                        "consent": "on"})
        assert resp.status_code == 302
        log = MealLog.objects.get()
        assert (log.user, log.food, log.portion_g, log.kcal) == (user, pho, 600, 540)
        assert (log.protein_g, log.carb_g, log.fat_g) == (36, 72, 12)
        assert log.model_version == mv and log.predicted_label == "pho"
        fb = FeedbackImage.objects.get()
        assert fb.true_food == pho and fb.meal_log == log and fb.image_path.name != log.image_path.name
        assert (media / fb.image_path.name).exists()
        assert logged_client.get(url).status_code == 404

    def test_change_food_with_custom_grams_no_consent(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        url = self.scan(logged_client).url
        banh_mi = Food.objects.get(class_label="banh_mi")
        logged_client.post(url, {"food": banh_mi.pk, "portion_choice": "custom", "portion_g": 150,
                                 "meal_type": "breakfast"})
        log = MealLog.objects.get()
        assert log.food == banh_mi and log.portion_g == 150 and log.kcal == 390
        assert log.predicted_label == "pho"
        assert not FeedbackImage.objects.exists()

    def test_small_portion_uses_multiplier(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        url = self.scan(logged_client).url
        com_tam = Food.objects.get(class_label="com_tam")
        logged_client.post(url, {"food": com_tam.pk, "portion_choice": "small", "meal_type": "dinner"})
        assert MealLog.objects.get().portion_g == 315

    @pytest.mark.parametrize("data, field", [
        ({"food": "999999", "portion_choice": "medium", "meal_type": "lunch"}, "food"),
        ({"food": "", "portion_choice": "medium", "meal_type": "lunch"}, "food"),
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
        assert other.get(url).status_code == 404


@pytest.mark.django_db
class TestApi:
    def test_api_predict(self, logged_client, make_mv, service):
        make_mv("unsure.pt")
        data = logged_client.post(reverse("recognition:api_predict"), {"image": upload()}).json()
        assert data["label"] == "pho" and data["name_vi"] == "Phở"
        assert "confidence" not in data
        assert not MealLog.objects.exists()

    def test_api_preview_does_not_save_image(self, logged_client, make_mv, service, media):
        make_mv("confident.pt")
        for _ in range(3):
            data = logged_client.post(reverse("recognition:api_predict") + "?preview=1", {"image": upload()}).json()
            assert data["image"] is None and data["label"] == "pho"
        assert not (media / "uploads").exists()

    def test_upload_page_has_camera(self, logged_client):
        html = logged_client.get(reverse("recognition:upload")).content.decode()
        assert 'id="cam-video"' in html and "getUserMedia" in html and "?preview=1" in html

    def test_api_requires_post(self, logged_client):
        assert logged_client.get(reverse("recognition:api_predict")).status_code == 405

    def test_reload_staff_only(self, logged_client, make_mv, service):
        make_mv("confident.pt")
        assert logged_client.post(reverse("recognition:reload")).status_code == 302

    def test_reload_by_staff(self, client, make_mv, service):
        make_mv("confident.pt")
        admin = get_user_model().objects.create_superuser(email="admin@example.com", password="x" * 12)
        client.force_login(admin)
        data = client.post(reverse("recognition:reload")).json()
        assert data == {"ok": True, "model_version": "confident.pt", "num_classes": 3}
