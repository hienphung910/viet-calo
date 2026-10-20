import io

from django.contrib import admin, messages
from django.core.management import CommandError, call_command
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import path, reverse

from .models import Food


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    # Template có thêm nút "Nạp lại từ nutrition.csv".
    change_list_template = "admin/foods/food/change_list.html"
    list_display = (
        "name_vi", "class_label", "kcal_per_100g", "protein", "carb", "fat", "default_portion_g", "times_eaten",
        "feedback_images", "is_active",
    )
    list_editable = ("kcal_per_100g", "protein", "carb", "fat", "default_portion_g", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name_vi", "name", "class_label")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _eaten=Count("meal_logs", distinct=True), _fb=Count("feedback_images", distinct=True)
        )

    @admin.display(description="Số lần ăn", ordering="_eaten")
    def times_eaten(self, obj):
        return obj._eaten

    @admin.display(description="Ảnh phản hồi", ordering="_fb")
    def feedback_images(self, obj):
        return obj._fb

    def get_urls(self):
        return [path("seed/", self.admin_site.admin_view(self.seed_view), name="foods_food_seed"), *super().get_urls()]

    def seed_view(self, request):
        """Chạy lệnh seed_foods từ trang admin (sau khi sửa data/nutrition.csv)."""
        if request.method == "POST" and self.has_change_permission(request):
            out = io.StringIO()
            try:
                call_command("seed_foods", stdout=out)
                for line in out.getvalue().strip().splitlines():
                    self.message_user(request, line, level=messages.WARNING if "Cảnh báo" in line else messages.SUCCESS)
            except CommandError as e:
                self.message_user(request, str(e), level=messages.ERROR)
        return redirect(reverse("admin:foods_food_changelist"))
