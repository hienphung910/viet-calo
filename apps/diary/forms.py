from django import forms
from django.conf import settings

from apps.foods.models import Food, vi_sort_key

from .models import MealLog

INPUT_CSS = "field"  # utility "field" định nghĩa trong templates/base.html


def guess_meal_type(hour: int) -> str:
    if hour < 10:
        return MealLog.MealType.BREAKFAST
    if hour < 14:
        return MealLog.MealType.LUNCH
    if 17 <= hour < 21:
        return MealLog.MealType.DINNER
    return MealLog.MealType.SNACK


class PortionForm(forms.Form):
    """Khẩu phần Nhỏ/Vừa/Lớn (theo hệ số × khẩu phần mặc định của món) hoặc nhập số gram."""

    PORTION_CHOICES = [("small", "Nhỏ"), ("medium", "Vừa"), ("large", "Lớn"), ("custom", "Nhập số gram")]

    portion_choice = forms.ChoiceField(choices=PORTION_CHOICES, initial="medium")
    portion_g = forms.FloatField(required=False, min_value=1, max_value=3000)

    def resolve_grams(self, food: Food, data: dict) -> float | None:
        """Số gram cuối cùng; None (và gắn lỗi vào form) nếu thiếu."""
        pc = data.get("portion_choice")
        if pc == "custom":
            if not data.get("portion_g"):
                self.add_error("portion_g", "Nhập khẩu phần (gram).")
                return None
            return data["portion_g"]
        if pc:
            return round(food.default_portion_g * settings.PORTION_MULTIPLIERS[pc], 1)
        return None


def initial_portion(food: Food, grams: float) -> dict:
    """Giá trị ban đầu cho form sửa: khớp đúng một mức Nhỏ/Vừa/Lớn thì chọn mức đó, không thì 'custom'."""
    for key, m in settings.PORTION_MULTIPLIERS.items():
        if abs(food.default_portion_g * m - grams) < 0.05:
            return {"portion_choice": key, "portion_g": None}
    return {"portion_choice": "custom", "portion_g": grams}


class MealForm(PortionForm):
    """Thêm thủ công (không có ảnh) hoặc sửa một bữa ăn đã lưu."""

    food = forms.ModelChoiceField(queryset=Food.objects.filter(is_active=True), label="Món ăn")
    meal_type = forms.ChoiceField(choices=MealLog.MealType.choices, label="Bữa")
    eaten_at = forms.DateTimeField(
        label="Thời điểm ăn",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    field_order = ["food", "portion_choice", "portion_g", "meal_type", "eaten_at"]

    def __init__(self, *args, current_food: Food | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        food_field = self.fields["food"]
        if current_food is not None and not current_food.is_active:
            # Món đã bị ẩn nhưng bữa ăn cũ vẫn dùng -> vẫn cho giữ nguyên khi sửa.
            food_field.queryset = Food.objects.filter(is_active=True) | Food.objects.filter(pk=current_food.pk)
        # Sắp xếp theo tiếng Việt bỏ dấu (ORDER BY của SQLite xếp 'đ' xuống cuối).
        food_field.choices = [("", "-- chọn món --")] + [
            (f.pk, f.name_vi) for f in sorted(food_field.queryset, key=lambda f: vi_sort_key(f.name_vi))
        ]
        for name in ("food", "meal_type", "eaten_at", "portion_g"):
            self.fields[name].widget.attrs.setdefault("class", INPUT_CSS)

    def clean(self):
        data = super().clean()
        food = data.get("food")
        if food is not None:
            data["grams"] = self.resolve_grams(food, data)
        return data
