"""
Ghi một model đã train (thư mục models/<version>/) vào bảng model_versions.

    python manage.py register_model models/20261019-1530-efficientnet_b0
    python manage.py register_model models/... --activate     # đặt làm model đang dùng

ml/train.py --register gọi lệnh này tự động. Chạy lại với cùng version thì cập nhật dòng cũ.
"""
import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.foods.models import Food
from apps.recognition.models import ModelVersion


class Command(BaseCommand):
    help = "Đăng ký model đã train vào bảng model_versions"

    def add_arguments(self, parser):
        parser.add_argument("model_dir", help="Thư mục chứa model.pt, class_list.json, metrics.json")
        parser.add_argument("--activate", action="store_true", help="Đặt làm model đang dùng")
        parser.add_argument("--force", action="store_true", help="Cho kích hoạt dù có lớp chưa có trong bảng foods")
        parser.add_argument("--notes", default="")

    def handle(self, *args, **opts):
        model_dir = Path(opts["model_dir"])
        if not model_dir.is_absolute():
            model_dir = (settings.BASE_DIR / model_dir).resolve()
        for name in ("model.pt", "class_list.json", "metrics.json"):
            if not (model_dir / name).exists():
                raise CommandError(f"Thiếu {model_dir / name}")

        class_list = json.loads((model_dir / "class_list.json").read_text(encoding="utf-8"))
        metrics = json.loads((model_dir / "metrics.json").read_text(encoding="utf-8"))

        # Model đoán ra nhãn không có trong bảng foods thì web không tính được calo.
        known = set(Food.objects.filter(is_active=True).values_list("class_label", flat=True))
        missing = [c for c in class_list if c not in known]
        if missing:
            self.stdout.write(self.style.WARNING(
                f"Các lớp chưa có trong bảng foods: {', '.join(missing)} -> chạy seed_foods sau khi thêm dòng CSV."
            ))
            if opts["activate"] and not opts["force"]:
                raise CommandError("Không kích hoạt model có lớp thiếu dữ liệu dinh dưỡng (dùng --force nếu chắc chắn).")

        # Lưu đường dẫn tương đối so với thư mục dự án để chuyển máy vẫn dùng được.
        try:
            file_path = (model_dir / "model.pt").relative_to(settings.BASE_DIR).as_posix()
        except ValueError:
            file_path = (model_dir / "model.pt").as_posix()

        trained_at = metrics.get("trained_at")
        trained_at = datetime.fromisoformat(trained_at) if trained_at else timezone.now()
        if timezone.is_naive(trained_at):
            trained_at = timezone.make_aware(trained_at)

        mv, created = ModelVersion.objects.update_or_create(
            version=metrics.get("version", model_dir.name),
            defaults={
                "backbone": metrics.get("backbone", ""),
                "file_path": file_path,
                "class_list": class_list,
                "val_accuracy": metrics.get("val_accuracy"),
                "top3_accuracy": metrics.get("top3_accuracy"),
                "test_accuracy": metrics.get("test_accuracy"),
                "trained_at": trained_at,
                "notes": opts["notes"],
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"{'Đã thêm' if created else 'Đã cập nhật'} model_versions: {mv.version} "
            f"(val acc {mv.val_accuracy}, top-3 {mv.top3_accuracy}, test acc {mv.test_accuracy})"
        ))

        # Chưa có model nào đang dùng thì tự kích hoạt model đầu tiên.
        if opts["activate"] or not ModelVersion.objects.filter(is_active=True).exists():
            if missing and not opts["force"]:
                self.stdout.write(self.style.WARNING("Không tự kích hoạt vì thiếu dữ liệu dinh dưỡng."))
                return
            mv.activate()
            self.stdout.write(self.style.SUCCESS(f"Model đang dùng: {mv.version}"))
