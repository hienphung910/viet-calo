from django.db import models
from django.db.models import Q


class FeedbackImage(models.Model):
    """
    Bảng feedback_images: ảnh người dùng đã xác nhận/sửa nhãn và ĐỒNG Ý cho dùng để train.

    Ảnh được copy riêng sang media/feedback/, nên khi người dùng xóa bữa ăn (meal_log -> NULL)
    dữ liệu train vẫn còn.
    """

    meal_log = models.OneToOneField(
        "diary.MealLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback",
        verbose_name="bữa ăn",
    )
    # Nhãn đúng là FK tới foods (không phải text tự do) -> không thể sai chính tả nhãn.
    true_food = models.ForeignKey(
        "foods.Food", on_delete=models.PROTECT, related_name="feedback_images", verbose_name="nhãn đúng"
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
            # export_feedback.py lọc theo cặp cờ này.
            models.Index(fields=["used_in_training", "user_consented"], name="feedback_training_idx"),
        ]
        constraints = [
            # Không được dùng ảnh để train nếu người dùng chưa (hoặc đã rút lại) đồng ý.
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
