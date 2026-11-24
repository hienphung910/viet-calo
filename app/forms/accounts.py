from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from app.models import User

INPUT_CSS = "field"


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", INPUT_CSS)


class RegisterForm(StyledFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ("email",)

    # Email luôn lưu chữ thường (giống UserManager). Nếu không, "An@x.com" và "an@x.com" thành hai tài khoản
    # trên CSDL phân biệt hoa thường, và người đăng ký bằng chữ hoa không đăng nhập lại được bằng chữ thường.
    def clean_email(self):
        return self.cleaned_data["email"].lower()


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Email")

    def clean_username(self):
        return self.cleaned_data["username"].lower()
