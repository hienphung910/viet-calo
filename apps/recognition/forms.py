from django import forms
from django.conf import settings

from apps.diary.forms import PortionForm
from apps.diary.models import MealLog
from apps.foods.models import Food


class UploadForm(forms.Form):
    image = forms.ImageField(label="Ảnh món ăn")  # ImageField tự kiểm tra file có phải ảnh hợp lệ (Pillow)

    def clean_image(self):
        f = self.cleaned_data["image"]
        if f.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"Ảnh quá lớn (tối đa {settings.MAX_UPLOAD_MB} MB).")
        fmt = getattr(getattr(f, "image", None), "format", None)
        if fmt not in settings.ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError("Chỉ nhận ảnh JPG, PNG hoặc WEBP.")
        return f


class ConfirmForm(PortionForm):
    """
    Xác nhận món + khẩu phần. `choice` là id của một món trong top-3, hoặc "other" để chọn
    món khác trong danh sách (sửa nhãn khi model đoán sai hoàn toàn).
    """

    choice = forms.CharField()
    other_food = forms.ModelChoiceField(queryset=Food.objects.filter(is_active=True), required=False)
    meal_type = forms.ChoiceField(choices=MealLog.MealType.choices)
    consent = forms.BooleanField(
        required=False,
        initial=True,
        label="Cho phép dùng ảnh này (ẩn danh) để cải thiện model",
    )

    def __init__(self, *args, candidate_food_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.candidate_food_ids = {str(i) for i in candidate_food_ids}

    def clean(self):
        data = super().clean()
        choice = data.get("choice")
        if choice == "other":
            food = data.get("other_food")
            if food is None:
                self.add_error("other_food", "Hãy chọn món trong danh sách.")
                return data
        elif choice in self.candidate_food_ids:
            food = Food.objects.get(pk=choice)
        else:
            self.add_error("choice", "Hãy chọn món đúng.")
            return data
        data["food"] = food
        data["grams"] = self.resolve_grams(food, data)
        return data
