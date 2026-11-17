from django.contrib import admin

from app.admin.common import thumbnail

from app.models import MealLog


@admin.register(MealLog)
class MealLogAdmin(admin.ModelAdmin):
    list_display = (
        "thumb", "eaten_at", "user", "food", "meal_type", "portion_g", "kcal", "predicted_label", "model_version",
    )
    list_display_links = ("thumb", "eaten_at")
    list_filter = ("meal_type", "model_version", "eaten_date")
    search_fields = ("user__email", "food__name_vi", "predicted_label")
    date_hierarchy = "eaten_date"
    list_select_related = ("user", "food", "model_version")
    raw_id_fields = ("user",)
    readonly_fields = ("preview", "eaten_date", "created_at")

    @admin.display(description="Ảnh")
    def thumb(self, obj):
        return thumbnail(obj.image_path, size=44)

    @admin.display(description="Ảnh")
    def preview(self, obj):
        return thumbnail(obj.image_path, size=320)
