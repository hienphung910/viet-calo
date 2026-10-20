"""
Phần dùng chung cho train / evaluate / web (PredictionService).

Quan trọng: tiền xử lý ảnh lúc dự đoán trên web PHẢI giống hệt lúc đánh giá model.
Vì vậy build_transforms() và load_checkpoint() chỉ được định nghĩa ở đây.
"""
import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
import yaml
from torchvision import transforms

ROOT = Path(__file__).resolve().parent.parent
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load_config(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def get_device() -> torch.device:
    """GPU nếu có, không thì CPU."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def read_nutrition_labels(csv_path) -> set[str]:
    """Tập class_label có trong data/nutrition.csv (không cần Django)."""
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        return {row["class_label"].strip() for row in csv.DictReader(f)}


def load_image(src):
    """
    Mở ảnh -> xoay đúng chiều theo EXIF -> RGB. Dùng cho CẢ chuẩn bị dữ liệu lẫn dự đoán trên web:
    ảnh chụp dọc bằng điện thoại lưu pixel nằm ngang + cờ EXIF, không xoay thì model nhìn ảnh bị nghiêng.
    """
    from PIL import Image, ImageOps

    with Image.open(src) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def build_transforms(img_size: int, train: bool, aug: dict | None = None):
    """
    Train: augmentation ngẫu nhiên để model không học thuộc ảnh.
    Eval/dự đoán: resize cạnh ngắn rồi cắt giữa, không ngẫu nhiên.
    """
    normalize = transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD)
    if not train:
        return transforms.Compose([
            transforms.Resize(int(img_size * 256 / 224)),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            normalize,
        ])

    aug = aug or {}
    steps = [transforms.RandomResizedCrop(img_size, scale=tuple(aug.get("crop_scale", (0.6, 1.0))))]
    if aug.get("hflip", True):
        steps.append(transforms.RandomHorizontalFlip())
    if aug.get("rotation", 0):
        steps.append(transforms.RandomRotation(aug["rotation"]))
    cj = aug.get("color_jitter", 0)
    if cj:
        steps.append(transforms.ColorJitter(brightness=cj, contrast=cj, saturation=cj, hue=min(cj / 4, 0.1)))
    steps += [transforms.ToTensor(), normalize]
    if aug.get("random_erasing", 0):
        steps.append(transforms.RandomErasing(p=aug["random_erasing"], scale=(0.02, 0.15)))
    return transforms.Compose(steps)


def build_model(backbone: str, num_classes: int, pretrained: bool = True, drop_rate: float = 0.0):
    import timm  # import muộn để các script không cần timm vẫn chạy nhanh

    model = timm.create_model(backbone, pretrained=pretrained, num_classes=num_classes, drop_rate=drop_rate)
    # Khởi tạo lại lớp phân loại với trọng số nhỏ. Mặc định timm (EfficientNet/MobileNet) dùng
    # uniform(±1/sqrt(num_classes)): ít lớp -> logit ban đầu rất lớn, loss khởi đầu cao bất thường
    # (đo được 4.07 thay vì ln(5)=1.61) và model học chậm. Trọng số nhỏ -> bắt đầu từ dự đoán gần đều.
    head = model.get_classifier()
    if isinstance(head, torch.nn.Linear):
        torch.nn.init.normal_(head.weight, std=0.01)
        torch.nn.init.zeros_(head.bias)
    return model


def save_checkpoint(path, model, *, backbone: str, class_list: list[str], img_size: int, extra: dict | None = None):
    """Lưu trọng số + đủ thông tin để dựng lại model mà không cần file config."""
    torch.save(
        {
            "backbone": backbone,
            "class_list": class_list,
            "img_size": img_size,
            "state_dict": model.state_dict(),
            **(extra or {}),
        },
        path,
    )


def load_checkpoint(path, device=None):
    """Trả về (model ở chế độ eval, metadata). Dùng chung cho evaluate.py và web."""
    device = device or get_device()
    # weights_only=True: chỉ nạp tensor/kiểu cơ bản, không chạy code tùy ý trong file.
    ckpt = torch.load(path, map_location=device, weights_only=True)
    model = build_model(ckpt["backbone"], len(ckpt["class_list"]), pretrained=False)
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    meta = {k: v for k, v in ckpt.items() if k != "state_dict"}
    return model, meta


@torch.no_grad()
def predict_topk(model, batch: torch.Tensor, k: int = 3):
    """Trả về (xác suất top-k, chỉ số top-k) cho một batch ảnh đã qua transform."""
    probs = torch.softmax(model(batch), dim=1)
    k = min(k, probs.shape[1])
    return probs.topk(k, dim=1)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
