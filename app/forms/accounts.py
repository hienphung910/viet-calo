from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm

from app.models import User
from app.services import login_guard

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Không hiện sẵn danh sách quy tắc mật khẩu dưới ô nhập cho gọn giao diện.
        # Quy tắc vẫn được kiểm tra: mật khẩu không đạt thì form báo lỗi cụ thể khi bấm Đăng ký.
        self.fields["password1"].help_text = ""

    # Email luôn lưu chữ thường (giống UserManager). Nếu không, "An@x.com" và "an@x.com" thành hai tài khoản
    # trên CSDL phân biệt hoa thường, và người đăng ký bằng chữ hoa không đăng nhập lại được bằng chữ thường.
    def clean_email(self):
        return self.cleaned_data["email"].lower()


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Email")

    def clean_username(self):
        return self.cleaned_data["username"].lower()

    def clean(self):
        # GuardedModelBackend cũng chặn, nhưng chỉ báo "sai email hoặc mật khẩu"; ở đây nói rõ lý do
        if login_guard.is_blocked(self.request, self.cleaned_data.get("username")):
            raise forms.ValidationError(
                f"Bạn đã nhập sai quá nhiều lần. Hãy thử lại sau {settings.LOGIN_LOCK_SECONDS // 60} phút.",
                code="too_many_attempts",
            )
        return super().clean()


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass
