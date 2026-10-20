from django.apps import AppConfig


class FoodsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.foods"
    label = "foods"
    verbose_name = "Món ăn & dinh dưỡng"
