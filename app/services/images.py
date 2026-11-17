import io
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image

from ml.common import load_image


def open_upload(uploaded_file) -> Image.Image:
    uploaded_file.seek(0)
    return load_image(uploaded_file)


def _new_name(folder: str) -> str:
    return f"{folder}/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}.jpg"


def save_image(image: Image.Image, folder: str = "uploads") -> str:
    im = image.copy()
    im.thumbnail((settings.UPLOAD_MAX_SIDE, settings.UPLOAD_MAX_SIDE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return default_storage.save(_new_name(folder), ContentFile(buf.getvalue()))


def copy_image(name: str, folder: str) -> str:
    with default_storage.open(name, "rb") as f:
        return default_storage.save(_new_name(folder), ContentFile(f.read()))
