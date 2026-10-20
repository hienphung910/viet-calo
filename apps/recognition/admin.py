from django.contrib import admin, messages
from django.db.models import Count, Q

from .models import ModelVersion
from .services import ModelLoadError, NoActiveModel, get_service


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    # Template có thêm nút "Thống kê & so sánh" và "Nạp lại model".
    change_list_template = "admin/recognition/modelversion/change_list.html"
    list_display = (
        "version", "backbone", "classes", "pct_val", "pct_test", "uses", "pct_real", "trained_at", "is_active",
    )
    list_filter = ("is_active", "backbone")
    readonly_fields = ("is_active", "created_at", "class_list")
    actions = ["activate_selected"]

    def get_queryset(self, request):
        # Độ chính xác thực tế = bữa ăn AI nhận diện mà người dùng không sửa nhãn.
        ai = Q(meal_logs__predicted_label__gt="")
        return super().get_queryset(request).annotate(
            _uses=Count("meal_logs", filter=ai),
            _correct=Count("meal_logs", filter=ai & Q(meal_logs__was_corrected=False)),
        )

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

    @admin.display(description="Lượt dùng", ordering="_uses")
    def uses(self, obj):
        return obj._uses

    @admin.display(description="Thực tế top-1")
    def pct_real(self, obj):
        return self._pct(obj._correct / obj._uses) if obj._uses else "—"

    @admin.action(description="Đặt làm model đang dùng")
    def activate_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Chọn đúng 1 phiên bản.", level=messages.ERROR)
            return
        mv = queryset.get()
        mv.activate()
        # Process đang xử lý request này nạp ngay; các process khác tự nạp sau MODEL_CHECK_INTERVAL giây.
        try:
            get_service().reload()
            self.message_user(request, f"Đã kích hoạt và nạp {mv.version}.")
        except (NoActiveModel, ModelLoadError) as e:
            self.message_user(request, f"Đã kích hoạt {mv.version} nhưng nạp lỗi: {e}", level=messages.ERROR)
