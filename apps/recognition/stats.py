"""
Thống kê độ chính xác của model trong THỰC TẾ, dựa trên phản hồi của người dùng:
mỗi bữa ăn do AI nhận diện lưu nhãn model đoán (predicted_label, top3_predictions) và món người dùng
xác nhận (food). Khác với val/test accuracy lúc train (đo trên ảnh Kaggle), đây là độ chính xác
trên ảnh thật người dùng chụp.

Tất cả viết bằng Django ORM; SQL tương đương xem docs/database.md.
"""
from collections import defaultdict

from django.conf import settings
from django.db.models import Avg, Case, Count, IntegerField, Q, Value, When

from apps.diary.models import MealLog
from apps.feedback.models import FeedbackImage

from .models import ModelVersion

CONF_BUCKETS = [0.2, 0.4, 0.6, 0.8]  # cận trên của các nhóm độ tin cậy; nhóm cuối là [0.8, 1]


def ai_logs():
    """Các bữa ăn được AI nhận diện (thêm thủ công thì predicted_label rỗng)."""
    return MealLog.objects.exclude(predicted_label="")


def _rate(part, whole):
    return round(part / whole, 4) if whole else None


def top3_hits() -> dict:
    """
    {model_version_id: (số lần món đúng nằm trong top-3, tổng)}.
    top3_predictions là JSON; truy vấn bên trong JSON khác nhau giữa MySQL và SQLite,
    nên phần này tính bằng Python trên các cột cần thiết.
    """
    hits = defaultdict(lambda: [0, 0])
    for mv_id, label, top3 in ai_logs().values_list("model_version_id", "food__class_label", "top3_predictions"):
        hits[mv_id][1] += 1
        hits[mv_id][0] += any(p.get("label") == label for p in top3 or [])
    return hits


def overview() -> dict:
    """
    SQL: SELECT COUNT(*), COUNT(CASE WHEN was_corrected = 0 THEN 1 END), AVG(confidence),
                COUNT(CASE WHEN confidence < :threshold THEN 1 END)
         FROM meal_logs WHERE predicted_label <> ''
    """
    t = settings.CONFIDENCE_THRESHOLD
    agg = ai_logs().aggregate(
        n=Count("id"),
        correct=Count("id", filter=Q(was_corrected=False)),
        avg_conf=Avg("confidence"),
        low=Count("id", filter=Q(confidence__lt=t)),
    )
    h = top3_hits()
    hit3, total3 = sum(v[0] for v in h.values()), sum(v[1] for v in h.values())
    return {
        **agg,
        "wrong": agg["n"] - agg["correct"],
        "top1_acc": _rate(agg["correct"], agg["n"]),
        "top3_acc": _rate(hit3, total3),
        "low_rate": _rate(agg["low"], agg["n"]),
        "threshold": t,
    }


def model_comparison() -> list[dict]:
    """
    So sánh các phiên bản model: độ chính xác lúc train (val/test) và độ chính xác thực tế.
    SQL: SELECT mv.version, mv.val_accuracy, mv.test_accuracy,
                COUNT(m.id) AS n, COUNT(CASE WHEN m.was_corrected = 0 THEN 1 END) AS correct, AVG(m.confidence)
         FROM model_versions mv LEFT JOIN meal_logs m ON m.model_version_id = mv.id AND m.predicted_label <> ''
         GROUP BY mv.id ORDER BY mv.trained_at
    """
    ai = Q(meal_logs__predicted_label__gt="")
    rows = ModelVersion.objects.annotate(
        n=Count("meal_logs", filter=ai),
        correct=Count("meal_logs", filter=ai & Q(meal_logs__was_corrected=False)),
        avg_conf=Avg("meal_logs__confidence", filter=ai),
        low=Count("meal_logs", filter=ai & Q(meal_logs__confidence__lt=settings.CONFIDENCE_THRESHOLD)),
    ).order_by("trained_at")
    hits = top3_hits()
    result = []
    for mv in rows:
        hit3, total3 = hits.get(mv.pk, (0, 0))
        result.append({
            "mv": mv,
            "n": mv.n,
            "real_top1": _rate(mv.correct, mv.n),
            "real_top3": _rate(hit3, total3),
            "avg_conf": round(mv.avg_conf, 4) if mv.avg_conf is not None else None,
            "low_rate": _rate(mv.low, mv.n),
        })
    return result


