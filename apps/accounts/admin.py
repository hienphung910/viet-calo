from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # UserAdmin gốc dùng `username`; viết lại các fieldset cho User đăng nhập bằng email.
    ordering = ("email",)
    list_display = ("email", "first_name", "daily_calorie_target", "is_staff", "date_joined")
    search_fields = ("email", "first_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Thông tin", {"fields": ("first_name", "last_name", "daily_calorie_target")}),
        ("Phân quyền", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Thời gian", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "daily_calorie_target", "password1", "password2")}),
    )
