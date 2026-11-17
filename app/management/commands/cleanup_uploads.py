import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from app.models import MealLog
from app.models import FeedbackImage

FOLDERS = ("uploads", "feedback")


class Command(BaseCommand):
    help = "Xóa ảnh trong media/uploads và media/feedback không còn được CSDL tham chiếu"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=float, default=24, help="Chỉ xóa file cũ hơn số giờ này (mặc định 24)")
        parser.add_argument("--dry-run", action="store_true", help="Chỉ liệt kê, không xóa")

    def handle(self, *args, **opts):
        media = Path(settings.MEDIA_ROOT)
        used = set(MealLog.objects.exclude(image_path="").values_list("image_path", flat=True))
        used |= set(FeedbackImage.objects.exclude(image_path="").values_list("image_path", flat=True))
        cutoff = time.time() - opts["hours"] * 3600

        orphans = []
        for folder in FOLDERS:
            base = media / folder
            if not base.exists():
                continue
            for f in base.rglob("*"):
                if f.is_file() and f.relative_to(media).as_posix() not in used and f.stat().st_mtime < cutoff:
                    orphans.append(f)

        size = sum(f.stat().st_size for f in orphans)
        for f in orphans:
            if opts["verbosity"] > 1 or opts["dry_run"]:
                self.stdout.write(f"  {f.relative_to(media).as_posix()}")
            if not opts["dry_run"]:
                f.unlink()

        if not opts["dry_run"]:
            for folder in FOLDERS:
                base = media / folder
                if base.exists():
                    for d in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
                        if not any(d.iterdir()):
                            d.rmdir()

        verb = "Sẽ xóa (dry-run)" if opts["dry_run"] else "Đã xóa"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {len(orphans)} ảnh mồ côi ({size / 1024 / 1024:.2f} MB). Đang dùng: {len(used)} ảnh."
        ))
