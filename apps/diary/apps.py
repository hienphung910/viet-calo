from django.apps import AppConfig


class DiaryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.diary"
    label = "diary"
    verbose_name = "Nhật ký ăn uống"
