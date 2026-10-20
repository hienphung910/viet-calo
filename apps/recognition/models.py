from django.db import models, transaction
from django.db.models import Case, Value, When


class ModelVersion(models.Model):
    """
    Bảng model_versions: mỗi lần train xong ghi một dòng.
    Tại một thời điểm chỉ có đúng 1 dòng is_active=True (ràng buộc unique có điều kiện).
    """

    version = models.CharField("phiên bản", max_length=50, unique=True)
    backbone = models.CharField(max_length=64, blank=True)
    file_path = models.CharField("đường dẫn file model", max_length=255)
    class_list = models.JSONField("danh sách lớp", default=list)  # thứ tự = chỉ số output của model
    val_accuracy = models.FloatField(null=True, blank=True)
    top3_accuracy = models.FloatField(null=True, blank=True)
    test_accuracy = models.FloatField(null=True, blank=True)
    trained_at = models.DateTimeField("thời điểm train")
    is_active = models.BooleanField("đang dùng", default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "model_versions"
        ordering = ["-trained_at"]
        verbose_name = "phiên bản model"
        verbose_name_plural = "phiên bản model"
        constraints = [
            # Chỉ cho phép 1 dòng is_active=True.
            # MySQL không có partial index (UNIQUE ... WHERE), nên dùng functional unique index
            # (MySQL >= 8.0.13): đánh index biểu thức CASE -> dòng active = 1, dòng khác = NULL.
            # Unique index cho phép nhiều NULL, nên chỉ có đúng một giá trị 1.
            models.UniqueConstraint(
                Case(When(is_active=True, then=Value(1)), default=None),
                name="model_versions_single_active",
            ),
        ]

    def __str__(self):
        return f"{self.version}{' (active)' if self.is_active else ''}"

    @property
    def num_classes(self) -> int:
        return len(self.class_list)

    def activate(self):
        """Đặt model này làm model đang dùng. Hai lệnh UPDATE trong một transaction."""
        with transaction.atomic():
            ModelVersion.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
            ModelVersion.objects.filter(pk=self.pk).update(is_active=True)
        self.is_active = True
