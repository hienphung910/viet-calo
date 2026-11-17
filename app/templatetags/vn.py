from django import template

register = template.Library()


@register.filter
def num(value):
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        return value
    return f"{n:,}".replace(",", ".")
