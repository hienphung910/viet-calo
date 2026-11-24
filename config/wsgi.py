import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# nạp model ngay khi server khởi động
from django.conf import settings  # noqa: E402

from app.services.maintenance import start_upload_cleanup  # noqa: E402
from app.services.prediction import warm_up  # noqa: E402

warm_up()
start_upload_cleanup(settings.UPLOAD_CLEANUP_HOURS)
