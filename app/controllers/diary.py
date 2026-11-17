from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from app.models import Food

from app.services import diary_stats as stats
from app.forms.diary import MealForm, guess_meal_type, initial_portion
from app.models import MealLog
from app.services.meal_log import create_meal_log, delete_meal_log, update_meal_log

WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def _parse_date(value: str | None) -> date:
    try:
        return date.fromisoformat(value) if value else timezone.localdate()
    except ValueError:
        return timezone.localdate()


KCAL_PER_GRAM = {"Protein": 4, "Carb": 4, "Fat": 9}


def _macro_split(totals: dict) -> list[dict]:
    grams = {"Protein": totals["protein_g"], "Carb": totals["carb_g"], "Fat": totals["fat_g"]}
    energy = {n: g * KCAL_PER_GRAM[n] for n, g in grams.items()}
    total_energy = sum(energy.values()) or 1
    return [
        {"name": n, "key": n.lower(), "grams": round(grams[n]), "percent": round(energy[n] / total_energy * 100)}
        for n in grams
    ]


def _greeting(hour: int) -> str:
    if hour < 11:
        return "Chào buổi sáng"
    if hour < 14:
        return "Chào buổi trưa"
    if hour < 18:
        return "Chào buổi chiều"
    return "Chào buổi tối"


@login_required
def home(request):
    day = _parse_date(request.GET.get("date"))
    summary = stats.day_summary(request.user, day)
    groups = []
    for value, label in MealLog.MealType.choices:
        logs = [log for log in summary["logs"] if log.meal_type == value]
        if logs:
            groups.append({"label": label, "logs": logs, "kcal": round(sum(log.kcal for log in logs))})
    return render(request, "diary/home.html", {
        **summary,
        "groups": groups,
        "macros": _macro_split(summary["totals"]),
        "greeting": _greeting(timezone.localtime().hour),
        "display_name": request.user.first_name or request.user.email.split("@")[0],
        "prev_day": day - timedelta(days=1),
        "next_day": day + timedelta(days=1),
        "is_today": day == timezone.localdate(),
        "week_start": stats.week_start(day),
    })


@login_required
def week(request):
    start = stats.week_start(_parse_date(request.GET.get("start")))
    end = start + timedelta(days=6)
    summary = stats.period_summary(request.user, start)
    chart = {
        "labels": [f"{WEEKDAYS[d['date'].weekday()]} {d['date']:%d/%m}" for d in summary["series"]],
        "short": [WEEKDAYS[d["date"].weekday()] for d in summary["series"]],
        "dates": [d["date"].isoformat() for d in summary["series"]],
        "kcal": [d["kcal"] for d in summary["series"]],
        "macros": [round(summary["total"]["protein_g"] * 4), round(summary["total"]["carb_g"] * 4),
                   round(summary["total"]["fat_g"] * 9)],
    }
    top_foods = stats.top_foods(request.user, start, end)
    max_food = max((f["kcal"] for f in top_foods), default=0) or 1
    for f in top_foods:
        f["bar"] = round(f["kcal"] / max_food * 100)
    by_meal = stats.meal_type_breakdown(request.user, start, end)
    max_meal = max((m["kcal"] for m in by_meal), default=0) or 1
    for m in by_meal:
        m["bar"] = round(m["kcal"] / max_meal * 100)
    return render(request, "diary/week.html", {
        **summary,
        "start": start,
        "end": end,
        "chart": chart,
        "top_foods": top_foods,
        "by_meal": by_meal,
        "macros": _macro_split(summary["total"]),
        "prev_week": start - timedelta(days=7),
        "next_week": start + timedelta(days=7),
        "is_current": start == stats.week_start(timezone.localdate()),
    })


@login_required
def meal_add(request):
    day = _parse_date(request.GET.get("date"))
    now = timezone.localtime()
    at = now if day == now.date() else timezone.make_aware(datetime.combine(day, time(12, 0)))
    form = MealForm(request.POST or None, initial={
        "portion_choice": "medium", "meal_type": guess_meal_type(at.hour), "eaten_at": at,
    })
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        log = create_meal_log(user=request.user, food=d["food"], grams=d["grams"], meal_type=d["meal_type"],
                              eaten_at=d["eaten_at"])
        messages.success(request, f"Đã thêm {log.food.name_vi} ({log.kcal:.0f} kcal).")
        return redirect(_day_url(log))
    return render(request, "diary/meal_form.html", {"form": form, "title": "Thêm món thủ công", **_js_data()})


@login_required
def meal_edit(request, pk):
    log = get_object_or_404(MealLog.objects.select_related("food"), pk=pk, user=request.user)
    form = MealForm(
        request.POST or None,
        current_food=log.food,
        initial={"food": log.food, "meal_type": log.meal_type, "eaten_at": timezone.localtime(log.eaten_at),
                 **initial_portion(log.food, log.portion_g)},
    )
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        update_meal_log(log, food=d["food"], grams=d["grams"], meal_type=d["meal_type"], eaten_at=d["eaten_at"])
        messages.success(request, f"Đã cập nhật {log.food.name_vi} ({log.kcal:.0f} kcal).")
        return redirect(_day_url(log))
    return render(request, "diary/meal_form.html", {"form": form, "log": log, "title": "Sửa bữa ăn", **_js_data()})


@login_required
def meal_delete(request, pk):
    log = get_object_or_404(MealLog.objects.select_related("food"), pk=pk, user=request.user)
    if request.method == "POST":
        url = _day_url(log)
        name = log.food.name_vi
        delete_meal_log(log)
        messages.success(request, f"Đã xóa {name}.")
        return redirect(url)
    return render(request, "diary/meal_confirm_delete.html", {"log": log})


def _day_url(log: MealLog) -> str:
    return f"{reverse('diary:home')}?date={log.eaten_date.isoformat()}"


def _js_data() -> dict:
    return {
        "foods_data": {str(f.pk): {"kcal": f.kcal_per_100g, "p": f.protein, "c": f.carb, "f": f.fat,
                                   "portion": f.default_portion_g} for f in Food.objects.all()},
        "multipliers": settings.PORTION_MULTIPLIERS,
    }
