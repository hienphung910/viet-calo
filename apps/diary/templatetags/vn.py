"""Filter định dạng số kiểu Việt Nam: {% load vn %} ... {{ value|num }} -> 1.498"""
from django import template

register = template.Library()


@register.filter
def num(value):
    """Làm tròn về số nguyên và nhóm hàng nghìn bằng dấu chấm (locale 'vi' của Django không tự nhóm)."""
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        return value
    return f"{n:,}".replace(",", ".")
