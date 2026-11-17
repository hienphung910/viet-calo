from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import F

from app.models import FeedbackImage


@dataclass
class ExportResult:
    exported: Counter = field(default_factory=Counter)
    missing: list[int] = field(default_factory=list)
    skipped_inactive: int = 0
    dry_run: bool = False

    @property
    def total(self) -> int:
        return sum(self.exported.values())


def exported_path(fb: FeedbackImage, label: str | None = None, dest: Path | None = None) -> Path:
    dest = Path(dest or settings.FEEDBACK_EXPORT_DIR)
    return dest / (label or fb.true_food.class_label) / f"feedback_{fb.pk}.jpg"


def unexport(fb: FeedbackImage, label: str | None = None) -> bool:
    path = exported_path(fb, label)
    if path.exists():
        path.unlink()
        return True
    return False


def exportable(queryset=None, only_corrected: bool = False):
    qs = (queryset if queryset is not None else FeedbackImage.objects.all()).filter(
        user_consented=True, used_in_training=False
    )
    if only_corrected:
        qs = qs.exclude(predicted_label="").exclude(predicted_label=F("true_food__class_label"))
    return qs.select_related("true_food").order_by("pk")


def export_feedback(dest: Path, queryset=None, only_corrected: bool = False, dry_run: bool = False) -> ExportResult:
    result = ExportResult(dry_run=dry_run)
    done_ids = []
    for fb in exportable(queryset, only_corrected):
        if not fb.true_food.is_active:
            result.skipped_inactive += 1
            continue
        name = fb.image_path.name
        if not name or not default_storage.exists(name):
            result.missing.append(fb.pk)
            continue
        label = fb.true_food.class_label
        if not dry_run:
            target = exported_path(fb, dest=dest)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                with default_storage.open(name, "rb") as f:
                    target.write_bytes(f.read())
            done_ids.append(fb.pk)
        result.exported[label] += 1

    if done_ids:
        FeedbackImage.objects.filter(pk__in=done_ids).update(used_in_training=True)
    return result
