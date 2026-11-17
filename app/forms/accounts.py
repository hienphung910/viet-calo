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


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Email")
