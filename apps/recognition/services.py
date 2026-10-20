"""
PredictionService: lớp duy nhất trong web làm việc với PyTorch.

- Model được nạp MỘT lần cho mỗi process (không nạp lại ở mỗi request).
- Hot-reload: cứ MODEL_CHECK_INTERVAL giây, service hỏi CSDL "model nào đang active?".
  Admin đổi model -> mọi process tự nạp model mới, không cần restart server.
  reload() ép nạp lại ngay (dùng cho endpoint /recognition/reload/).
- View chỉ gọi get_service().predict(image) -> không phụ thuộc PyTorch, dễ test bằng model giả.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from apps.foods.models import Food

from .models import ModelVersion

logger = logging.getLogger(__name__)


class NoActiveModel(Exception):
    """Chưa có model nào được kích hoạt trong bảng model_versions."""


class ModelLoadError(Exception):
    """Có model active nhưng không nạp được file (mất file, file hỏng...)."""


@dataclass
class Candidate:
    label: str
    confidence: float
    food: Food | None  # None nếu nhãn chưa có trong bảng foods

    def as_dict(self):
        return {"label": self.label, "confidence": round(self.confidence, 4)}


@dataclass
class PredictionResult:
    model_version_id: int
    model_version: str
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def top1(self) -> Candidate:
        return self.candidates[0]

    @property
    def is_confident(self) -> bool:
        return self.top1.confidence >= settings.CONFIDENCE_THRESHOLD


def _default_loader(path: Path, device):
    from ml.common import load_checkpoint  # import muộn: lệnh manage.py khác không phải nạp torch

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

    # ---------- nạp model ----------
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
        # Tiền xử lý giống hệt lúc evaluate (cùng hàm build_transforms).
        self._transform = build_transforms(meta["img_size"], train=False)
        logger.info("Đã nạp model %s (%d lớp)", mv.version, len(meta["class_list"]))

    def ensure_loaded(self, force: bool = False) -> ModelVersion:
        """Nạp model active nếu chưa nạp hoặc nếu model active trong CSDL đã thay đổi."""
        now = time.monotonic()
        if not force and self._model is not None and now - self._last_check < self._check_interval:
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

    # ---------- dự đoán ----------
    def predict(self, image, k: int = 3) -> PredictionResult:
        """`image`: ảnh PIL (đã xoay EXIF, RGB). Trả về top-k kèm Food tương ứng."""
        import torch

        from ml.common import predict_topk

        mv = self.ensure_loaded()
        model, meta, transform = self._model, self._meta, self._transform  # giữ tham chiếu nếu đang reload
        device = next(model.parameters()).device
        x = transform(image).unsqueeze(0).to(device)
        with torch.inference_mode():
            probs, idx = predict_topk(model, x, k)
        labels = [meta["class_list"][i] for i in idx[0].tolist()]
        foods = Food.objects.in_bulk(labels, field_name="class_label")
        return PredictionResult(
            model_version_id=mv.pk,
            model_version=mv.version,
            candidates=[Candidate(lbl, p, foods.get(lbl)) for lbl, p in zip(labels, probs[0].tolist())],
        )


_service: PredictionService | None = None
_service_lock = threading.Lock()


def get_service() -> PredictionService:
    """Một PredictionService dùng chung cho cả process."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = PredictionService()
    return _service


def warm_up():
    """Nạp model ngay khi server khởi động (gọi từ config/wsgi.py). Lỗi thì chỉ ghi log, web vẫn chạy."""
    try:
        mv = get_service().ensure_loaded()
        logger.warning("Model đang dùng: %s", mv.version)
    except (NoActiveModel, ModelLoadError) as e:
        logger.warning("Chưa nạp được model khi khởi động: %s", e)
