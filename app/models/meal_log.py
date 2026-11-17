from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class MealLog(models.Model):
    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Bữa sáng"
        LUNCH = "lunch", "Bữa trưa"
        DINNER = "dinner", "Bữa tối"
        SNACK = "snack", "Bữa phụ"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meal_logs", verbose_name="người dùng"
    )
    food = models.ForeignKey("app.Food", on_delete=models.PROTECT, related_name="meal_logs", verbose_name="món")
    model_version = models.ForeignKey(
        "app.ModelVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meal_logs",
        verbose_name="phiên bản model",
    )
    image_path = models.ImageField("ảnh", upload_to="uploads/%Y/%m/", blank=True)
    meal_type = models.CharField("bữa", max_length=10, choices=MealType.choices, default=MealType.LUNCH)
    portion_g = models.FloatField("khẩu phần (g)")
    # lưu sẵn dinh dưỡng lúc ghi, sửa bảng foods sau này không làm đổi nhật ký cũ
    kcal = models.FloatField()
    protein_g = models.FloatField(default=0)
    carb_g = models.FloatField(default=0)
    fat_g = models.FloatField(default=0)
    predicted_label = models.CharField("model đoán", max_length=64, blank=True)
    eaten_at = models.DateTimeField("thời điểm ăn", default=timezone.now)
    # ngày ăn theo giờ VN, tính trong save() để GROUP BY theo ngày cho dễ
    eaten_date = models.DateField("ngày ăn", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meal_logs"
        ordering = ["-eaten_at"]
        verbose_name = "bữa ăn"
        verbose_name_plural = "nhật ký ăn uống"
        indexes = [
            models.Index(fields=["user", "eaten_date"], name="meal_logs_user_date_idx"),
            models.Index(fields=["user", "eaten_at"], name="meal_logs_user_eaten_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(portion_g__gt=0), name="meal_logs_portion_positive"),
            models.CheckConstraint(condition=Q(kcal__gte=0), name="meal_logs_kcal_non_negative"),
        ]

    def __str__(self):
        return f"{self.user} - {self.food} ({self.portion_g:g}g)"

    def save(self, *args, **kwargs):
        self.eaten_date = timezone.localdate(self.eaten_at)
        super().save(*args, **kwargs)
