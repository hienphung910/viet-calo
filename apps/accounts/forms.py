from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User

INPUT_CSS = "field"  # utility "field" định nghĩa trong templates/base.html


class StyledFormMixin:
    """Gắn class Tailwind cho mọi input để template gọn."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT_CSS)


class RegisterForm(StyledFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "daily_calorie_target")
        labels = {"daily_calorie_target": "Mục tiêu kcal mỗi ngày"}
        help_texts = {"daily_calorie_target": "Người trưởng thành thường 1600–2500 kcal. Có thể sửa sau."}


class LoginForm(StyledFormMixin, AuthenticationForm):
    # AuthenticationForm dùng tên field "username" cho USERNAME_FIELD (ở đây là email).
    username = forms.EmailField(label="Email")


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "daily_calorie_target")
        labels = {"first_name": "Tên hiển thị", "daily_calorie_target": "Mục tiêu kcal mỗi ngày"}
