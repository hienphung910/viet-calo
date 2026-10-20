"""Tiện ích dùng chung cho các trang admin."""
from django.utils.html import format_html


def thumbnail(image_field, size: int = 56):
    """Ảnh thu nhỏ cho cột danh sách / trang chi tiết trong admin."""
    if not image_field:
        return "—"
    return format_html(
        '<a href="{0}" target="_blank"><img src="{0}" alt="" '
        'style="height:{1}px;width:{1}px;object-fit:cover;border-radius:6px"></a>',
        image_field.url,
        size,
    )
