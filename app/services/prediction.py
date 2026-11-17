import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from app.models import Food, ModelVersion

logger = logging.getLogger(__name__)


class NoActiveModel(Exception):
    pass


class ModelLoadError(Exception):
    pass


@dataclass
class PredictionResult:
    model_version_id: int
    model_version: str
    label: str
    food: Food | None


def _default_loader(path: Path, device):
    from ml.common import load_checkpoint

    return load_checkpoint(path, device)


class PredictionService:
    def __init__(self, loader=None, check_interval: float | None = None):
        self._loader = loader or _default_loader
        self._check_interval = settings.MODEL_CHECK_INTERVAL if check_interval is None else check_interval
        self._lock = threading.Lock()
        self._model = None
        self._meta = None
        self._transform = None
        self._version: ModelVersion | None = None
        self._last_check = 0.0

    @property
    def current_version(self) -> ModelVersion | None:
        return self._version

    def _device(self):
        import torch

        wanted = settings.ML_DEVICE
        if wanted == "auto":
            wanted = "cuda" if torch.cuda.is_available() else "cpu"
        return torch.device(wanted)

    def _load(self, mv: ModelVersion):
        from ml.common import build_transforms

        path = Path(mv.file_path)
        if not path.is_absolute():
            path = settings.BASE_DIR / path
        if not path.exists():
            raise ModelLoadError(f"Không tìm thấy file model {path} (phiên bản {mv.version})")
        try:
            model, meta = self._loader(path, self._device())
        except Exception as e:
            raise ModelLoadError(f"Lỗi nạp model {mv.version}: {e}") from e
        self._model, self._meta, self._version = model, meta, mv
        self._transform = build_transforms(meta["img_size"], train=False)
        logger.info("Đã nạp model %s (%d lớp)", mv.version, len(meta["class_list"]))

    def ensure_loaded(self, force: bool = False) -> ModelVersion:
        now = time.monotonic()
        recently_checked = now - self._last_check < self._check_interval
        if not force and self._model is not None and recently_checked:
            return self._version
        with self._lock:  # tránh 2 request cùng lúc nạp model 2 lần
            active = ModelVersion.objects.filter(is_active=True).first()
            self._last_check = now
            if active is None:
                self._model = self._version = None
                raise NoActiveModel("Chưa có model nào được kích hoạt. Train và chạy register_model --activate.")
            if force or self._version is None or self._version.pk != active.pk:
                self._load(active)
            return self._version

    def reload(self) -> ModelVersion:
        return self.ensure_loaded(force=True)

    def predict(self, image) -> PredictionResult:
        import torch

        mv = self.ensure_loaded()
        model, meta, transform = self._model, self._meta, self._transform
        device = next(model.parameters()).device
        x = transform(image).unsqueeze(0).to(device)
        with torch.inference_mode():
            idx = model(x).argmax(dim=1).item()
        label = meta["class_list"][idx]
        food = Food.objects.filter(class_label=label).first()
        return PredictionResult(mv.pk, mv.version, label, food)


_service: PredictionService | None = None
_service_lock = threading.Lock()


def get_service() -> PredictionService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = PredictionService()
    return _service


def warm_up():
    try:
        mv = get_service().ensure_loaded()
        logger.warning("Model đang dùng: %s", mv.version)
    except (NoActiveModel, ModelLoadError) as e:
        logger.warning("Chưa nạp được model khi khởi động: %s", e)
