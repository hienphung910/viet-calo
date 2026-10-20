"""
Truy vấn thống kê nhật ký ăn uống. Tất cả viết bằng Django ORM (không raw SQL) nên chạy được
trên cả MySQL lẫn SQLite. SQL tương đương được ghi trong docs/database.md.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Sum

from .models import MealLog

NUTRIENTS = ("kcal", "protein_g", "carb_g", "fat_g")


def week_start(d: date) -> date:
    """Thứ Hai của tuần chứa ngày d."""
    return d - timedelta(days=d.weekday())


def _totals(qs) -> dict:
    agg = qs.aggregate(**{n: Sum(n) for n in NUTRIENTS}, count=Count("id"))
    return {n: round(agg[n] or 0, 1) for n in NUTRIENTS} | {"count": agg["count"]}


@dataclass
class TargetStatus:
    """So sánh lượng kcal với mục tiêu."""

    kcal: float
    target: int

    @property
    def percent(self) -> int:
        return round(self.kcal / self.target * 100) if self.target else 0

    @property
    def remaining(self) -> float:
        return round(self.target - self.kcal, 1)

    @property
    def over_by(self) -> float:
        """Số kcal vượt mục tiêu (0 nếu chưa vượt)."""
        return max(0.0, -self.remaining)

    @property
    def level(self) -> str:
        """under: < 90% mục tiêu, ok: 90–110%, over: > 110%. So sánh tỷ lệ chính xác (không làm tròn),
        giống hệt màu cột trên biểu đồ tuần."""
        ratio = self.kcal / self.target if self.target else 0
        if ratio < 0.9:
            return "under"
        return "ok" if ratio <= 1.1 else "over"


def day_summary(user, day: date) -> dict:
    """
    Tổng dinh dưỡng một ngày + danh sách bữa ăn.
    SQL: SELECT SUM(kcal), SUM(protein_g), ... FROM meal_logs WHERE user_id=? AND eaten_date=?
    """
    qs = MealLog.objects.filter(user=user, eaten_date=day)
    totals = _totals(qs)
    return {
        "date": day,
        "totals": totals,
        "target": TargetStatus(totals["kcal"], user.daily_calorie_target),
        "logs": qs.select_related("food", "model_version").order_by("eaten_at"),
    }


def daily_series(user, start: date, days: int = 7) -> list[dict]:
    """
    Tổng dinh dưỡng theo từng ngày trong [start, start + days). Ngày không ăn gì vẫn có dòng = 0.
    SQL: SELECT eaten_date, SUM(kcal), ..., COUNT(*) FROM meal_logs
         WHERE user_id=? AND eaten_date BETWEEN ? AND ? GROUP BY eaten_date ORDER BY eaten_date
    """
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
    """Tổng hợp một khoảng (tuần): tổng, trung bình/ngày có ăn, số ngày vượt mục tiêu."""
    series = daily_series(user, start, days)
    logged = [d for d in series if d["count"]]
    target = user.daily_calorie_target
    total = {n: round(sum(d[n] for d in series), 1) for n in NUTRIENTS}
    return {
        "series": series,
        "total": total,
        "days_logged": len(logged),
        # Chỉ chia cho số ngày có ghi nhật ký: ngày quên ghi không kéo trung bình xuống 0.
        "avg_kcal": round(total["kcal"] / len(logged)) if logged else 0,
        "days_over": sum(TargetStatus(d["kcal"], target).level == "over" for d in logged),
        "days_ok": sum(TargetStatus(d["kcal"], target).level == "ok" for d in logged),
    }


def top_foods(user, start: date, end: date, limit: int = 5) -> list[dict]:
    """
    Món ăn nhiều nhất trong khoảng thời gian (theo số lần, rồi theo tổng kcal).
    SQL: SELECT f.name_vi, COUNT(*) AS times, SUM(m.kcal) AS kcal FROM meal_logs m JOIN foods f ON f.id=m.food_id
         WHERE m.user_id=? AND m.eaten_date BETWEEN ? AND ?
         GROUP BY f.id, f.name_vi ORDER BY times DESC, kcal DESC LIMIT 5
    """
    return list(
        MealLog.objects.filter(user=user, eaten_date__range=(start, end))
        .values("food_id", "food__name_vi")
        .annotate(times=Count("id"), kcal=Sum("kcal"))
        .order_by("-times", "-kcal")[:limit]
    )


def meal_type_breakdown(user, start: date, end: date) -> list[dict]:
    """
    kcal theo bữa (sáng/trưa/tối/phụ).
    SQL: SELECT meal_type, SUM(kcal) FROM meal_logs WHERE user_id=? AND eaten_date BETWEEN ? AND ? GROUP BY meal_type
    """
    labels = dict(MealLog.MealType.choices)
    rows = (
        MealLog.objects.filter(user=user, eaten_date__range=(start, end))
        .values("meal_type")
        .annotate(kcal=Sum("kcal"))
    )
    by_type = {r["meal_type"]: r["kcal"] for r in rows}
    return [{"meal_type": k, "label": labels[k], "kcal": round(by_type.get(k) or 0, 1)} for k in labels]
