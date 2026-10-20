"""
Luồng nhận diện:
  1. GET/POST /scan/          upload ảnh -> lưu ảnh -> dự đoán -> lưu kết quả tạm trong session
  2. GET/POST /scan/<token>/  hiện top-3, người dùng chọn/sửa món + khẩu phần -> lưu MealLog
Kết quả tạm để trong session (không ghi CSDL) cho tới khi người dùng xác nhận.
"""
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.diary.forms import guess_meal_type
from apps.diary.services import create_meal_log
from apps.foods.models import Food, vi_sort_key

from . import stats
from .forms import ConfirmForm, UploadForm
from .images import open_upload, save_image
from .services import ModelLoadError, NoActiveModel, get_service

UPLOAD_TIPS = [
    "Chụp từ trên xuống, món chiếm phần lớn khung",
    "Đủ ánh sáng, tránh ngược sáng",
    "Mỗi ảnh chỉ một món",
    "Không có camera? Dùng tab “Chọn ảnh có sẵn”",
]
PENDING_KEY = "pending_scans"
MAX_PENDING = 5


def _run_prediction(uploaded_file, save: bool = True):
    """
    Ảnh upload -> (đường dẫn ảnh đã lưu hoặc None, PredictionResult). Dùng chung cho trang web và API.
    save=False: chỉ dự đoán, không ghi file (nhận diện trực tiếp từ camera gửi ảnh liên tục).
    """
    image = open_upload(uploaded_file)
    result = get_service().predict(image)
    return (save_image(image, "uploads") if save else None), result


def _upload_context(form) -> dict:
    # Ngưỡng tin cậy cho phần nhận diện trực tiếp bằng camera (tô màu kết quả).
    return {"form": form, "threshold": settings.CONFIDENCE_THRESHOLD, "tips": UPLOAD_TIPS}


