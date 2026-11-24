import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from app.models import Food, ModelVersion

MODEL_FILES = ("model.pt", "class_list.json", "metrics.json")


class Command(BaseCommand):
    help = "Chuẩn bị dữ liệu khi deploy: nạp bảng món ăn, tải và đăng ký model, tạo tài khoản admin"

    def handle(self, *args, **opts):
        # chỉ nạp khi bảng còn trống để không ghi đè số liệu admin đã sửa
        if not Food.objects.exists():
            call_command("seed_foods", stdout=self.stdout)
        self._setup_model()
        self._create_admin()

    def _setup_model(self):
        active = ModelVersion.objects.filter(is_active=True).first()
        if active and (settings.BASE_DIR / active.file_path).exists():
            return

        # ổ đĩa của server bị xoá mỗi lần deploy nên file model phải tải lại, dù CSDL vẫn còn bản ghi
        if settings.MODEL_URL and not self._model_dirs():
            try:
                self._download(settings.MODEL_URL)
            except (OSError, ValueError, zipfile.BadZipFile) as e:
                # link hỏng thì web vẫn phải chạy được (chỉ chưa nhận diện được ảnh)
                self.stderr.write(self.style.ERROR(f"Không tải được model từ MODEL_URL: {e}"))

        dirs = self._model_dirs()
        if not dirs:
            self.stdout.write(self.style.WARNING(
                "Chưa có model: đặt biến MODEL_URL (link file .zip) hoặc đưa thư mục model vào models/."
            ))
            return
        # register_model tự kích hoạt model đầu tiên nếu chưa có model nào đang dùng -> đưa model tốt nhất lên trước
        for model_dir in sorted(dirs, key=self._test_accuracy, reverse=True):
            call_command("register_model", str(model_dir), stdout=self.stdout)

    def _model_dirs(self) -> list[Path]:
        if not settings.MODELS_DIR.is_dir():
            return []
        return [d for d in settings.MODELS_DIR.iterdir() if all((d / name).exists() for name in MODEL_FILES)]

    @staticmethod
    def _test_accuracy(model_dir: Path) -> float:
        metrics = json.loads((model_dir / "metrics.json").read_text(encoding="utf-8"))
        return metrics.get("test_accuracy") or 0.0

    def _download(self, url: str):
        if not url.startswith(("https://", "http://")):
            raise ValueError("MODEL_URL phải là link http(s) tới file .zip")
        self.stdout.write(f"Đang tải model từ {url} ...")
        settings.MODELS_DIR.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "model.zip"
            extracted = Path(tmp) / "extracted"
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(extracted)
            # file .zip có thể chứa thẳng model.pt hoặc chứa thư mục model
            # (list() để tìm xong hết rồi mới chuyển thư mục, tránh chuyển trong lúc rglob còn đang quét)
            for model_pt in list(extracted.rglob("model.pt")):
                src = model_pt.parent
                name = src.name if src != extracted else "model"
                shutil.move(str(src), str(settings.MODELS_DIR / name))

    def _create_admin(self):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        User = get_user_model()
        if email and password and not User.objects.filter(email=email).exists():
            User.objects.create_superuser(email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f"Đã tạo tài khoản admin {email}"))
