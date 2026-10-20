"""Nghiệp vụ nhật ký ăn uống: tạo bữa ăn từ kết quả nhận diện."""
from django.db import transaction
from django.utils import timezone

from apps.feedback.models import FeedbackImage
from apps.foods.models import Food
from apps.recognition.images import copy_image

from .models import MealLog


@transaction.atomic
def create_meal_log(
    *,
    user,
    food: Food,
    grams: float,
    meal_type: str,
    image_path: str = "",
    model_version_id: int | None = None,
    top3: list[dict] | None = None,
    consent: bool = False,
    eaten_at=None,
) -> MealLog:
    """
    Lưu một bữa ăn. kcal/macro = giá trị trên 100g x gram / 100, lưu snapshot vào meal_logs.
    Có ảnh + người dùng đồng ý -> tạo thêm FeedbackImage với nhãn đúng = món người dùng xác nhận.
    Cả hai được ghi trong cùng một transaction.
    """
    top3 = top3 or []
    predicted = top3[0] if top3 else None
    log = MealLog.objects.create(
        user=user,
        food=food,
        model_version_id=model_version_id,
        image_path=image_path,
        meal_type=meal_type,
        portion_g=grams,
        **food.nutrition_for(grams),
        predicted_label=predicted["label"] if predicted else "",
        confidence=predicted["confidence"] if predicted else None,
        top3_predictions=top3,
        # Đoán sai = món cuối cùng khác top-1 của model (kể cả khi đúng món nằm trong top-3).
        was_corrected=bool(predicted) and predicted["label"] != food.class_label,
        eaten_at=eaten_at or timezone.now(),
    )
    if consent and image_path:
        FeedbackImage.objects.create(
            meal_log=log,
            true_food=food,
            image_path=copy_image(image_path, "feedback"),
            predicted_label=log.predicted_label,
            user_consented=True,
        )
    return log


@transaction.atomic
def update_meal_log(log: MealLog, *, food: Food, grams: float, meal_type: str, eaten_at) -> MealLog:
    """
    Sửa bữa ăn: tính lại snapshot dinh dưỡng theo bảng foods hiện tại.
    Đổi món sau khi lưu nghĩa là người dùng sửa nhãn -> cập nhật was_corrected và nhãn đúng của ảnh phản hồi
    (trừ khi ảnh đó đã được dùng để train).
    """
    log.food = food
    log.portion_g = grams
    for key, value in food.nutrition_for(grams).items():
        setattr(log, key, value)
    log.meal_type = meal_type
    log.eaten_at = eaten_at
    if log.predicted_label:
        log.was_corrected = log.predicted_label != food.class_label
    log.save()  # save() tự tính lại eaten_date

    fb = FeedbackImage.objects.filter(meal_log=log, used_in_training=False).first()
    if fb and fb.true_food_id != food.pk:
        fb.true_food = food
        fb.save(update_fields=["true_food"])
    return log


def delete_meal_log(log: MealLog):
    """
    Xóa bữa ăn và ảnh gốc của nó (quyền riêng tư: không giữ ảnh người dùng đã xóa).
    Ảnh phản hồi (nếu người dùng đã đồng ý) là bản sao riêng nên vẫn còn; meal_log_id của nó thành NULL.
    """
    image_name = log.image_path.name if log.image_path else ""
    log.delete()
    if image_name:
        # Xóa file sau khi transaction xóa dòng đã commit, để lỗi CSDL không làm mất ảnh.
        transaction.on_commit(lambda: log.image_path.storage.delete(image_name))
