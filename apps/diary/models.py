from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class MealLog(models.Model):
    """
    Bảng meal_logs: mỗi dòng là một món người dùng đã ăn.

    kcal / protein_g / carb_g / fat_g được lưu sẵn (snapshot) tại thời điểm ghi:
    nếu admin sửa bảng dinh dưỡng sau này, nhật ký cũ không bị thay đổi theo.
    """

    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Bữa sáng"
        LUNCH = "lunch", "Bữa trưa"
        DINNER = "dinner", "Bữa tối"
        SNACK = "snack", "Bữa phụ"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_logs", verbose_name="người dùng"
    )
    # PROTECT: không xóa được món đã có trong nhật ký.
    food = models.ForeignKey("foods.Food", on_delete=models.PROTECT, related_name="meal_logs", verbose_name="món")
    # SET_NULL: xóa phiên bản model cũ không làm mất nhật ký.
    model_version = models.ForeignKey(
        "recognition.ModelVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meal_logs",
        verbose_name="phiên bản model",
    )
    # ImageField chỉ lưu đường dẫn tương đối (vd: uploads/2026/10/abc.jpg), file nằm trong media/.
    image_path = models.ImageField("ảnh", upload_to="uploads/%Y/%m/", blank=True)
    meal_type = models.CharField("bữa", max_length=10, choices=MealType.choices, default=MealType.LUNCH)
    portion_g = models.FloatField("khẩu phần (g)")
    kcal = models.FloatField()
    protein_g = models.FloatField(default=0)
    carb_g = models.FloatField(default=0)
    fat_g = models.FloatField(default=0)
    # Kết quả model: nhãn top-1, độ tin cậy, và top-3 [{label, confidence}, ...]
    predicted_label = models.CharField("model đoán", max_length=64, blank=True)
    confidence = models.FloatField("độ tin cậy", null=True, blank=True)
    top3_predictions = models.JSONField("top-3", default=list, blank=True)
    # True khi món cuối cùng khác top-1 của model -> dùng tính tỷ lệ đoán sai.
    was_corrected = models.BooleanField("đã sửa nhãn", default=False)
    eaten_at = models.DateTimeField("thời điểm ăn", default=timezone.now)
    # Ngày ăn theo giờ Việt Nam, tính từ eaten_at trong save().
    # Lý do lưu riêng: MySQL lưu datetime theo UTC; muốn gom nhóm theo ngày giờ VN bằng
    # TruncDate thì MySQL phải có bảng múi giờ (CONVERT_TZ), Windows mặc định không có.
    # Cột DATE riêng giúp GROUP BY theo ngày đơn giản, đúng và đánh index được.
    eaten_date = models.DateField("ngày ăn", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meal_logs"
        ordering = ["-eaten_at"]
        verbose_name = "bữa ăn"
        verbose_name_plural = "nhật ký ăn uống"
        indexes = [
            # Truy vấn chính: tổng kcal của 1 user theo ngày/tuần.
            models.Index(fields=["user", "eaten_date"], name="meal_logs_user_date_idx"),
            # Danh sách bữa ăn gần nhất của 1 user.
            models.Index(fields=["user", "eaten_at"], name="meal_logs_user_eaten_idx"),
            # Thống kê độ chính xác theo phiên bản model.
            models.Index(fields=["model_version", "was_corrected"], name="meal_logs_model_corr_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(portion_g__gt=0), name="meal_logs_portion_positive"),
            models.CheckConstraint(condition=Q(kcal__gte=0), name="meal_logs_kcal_non_negative"),
            models.CheckConstraint(
                condition=Q(confidence__isnull=True) | (Q(confidence__gte=0) & Q(confidence__lte=1)),
                name="meal_logs_confidence_0_1",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.food} ({self.portion_g:g}g)"

    def save(self, *args, **kwargs):
        # Luôn đồng bộ eaten_date với eaten_at. Lưu ý: QuerySet.update(eaten_at=...)
        # bỏ qua save(), nên khi sửa eaten_at hãy dùng save().
        self.eaten_date = timezone.localdate(self.eaten_at)
        super().save(*args, **kwargs)
