"""
Nạp bảng dinh dưỡng từ CSV vào bảng foods.

    python manage.py seed_foods                      # dùng settings.NUTRITION_CSV
    python manage.py seed_foods --csv path/to/file.csv
    python manage.py seed_foods --deactivate-missing # ẩn các món không còn trong CSV

Chạy lại nhiều lần an toàn (idempotent): món đã có (cùng class_label) thì cập nhật, chưa có thì thêm.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.foods.csv_loader import NutritionCSVError, load_nutrition_csv
from apps.foods.models import Food


class Command(BaseCommand):
    help = "Nạp/cập nhật danh sách món ăn và dinh dưỡng từ file CSV"

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=str(settings.NUTRITION_CSV), help="Đường dẫn file CSV")
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Đặt is_active=False cho món có trong CSDL nhưng không có trong CSV",
        )

    def handle(self, *args, **opts):
        try:
            rows, warnings = load_nutrition_csv(opts["csv"])
        except NutritionCSVError as e:
            raise CommandError(f"File CSV không hợp lệ:\n{e}")

        for w in warnings:
            self.stdout.write(self.style.WARNING(f"Cảnh báo: {w}"))

        created = updated = 0
        # Một transaction: lỗi giữa chừng thì không ghi gì cả.
        with transaction.atomic():
            for row in rows:
                _, is_new = Food.objects.update_or_create(
                    class_label=row.class_label,
                    defaults={
                        "name": row.name,
                        "name_vi": row.name_vi,
                        "kcal_per_100g": row.kcal_per_100g,
                        "protein": row.protein,
                        "carb": row.carb,
                        "fat": row.fat,
                        "default_portion_g": row.default_portion_g,
                        "is_active": True,
                    },
                )
                created += is_new
                updated += not is_new

            deactivated = 0
            if opts["deactivate_missing"]:
                labels = [r.class_label for r in rows]
                deactivated = Food.objects.exclude(class_label__in=labels).update(is_active=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Xong: thêm {created}, cập nhật {updated}, ẩn {deactivated}. Tổng số món: {Food.objects.count()}"
            )
        )
