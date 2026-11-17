from django.db import models
from django.db.models import Q


class FeedbackImage(models.Model):
    meal_log = models.OneToOneField(
        "app.MealLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback",
        verbose_name="bữa ăn",
    )
    true_food = models.ForeignKey(
        "app.Food", on_delete=models.PROTECT, related_name="feedback_images", verbose_name="nhãn đúng"
    )
    image_path = models.ImageField("ảnh", upload_to="feedback/%Y/%m/")
    predicted_label = models.CharField("model đoán", max_length=64, blank=True)
    user_consented = models.BooleanField("người dùng đồng ý", default=True)
    used_in_training = models.BooleanField("đã dùng để train", default=False)
    created_at = models.DateTimeField("thời điểm tạo", auto_now_add=True)

    class Meta:
        db_table = "feedback_images"
        ordering = ["-created_at"]
        verbose_name = "ảnh phản hồi"
        verbose_name_plural = "ảnh phản hồi"
        indexes = [
            models.Index(fields=["used_in_training", "user_consented"], name="feedback_training_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(used_in_training=False) | Q(user_consented=True),
                name="feedback_training_requires_consent",
            ),
        ]

    def __str__(self):
        return f"#{self.pk} {self.true_food.class_label}"

    @property
    def was_wrong(self) -> bool:
        return bool(self.predicted_label) and self.predicted_label != self.true_food.class_label
