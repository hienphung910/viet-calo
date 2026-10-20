from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class UserManager(BaseUserManager):
    """Manager cho User đăng nhập bằng email (không có trường username)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email là bắt buộc")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # băm mật khẩu (PBKDF2), không lưu mật khẩu gốc
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser phải có is_staff=True và is_superuser=True")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Bảng users. Kế thừa AbstractUser để dùng lại toàn bộ hệ thống auth của Django
    (password_hash nằm ở cột `password`, created_at là `date_joined`).
    """

    username = None  # bỏ username, đăng nhập bằng email
    email = models.EmailField("email", unique=True)
    daily_calorie_target = models.PositiveIntegerField(
        "mục tiêu kcal/ngày",
        default=2000,
        validators=[MinValueValidator(800), MaxValueValidator(6000)],
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "người dùng"
        verbose_name_plural = "người dùng"
        constraints = [
            # Validator chỉ chạy ở form; CHECK constraint bảo vệ ở tầng CSDL.
            models.CheckConstraint(
                condition=Q(daily_calorie_target__gte=800) & Q(daily_calorie_target__lte=6000),
                name="users_calorie_target_range",
            ),
        ]

    def __str__(self):
        return self.email
