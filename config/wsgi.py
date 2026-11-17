import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# nạp model ngay khi server khởi động
from app.services.prediction import warm_up  # noqa: E402

warm_up()