@login_required
def scan_upload(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            image_path, result = _run_prediction(form.cleaned_data["image"])
        except (NoActiveModel, ModelLoadError) as e:
            messages.error(request, f"Chưa nhận diện được: {e}")
            return render(request, "recognition/upload.html", _upload_context(form))

        token = secrets.token_urlsafe(8)
        pending = request.session.get(PENDING_KEY, {})
        pending[token] = {
            "image": image_path,
            "model_version_id": result.model_version_id,
            "model_version": result.model_version,
            "top3": [c.as_dict() for c in result.candidates],
        }
        # Chỉ giữ vài kết quả gần nhất trong session.
        request.session[PENDING_KEY] = dict(list(pending.items())[-MAX_PENDING:])
        return redirect("recognition:confirm", token=token)
    return render(request, "recognition/upload.html", _upload_context(form))


@login_required
def scan_confirm(request, token):
    pending = request.session.get(PENDING_KEY, {}).get(token)
    if pending is None:
        raise Http404("Kết quả nhận diện đã hết hạn, hãy tải ảnh lên lại.")

    foods = Food.objects.in_bulk([c["label"] for c in pending["top3"]], field_name="class_label")
    candidates = [
        {**c, "food": foods.get(c["label"]), "percent": round(c["confidence"] * 100)} for c in pending["top3"]
    ]
    top1 = candidates[0]
    is_confident = top1["confidence"] >= settings.CONFIDENCE_THRESHOLD and top1["food"] is not None
    candidate_ids = [c["food"].pk for c in candidates if c["food"]]

    initial = {
        "choice": str(top1["food"].pk) if is_confident else "",
        "portion_choice": "medium",
        "meal_type": guess_meal_type(timezone.localtime().hour),
        "consent": True,
    }
    form = ConfirmForm(request.POST or None, initial=initial, candidate_food_ids=candidate_ids)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        log = create_meal_log(
            user=request.user,
            food=d["food"],
            grams=d["grams"],
            meal_type=d["meal_type"],
            image_path=pending["image"],
            model_version_id=pending["model_version_id"],
            top3=pending["top3"],
            consent=d["consent"],
        )
        sessions = request.session[PENDING_KEY]
        sessions.pop(token, None)
        request.session.modified = True
        messages.success(request, f"Đã lưu {log.food.name_vi} ({log.portion_g:g} g, {log.kcal:.0f} kcal).")
        return redirect("diary:home")

    # Sắp xếp trong Python theo chữ bỏ dấu: ORDER BY của SQLite so sánh mã Unicode nên "Bánh đúc" bị xếp sau "Bánh xèo".
    all_foods = sorted(Food.objects.filter(is_active=True), key=lambda f: vi_sort_key(f.name_vi))
    return render(request, "recognition/confirm.html", {
        "form": form,
        "pending": pending,
        "candidates": candidates,
        "is_confident": is_confident,
        "threshold_percent": round(settings.CONFIDENCE_THRESHOLD * 100),
        "all_foods": all_foods,
        "multipliers": settings.PORTION_MULTIPLIERS,
        "macro_names": [("protein", "Protein"), ("carb", "Carb"), ("fat", "Fat")],
        # Dữ liệu cho JavaScript tính thử kcal trên trình duyệt.
        "foods_data": {
            str(f.pk): {"kcal": f.kcal_per_100g, "p": f.protein, "c": f.carb, "f": f.fat,
                        "portion": f.default_portion_g}
            for f in all_foods
        },
    })


@login_required
@require_POST
def api_predict(request):
    """
    API JSON: POST multipart field `image` -> top-3. Không lưu nhật ký.
    ?preview=1: không lưu ảnh lên đĩa (camera gửi khung hình liên tục để nhận diện trực tiếp,
    lưu lại sẽ sinh hàng trăm file rác).
    """
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    try:
        image_path, result = _run_prediction(form.cleaned_data["image"], save=request.GET.get("preview") != "1")
    except (NoActiveModel, ModelLoadError) as e:
        return JsonResponse({"error": str(e)}, status=503)
    return JsonResponse({
        "model_version": result.model_version,
        "is_confident": result.is_confident,
        "threshold": settings.CONFIDENCE_THRESHOLD,
        "image": image_path,
        "predictions": [
            {
                **c.as_dict(),
                "name_vi": c.food.name_vi if c.food else None,
                "kcal_per_100g": c.food.kcal_per_100g if c.food else None,
                "default_portion_g": c.food.default_portion_g if c.food else None,
            }
            for c in result.candidates
        ],
    })


@staff_member_required
def model_stats(request):
    """Thống kê độ chính xác thực tế của model + so sánh các phiên bản (chỉ admin)."""
    comparison = stats.model_comparison()
    buckets = stats.confidence_buckets()
    pct = lambda v: round(v * 100, 1) if v is not None else None  # noqa: E731
    chart = {
        "versions": [r["mv"].version for r in comparison],
        "val": [pct(r["mv"].val_accuracy) for r in comparison],
        "test": [pct(r["mv"].test_accuracy) for r in comparison],
        "real_top1": [pct(r["real_top1"]) for r in comparison],
        "real_top3": [pct(r["real_top3"]) for r in comparison],
        "bucket_labels": [b["label"] for b in buckets],
        "bucket_acc": [pct(b["acc"]) for b in buckets],
        "bucket_n": [b["n"] for b in buckets],
        "threshold": settings.CONFIDENCE_THRESHOLD * 100,
    }
    service = get_service()
    return render(request, "recognition/stats.html", {
        "overview": stats.overview(),
        "comparison": comparison,
        "buckets": buckets,
        "confusions": stats.top_confusions(),
        "per_food": stats.per_food_accuracy()[:10],
        "feedback": stats.feedback_summary(),
        "popular": stats.popular_foods(),
        "chart": chart,
        "loaded_version": service.current_version,
    })


@staff_member_required
@require_POST
def reload_model(request):
    """
    Nạp lại model active ngay lập tức (không cần restart server). Chỉ admin.
    Gọi từ API -> trả JSON; gọi từ nút trong trang (có field `next`) -> thông báo rồi quay lại trang đó.
    """
    next_url = request.POST.get("next")
    if next_url and not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = None
    try:
        mv = get_service().reload()
    except (NoActiveModel, ModelLoadError) as e:
        if next_url:
            messages.error(request, f"Không nạp được model: {e}")
            return redirect(next_url)
        return JsonResponse({"ok": False, "error": str(e)}, status=503)
    if next_url:
        messages.success(request, f"Đã nạp lại model {mv.version} ({mv.num_classes} lớp).")
        return redirect(next_url)
    return JsonResponse({"ok": True, "model_version": mv.version, "num_classes": mv.num_classes})
