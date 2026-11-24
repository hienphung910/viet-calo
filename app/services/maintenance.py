import logging
import threading

from django.core.management import call_command
from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)


def cleanup_uploads_once() -> None:
    close_old_connections()
    try:
        call_command("cleanup_uploads")
    except Exception:
        logger.exception("Dọn ảnh mồ côi bị lỗi")
    finally:
        # luồng này không thuộc request nào nên Django không tự đóng kết nối CSDL của nó
        connections.close_all()


def start_upload_cleanup(hours: float, stop: threading.Event | None = None) -> threading.Thread | None:
    """Chạy cleanup_uploads ngay lúc khởi động rồi lặp lại mỗi `hours` giờ, trong một luồng nền."""
    if hours <= 0:
        return None
    stop = stop or threading.Event()

    def loop():
        while True:
            cleanup_uploads_once()
            if stop.wait(hours * 3600):  # trả về True khi có yêu cầu dừng (dùng trong test)
                return

    thread = threading.Thread(target=loop, name="upload-cleanup", daemon=True)
    thread.start()
    return thread
