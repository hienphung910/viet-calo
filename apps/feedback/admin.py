from django.conf import settings
from django.contrib import admin, messages
from django.db.models import F

from apps.common_admin import thumbnail

from .models import FeedbackImage
from .services import export_feedback, unexport


class PredictionFilter(admin.SimpleListFilter):
    title = "model đoán"
    parameter_name = "prediction"

    def lookups(self, request, model_admin):
        return [("wrong", "Sai (người dùng sửa nhãn)"), ("right", "Đúng")]

    def queryset(self, request, qs):
        wrong = qs.exclude(predicted_label="").exclude(predicted_label=F("true_food__class_label"))
        if self.value() == "wrong":
            return wrong
        if self.value() == "right":
            return qs.filter(predicted_label=F("true_food__class_label"))
        return qs


@admin.register(FeedbackImage)
class FeedbackImageAdmin(admin.ModelAdmin):
    """
    Duyệt ảnh phản hồi trước khi đưa vào data train: xem ảnh, sửa nhãn đúng ngay trong danh sách
    (cột true_food), bỏ ảnh xấu (rút đồng ý), rồi xuất sang data/raw.
    """

    list_display = ("thumb", "true_food", "predicted_label", "wrong", "owner", "user_consented",
                    "used_in_training", "created_at")
    list_display_links = ("thumb",)
    list_editable = ("true_food",)  # admin sửa nhãn trực tiếp trong danh sách
    list_filter = (PredictionFilter, "used_in_training", "user_consented", "true_food")
    list_select_related = ("true_food", "meal_log__user")
    search_fields = ("predicted_label", "true_food__name_vi", "meal_log__user__email")
    readonly_fields = ("preview", "meal_log", "predicted_label", "created_at")
    fields = ("preview", "true_food", "predicted_label", "user_consented", "used_in_training", "meal_log", "created_at")
    list_per_page = 50
    actions = ["export_selected", "mark_unused", "exclude_from_training"]

    @admin.display(description="Ảnh")
    def thumb(self, obj):
        return thumbnail(obj.image_path)

    @admin.display(description="Ảnh")
    def preview(self, obj):
        return thumbnail(obj.image_path, size=320)

    @admin.display(description="Model sai", boolean=True)
    def wrong(self, obj):
        return obj.was_wrong if obj.predicted_label else None

    @admin.display(description="Người dùng", ordering="meal_log__user__email")
    def owner(self, obj):
        return obj.meal_log.user.email if obj.meal_log else "(bữa ăn đã xóa)"

    @admin.action(description="Xuất ảnh đã chọn sang data/raw (để train lại)")
    def export_selected(self, request, queryset):
        r = export_feedback(settings.FEEDBACK_EXPORT_DIR, queryset=queryset)
        detail = ", ".join(f"{k}: {v}" for k, v in sorted(r.exported.items()))
        self.message_user(request, f"Đã xuất {r.total} ảnh. {detail}")
        skipped = queryset.count() - r.total
        if skipped:
            self.message_user(request, f"{skipped} ảnh bị bỏ qua (chưa đồng ý, đã dùng train, mất file "
                                       "hoặc món đã ẩn).", level=messages.WARNING)

    @admin.action(description="Đánh dấu CHƯA dùng train (để xuất lại)")
    def mark_unused(self, request, queryset):
        n = queryset.update(used_in_training=False)
        self.message_user(request, f"Đã đánh dấu {n} ảnh.")

    @admin.action(description="Loại khỏi dữ liệu train (ảnh xấu / sai)")
    def exclude_from_training(self, request, queryset):
        removed = sum(unexport(fb) for fb in queryset.filter(used_in_training=True).select_related("true_food"))
        # Ràng buộc CSDL: used_in_training=True bắt buộc user_consented=True -> cập nhật cả hai.
        n = queryset.update(user_consented=False, used_in_training=False)
        self.message_user(request, f"Đã loại {n} ảnh khỏi dữ liệu train, gỡ {removed} file khỏi data/raw.")

    def save_model(self, request, obj, form, change):
        # Sửa nhãn một ảnh ĐÃ xuất (kể cả sửa ngay trong danh sách): gỡ file ở thư mục nhãn cũ và
        # đánh dấu chưa dùng, để lần xuất sau chép lại vào đúng thư mục nhãn mới.
        if change and obj.pk:
            old = FeedbackImage.objects.select_related("true_food").get(pk=obj.pk)
            if old.used_in_training and old.true_food_id != obj.true_food_id:
                unexport(old)
                obj.used_in_training = False
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        unexport(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for fb in queryset.select_related("true_food"):
            unexport(fb)
        super().delete_queryset(request, queryset)
