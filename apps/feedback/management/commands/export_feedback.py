"""
Xuất ảnh phản hồi (người dùng đã đồng ý, chưa dùng train) sang data/raw/<class_label>/ để train lại.

    python manage.py export_feedback --dry-run          # xem trước, không chép, không đánh dấu
    python manage.py export_feedback                    # chép + đánh dấu used_in_training
    python manage.py export_feedback --only-corrected   # chỉ ảnh model đoán sai

Sau đó: python -m ml.prepare_data  ->  python -m ml.train --register
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.feedback.services import export_feedback


class Command(BaseCommand):
    help = "Xuất ảnh phản hồi sang data/raw để train lại model"

    def add_arguments(self, parser):
        parser.add_argument("--dest", default=None, help="Mặc định: settings.FEEDBACK_EXPORT_DIR (data/raw)")
        parser.add_argument("--only-corrected", action="store_true", help="Chỉ xuất ảnh model đoán sai")
        parser.add_argument("--dry-run", action="store_true", help="Chỉ thống kê, không chép, không đánh dấu")

    def handle(self, *args, **opts):
        dest = Path(opts["dest"] or settings.FEEDBACK_EXPORT_DIR)
        r = export_feedback(dest, only_corrected=opts["only_corrected"], dry_run=opts["dry_run"])
        for label, n in sorted(r.exported.items()):
            self.stdout.write(f"  {label:<22}{n:>5}")
        if r.missing:
            self.stdout.write(self.style.WARNING(f"Bỏ qua {len(r.missing)} ảnh mất file: id {r.missing}"))
        if r.skipped_inactive:
            self.stdout.write(self.style.WARNING(f"Bỏ qua {r.skipped_inactive} ảnh của món đã bị ẩn"))
        verb = "Sẽ xuất (dry-run)" if r.dry_run else "Đã xuất"
        self.stdout.write(self.style.SUCCESS(f"{verb} {r.total} ảnh, {len(r.exported)} lớp -> {dest}"))
