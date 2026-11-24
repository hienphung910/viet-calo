from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from app.forms.accounts import LoginForm, RegisterForm, StyledPasswordChangeForm
from app.signals import WEAK_PASSWORD_KEY


def register(request):
    if request.user.is_authenticated:
        return redirect("diary:home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Tạo tài khoản thành công.")
        return redirect("diary:home")
    return render(request, "accounts/register.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class PasswordChange(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("diary:home")

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs, forced=bool(self.request.session.get(WEAK_PASSWORD_KEY)))

    def form_valid(self, form):
        response = super().form_valid(form)  # lưu mật khẩu mới và giữ phiên đăng nhập hiện tại
        self.request.session.pop(WEAK_PASSWORD_KEY, None)
        messages.success(self.request, "Đã đổi mật khẩu.")
        return response
