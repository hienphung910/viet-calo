from datetime import date, timedelta

from django.db.models import Count, Sum

from app.models import MealLog

NUTRIENTS = ("kcal", "protein_g", "carb_g", "fat_g")


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _totals(qs) -> dict:
    agg = qs.aggregate(**{n: Sum(n) for n in NUTRIENTS}, count=Count("id"))
    return {n: round(agg[n] or 0, 1) for n in NUTRIENTS} | {"count": agg["count"]}


def day_summary(user, day: date) -> dict:
    qs = MealLog.objects.filter(user=user, eaten_date=day)
    return {
        "date": day,
        "totals": _totals(qs),
        "logs": qs.select_related("food", "model_version").order_by("eaten_at"),
    }


def daily_series(user, start: date, days: int = 7) -> list[dict]:
    end = start + timedelta(days=days - 1)
    rows = (
        MealLog.objects.filter(user=user, eaten_date__range=(start, end))
        .values("eaten_date")
        .annotate(**{n: Sum(n) for n in NUTRIENTS}, count=Count("id"))
        .order_by("eaten_date")
    )
    by_day = {r["eaten_date"]: r for r in rows}
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        r = by_day.get(d, {})
        series.append({"date": d, **{n: round(r.get(n) or 0, 1) for n in NUTRIENTS}, "count": r.get("count", 0)})
    return series


def period_summary(user, start: date, days: int = 7) -> dict:
    series = daily_series(user, start, days)
    logged = [d for d in series if d["count"]]
    total = {n: round(sum(d[n] for d in series), 1) for n in NUTRIENTS}
    return {
        "series": series,
        "total": total,
        "days_logged": len(logged),
        "avg_kcal": round(total["kcal"] / len(logged)) if logged else 0,
        "meal_count": sum(d["count"] for d in series),
    }


def top_foods(user, start: date, end: date, limit: int = 5) -> list[dict]:
    return list(
        MealLog.objects.filter(user=user, eaten_date__range=(start, end))
        .values("food_id", "food__name_vi")
        .annotate(times=Count("id"), kcal=Sum("kcal"))
        .order_by("-times", "-kcal")[:limit]
    )


def meal_type_breakdown(user, start: date, end: date) -> list[dict]:
    labels = dict(MealLog.MealType.choices)
    rows = (
        MealLog.objects.filter(user=user, eaten_date__range=(start, end))
        .values("meal_type")
        .annotate(kcal=Sum("kcal"))
    )
    by_type = {r["meal_type"]: r["kcal"] for r in rows}
    return [{"meal_type": k, "label": labels[k], "kcal": round(by_type.get(k) or 0, 1)} for k in labels]
