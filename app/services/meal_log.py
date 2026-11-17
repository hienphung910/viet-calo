from django.db import transaction
from django.utils import timezone

from app.models import FeedbackImage
from app.models import Food
from app.services.images import copy_image

from app.models import MealLog


@transaction.atomic
def create_meal_log(
    *,
    user,
    food: Food,
    grams: float,
    meal_type: str,
    image_path: str = "",
    model_version_id: int | None = None,
    predicted_label: str = "",
    consent: bool = False,
    eaten_at=None,
) -> MealLog:
    log = MealLog.objects.create(
        user=user,
        food=food,
        model_version_id=model_version_id,
        image_path=image_path,
        meal_type=meal_type,
        portion_g=grams,
        **food.nutrition_for(grams),
        predicted_label=predicted_label,
        eaten_at=eaten_at or timezone.now(),
    )
    if consent and image_path:
        FeedbackImage.objects.create(
            meal_log=log,
            true_food=food,
            image_path=copy_image(image_path, "feedback"),
            predicted_label=predicted_label,
            user_consented=True,
        )
    return log


@transaction.atomic
def update_meal_log(log: MealLog, *, food: Food, grams: float, meal_type: str, eaten_at) -> MealLog:
    log.food = food
    log.portion_g = grams
    for key, value in food.nutrition_for(grams).items():
        setattr(log, key, value)
    log.meal_type = meal_type
    log.eaten_at = eaten_at
    log.save()

    fb = FeedbackImage.objects.filter(meal_log=log, used_in_training=False).first()
    if fb and fb.true_food_id != food.pk:
        fb.true_food = food
        fb.save(update_fields=["true_food"])
    return log


def delete_meal_log(log: MealLog):
    image_name = log.image_path.name if log.image_path else ""
    log.delete()
    if image_name:
        transaction.on_commit(lambda: log.image_path.storage.delete(image_name))