def confidence_buckets(model_version=None) -> list[dict]:
    """
    Độ chính xác theo nhóm độ tin cậy -> kiểm tra model "tự tin" có đáng tin không, và chọn ngưỡng.
    SQL: SELECT CASE WHEN confidence < 0.2 THEN 0 WHEN confidence < 0.4 THEN 1 ... ELSE 4 END AS bucket,
                COUNT(*), COUNT(CASE WHEN was_corrected = 0 THEN 1 END)
         FROM meal_logs WHERE predicted_label <> '' AND confidence IS NOT NULL GROUP BY bucket ORDER BY bucket
    """
    bucket = Case(
        *[When(confidence__lt=hi, then=Value(i)) for i, hi in enumerate(CONF_BUCKETS)],
        default=Value(len(CONF_BUCKETS)),
        output_field=IntegerField(),
    )
    qs = ai_logs().filter(confidence__isnull=False)
    if model_version is not None:
        qs = qs.filter(model_version=model_version)
    rows = {
        r["bucket"]: r
        for r in qs.annotate(bucket=bucket).values("bucket")
        .annotate(n=Count("id"), correct=Count("id", filter=Q(was_corrected=False))).order_by("bucket")
    }
    edges = [0.0, *CONF_BUCKETS, 1.0]
    out = []
    for i in range(len(edges) - 1):
        r = rows.get(i, {"n": 0, "correct": 0})
        out.append({"label": f"{edges[i]:.0%}–{edges[i + 1]:.0%}", "n": r["n"], "acc": _rate(r["correct"], r["n"])})
    return out


def top_confusions(limit: int = 10) -> list[dict]:
    """
    Cặp (model đoán, thực tế) hay nhầm nhất.
    SQL: SELECT m.predicted_label, f.class_label, f.name_vi, COUNT(*) AS n
         FROM meal_logs m JOIN foods f ON f.id = m.food_id
         WHERE m.was_corrected = 1 GROUP BY m.predicted_label, f.class_label, f.name_vi ORDER BY n DESC LIMIT 10
    """
    return list(
        ai_logs().filter(was_corrected=True)
        .values("predicted_label", "food__class_label", "food__name_vi")
        .annotate(n=Count("id")).order_by("-n")[:limit]
    )


def per_food_accuracy(min_n: int = 1) -> list[dict]:
    """Độ chính xác thực tế theo từng món (món thật = món người dùng xác nhận), món yếu nhất lên đầu."""
    rows = (
        ai_logs().values("food__class_label", "food__name_vi")
        .annotate(n=Count("id"), correct=Count("id", filter=Q(was_corrected=False)))
        .filter(n__gte=min_n)
    )
    out = [{**r, "acc": _rate(r["correct"], r["n"])} for r in rows]
    return sorted(out, key=lambda r: (r["acc"], -r["n"]))


def feedback_summary() -> dict:
    """Số ảnh phản hồi: tổng, đã đồng ý, đã dùng train, đang chờ xuất; và theo từng món."""
    agg = FeedbackImage.objects.aggregate(
        total=Count("id"),
        consented=Count("id", filter=Q(user_consented=True)),
        used=Count("id", filter=Q(used_in_training=True)),
        pending=Count("id", filter=Q(user_consented=True, used_in_training=False)),
    )
    by_food = list(
        FeedbackImage.objects.filter(user_consented=True)
        .values("true_food__name_vi")
        .annotate(n=Count("id"), pending=Count("id", filter=Q(used_in_training=False)))
        .order_by("-n")[:10]
    )
    return {**agg, "by_food": by_food}


def popular_foods(limit: int = 10) -> list[dict]:
    """Món được ăn nhiều nhất trên toàn hệ thống (mọi người dùng)."""
    return list(
        MealLog.objects.values("food__name_vi")
        .annotate(times=Count("id"), users=Count("user", distinct=True))
        .order_by("-times")[:limit]
    )
