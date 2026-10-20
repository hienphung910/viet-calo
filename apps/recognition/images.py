"""Lưu ảnh người dùng upload vào media/. CSDL chỉ lưu đường dẫn tương đối do các hàm này trả về."""
import io
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image

from ml.common import load_image


def open_upload(uploaded_file) -> Image.Image:
    """Ảnh upload -> ảnh PIL đã xoay theo EXIF, RGB (cùng hàm load_image với lúc chuẩn bị data train)."""
    uploaded_file.seek(0)
    return load_image(uploaded_file)


def _new_name(folder: str) -> str:
    # Tên ngẫu nhiên: không lộ tên file gốc của người dùng, không trùng.
    return f"{folder}/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}.jpg"


def save_image(image: Image.Image, folder: str = "uploads") -> str:
    """
    Thu nhỏ (cạnh dài tối đa UPLOAD_MAX_SIDE) và lưu JPEG. Ghi lại từ pixel nên toàn bộ
    metadata EXIF (kể cả tọa độ GPS nơi chụp) bị loại bỏ -> bảo vệ quyền riêng tư.
    """
    im = image.copy()
    im.thumbnail((settings.UPLOAD_MAX_SIDE, settings.UPLOAD_MAX_SIDE), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return default_storage.save(_new_name(folder), ContentFile(buf.getvalue()))


def copy_image(name: str, folder: str) -> str:
    """Tạo bản sao độc lập (ảnh feedback không mất khi người dùng xóa bữa ăn)."""
    with default_storage.open(name, "rb") as f:
        return default_storage.save(_new_name(folder), ContentFile(f.read()))
