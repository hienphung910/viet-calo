import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Nạp model nhận diện ngay khi server khởi động (runserver và waitress đều đi qua file này),
# để request đầu tiên không phải chờ nạp model. Các lệnh như migrate/test không chạy đoạn này.
from apps.recognition.services import warm_up  # noqa: E402

warm_up()
