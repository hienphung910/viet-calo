from django import forms
from django.conf import settings

from app.forms.diary import PortionForm
from app.models import Food, MealLog


class UploadForm(forms.Form):
    image = forms.ImageField(label="Ảnh món ăn")

    def clean_image(self):
        f = self.cleaned_data["image"]
        if f.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"Ảnh quá lớn (tối đa {settings.MAX_UPLOAD_MB} MB).")
        fmt = getattr(getattr(f, "image", None), "format", None)
        if fmt not in settings.ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError("Chỉ nhận ảnh JPG, PNG hoặc WEBP.")
        return f


class ConfirmForm(PortionForm):
    food = forms.ModelChoiceField(
        queryset=Food.objects.filter(is_active=True),
        error_messages={"required": "Hãy chọn món.", "invalid_choice": "Hãy chọn món trong danh sách."},
    )
    meal_type = forms.ChoiceField(choices=MealLog.MealType.choices)
    consent = forms.BooleanField(
        required=False,
        initial=True,
        label="Cho phép dùng ảnh này (ẩn danh) để cải thiện model",
    )

    def clean(self):
        data = super().clean()
        if data.get("food"):
            data["grams"] = self.resolve_grams(data["food"], data)
        return data
