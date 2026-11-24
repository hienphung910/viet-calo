import logging
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

from app.forms.diary import guess_meal_type
from app.forms.recognition import ConfirmForm, UploadForm
from app.models import Food, vi_sort_key
from app.services.images import open_upload, save_image
from app.services.meal_log import create_meal_log
from app.services.prediction import ModelLoadError, NoActiveModel, get_service

UPLOAD_TIPS = [
    "Chụp từ trên xuống, món chiếm phần lớn khung",
    "Đủ ánh sáng, tránh ngược sáng",
    "Mỗi ảnh chỉ một món",
    "Không có camera? Dùng tab “Chọn ảnh có sẵn”",
]
PENDING_KEY = "pending_scans"
MAX_PENDING = 5

logger = logging.getLogger(__name__)


def _model_error_text(request, error: Exception) -> str:
    # lỗi nạp model có kèm đường dẫn file trên server và chi tiết lỗi: chỉ quản trị viên được thấy
    if isinstance(error, ModelLoadError) and not request.user.is_staff:
        logger.error("Không nạp được model: %s", error)
        return "Model nhận diện đang gặp lỗi, hãy báo quản trị viên."
    return str(error)


@login_required
def scan_upload(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        image = open_upload(form.cleaned_data["image"])
        try:
            result = get_service().predict(image)
        except (NoActiveModel, ModelLoadError) as e:
            messages.error(request, f"Chưa nhận diện được: {_model_error_text(request, e)}")
            return render(request, "recognition/upload.html", {"form": form, "tips": UPLOAD_TIPS})

        token = secrets.token_urlsafe(8)
        pending = request.session.get(PENDING_KEY, {})
        pending[token] = {
            "image": save_image(image, "uploads"),
            "model_version_id": result.model_version_id,
            "label": result.label,
        }
        request.session[PENDING_KEY] = dict(list(pending.items())[-MAX_PENDING:])
        return redirect("recognition:confirm", token=token)
    return render(request, "recognition/upload.html", {"form": form, "tips": UPLOAD_TIPS})


@login_required
def scan_confirm(request, token):
    pending = request.session.get(PENDING_KEY, {}).get(token)
    if pending is None:
        raise Http404("Kết quả nhận diện đã hết hạn, hãy tải ảnh lên lại.")

    predicted = Food.objects.filter(class_label=pending["label"], is_active=True).first()
    form = ConfirmForm(request.POST or None, initial={
        "food": predicted.pk if predicted else None,
        "portion_choice": "medium",
        "meal_type": guess_meal_type(timezone.localtime().hour),
        "consent": True,
    })
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        log = create_meal_log(
            user=request.user,
            food=d["food"],
            grams=d["grams"],
            meal_type=d["meal_type"],
            image_path=pending["image"],
            model_version_id=pending["model_version_id"],
            predicted_label=pending["label"],
            consent=d["consent"],
        )
        request.session[PENDING_KEY].pop(token, None)
        request.session.modified = True
        messages.success(request, f"Đã lưu {log.food.name_vi} ({log.portion_g:g} g, {log.kcal:.0f} kcal).")
        return redirect("diary:home")

    all_foods = sorted(Food.objects.filter(is_active=True), key=lambda f: vi_sort_key(f.name_vi))
    return render(request, "recognition/confirm.html", {
        "form": form,
        "pending": pending,
        "predicted": predicted,
        "all_foods": all_foods,
        "multipliers": settings.PORTION_MULTIPLIERS,
        "macro_names": [("protein", "Protein"), ("carb", "Carb"), ("fat", "Fat")],
        "foods_data": {
            str(f.pk): {"kcal": f.kcal_per_100g, "p": f.protein, "c": f.carb, "f": f.fat,
                        "portion": f.default_portion_g}
            for f in all_foods
        },
    })


@login_required
@require_POST
def api_predict(request):
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    image = open_upload(form.cleaned_data["image"])
    try:
        result = get_service().predict(image)
    except (NoActiveModel, ModelLoadError) as e:
        return JsonResponse({"error": _model_error_text(request, e)}, status=503)
    food = result.food
    return JsonResponse({
        "model_version": result.model_version,
        "image": None if request.GET.get("preview") == "1" else save_image(image, "uploads"),
        "label": result.label,
        "name_vi": food.name_vi if food else None,
        "kcal_per_100g": food.kcal_per_100g if food else None,
        "default_portion_g": food.default_portion_g if food else None,
    })


@staff_member_required
@require_POST
def reload_model(request):
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
