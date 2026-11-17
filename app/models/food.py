import unicodedata

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


def vi_sort_key(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()


class Food(models.Model):
    name = models.CharField("tên (EN)", max_length=100)
    name_vi = models.CharField("tên tiếng Việt", max_length=100)
    class_label = models.SlugField("nhãn lớp", max_length=64, unique=True)
    kcal_per_100g = models.FloatField("kcal / 100g", validators=[MinValueValidator(0)])
    protein = models.FloatField("protein (g/100g)", validators=[MinValueValidator(0)])
    carb = models.FloatField("carb (g/100g)", validators=[MinValueValidator(0)])
    fat = models.FloatField("fat (g/100g)", validators=[MinValueValidator(0)])
    default_portion_g = models.FloatField("khẩu phần mặc định (g)", validators=[MinValueValidator(1)])
    is_active = models.BooleanField("đang dùng", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "foods"
        ordering = ["name_vi"]
        verbose_name = "món ăn"
        verbose_name_plural = "món ăn"
        constraints = [
            models.CheckConstraint(
                condition=Q(kcal_per_100g__gte=0) & Q(protein__gte=0) & Q(carb__gte=0) & Q(fat__gte=0),
                name="foods_nutrition_non_negative",
            ),
            models.CheckConstraint(condition=Q(default_portion_g__gt=0), name="foods_portion_positive"),
        ]

    def __str__(self):
        return self.name_vi

    def nutrition_for(self, portion_g: float) -> dict:
        ratio = portion_g / 100
        return {
            "kcal": round(self.kcal_per_100g * ratio, 1),
            "protein_g": round(self.protein * ratio, 1),
            "carb_g": round(self.carb * ratio, 1),
            "fat_g": round(self.fat * ratio, 1),
        }
