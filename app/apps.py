from django.apps import AppConfig


class VietCaloConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app"
    verbose_name = "VietCalo"

    def ready(self):
        from app import signals  # noqa: F401  (đăng ký các hàm nhận tín hiệu đăng nhập)
