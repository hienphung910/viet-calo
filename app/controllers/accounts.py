from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from app.forms.accounts import LoginForm, RegisterForm


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
