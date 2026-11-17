from django.contrib import admin, messages

from app.models import ModelVersion
from app.services.prediction import ModelLoadError, NoActiveModel, get_service


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    change_list_template = "admin/app/modelversion/change_list.html"
    list_display = (
        "version", "backbone", "classes", "pct_val", "pct_test", "trained_at", "is_active",
    )
    list_filter = ("is_active", "backbone")
    readonly_fields = ("is_active", "created_at", "class_list")
    actions = ["activate_selected"]

    @staticmethod
    def _pct(v):
        return f"{v * 100:.1f}%" if v is not None else "—"

    @admin.display(description="Số lớp")
    def classes(self, obj):
        return obj.num_classes

    @admin.display(description="Val acc", ordering="val_accuracy")
    def pct_val(self, obj):
        return self._pct(obj.val_accuracy)

    @admin.display(description="Test acc", ordering="test_accuracy")
    def pct_test(self, obj):
        return self._pct(obj.test_accuracy)

    @admin.action(description="Đặt làm model đang dùng")
    def activate_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Chọn đúng 1 phiên bản.", level=messages.ERROR)
            return
        mv = queryset.get()
        mv.activate()
        try:
            get_service().reload()
            self.message_user(request, f"Đã kích hoạt và nạp {mv.version}.")
        except (NoActiveModel, ModelLoadError) as e:
            self.message_user(request, f"Đã kích hoạt {mv.version} nhưng nạp lỗi: {e}", level=messages.ERROR)
