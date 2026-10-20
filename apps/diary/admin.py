from django.contrib import admin

from apps.common_admin import thumbnail

from .models import MealLog


@admin.register(MealLog)
class MealLogAdmin(admin.ModelAdmin):
    list_display = (
        "thumb", "eaten_at", "user", "food", "meal_type", "portion_g", "kcal", "predicted_label", "confidence",
        "was_corrected", "model_version",
    )
    list_display_links = ("thumb", "eaten_at")
    list_filter = ("meal_type", "was_corrected", "model_version", "eaten_date")
    search_fields = ("user__email", "food__name_vi", "predicted_label")
    date_hierarchy = "eaten_at"
    list_select_related = ("user", "food", "model_version")
    raw_id_fields = ("user",)
    readonly_fields = ("preview", "eaten_date", "top3_predictions", "created_at")

    @admin.display(description="Ảnh")
    def thumb(self, obj):
        return thumbnail(obj.image_path, size=44)

    @admin.display(description="Ảnh")
    def preview(self, obj):
        return thumbnail(obj.image_path, size=320)
