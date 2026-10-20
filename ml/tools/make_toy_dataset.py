"""
Tạo một bộ ảnh tổng hợp nhỏ (hình học có màu) để chạy thử toàn bộ pipeline khi chưa có data thật.
Model học bộ này rất dễ, nên nếu accuracy thấp nghĩa là pipeline có lỗi.

    python -m ml.tools.make_toy_dataset --out data/raw_toy --per-class 60

Cố ý thêm 1 file ảnh hỏng và 1 ảnh trùng lặp để kiểm tra prepare_data.py phát hiện được.
"""
import argparse
import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from ml.common import ROOT

DEFAULT_CLASSES = ["pho", "banh_mi", "com_tam", "bun_bo_hue", "goi_cuon"]
COLORS = [(200, 60, 40), (220, 170, 60), (90, 160, 70), (60, 110, 200), (160, 80, 170)]


def draw_sample(cls_idx: int, rng: random.Random, size=(320, 280)) -> Image.Image:
    bg = tuple(rng.randint(200, 255) for _ in range(3))
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    w, h = size
    cx, cy = rng.randint(100, w - 100), rng.randint(90, h - 90)
    r = rng.randint(50, 80)
    color = tuple(max(0, min(255, c + rng.randint(-30, 30))) for c in COLORS[cls_idx % len(COLORS)])
    shape = cls_idx % 5
    if shape == 0:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    elif shape == 1:
        d.rectangle([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=color)
    elif shape == 2:
        d.polygon([(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)], fill=color)
    elif shape == 3:
        for i in range(-r, r, 16):
            d.line([(cx + i, cy - r), (cx + i, cy + r)], fill=color, width=7)
    else:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=14)
    # Nhiễu: vài chấm ngẫu nhiên để ảnh không giống hệt nhau.
    for _ in range(40):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        d.point((x, y), fill=tuple(rng.randint(0, 255) for _ in range(3)))
    return img


def make_toy_dataset(out: Path, classes=DEFAULT_CLASSES, per_class=60, seed=0):
    rng = random.Random(seed)
    if out.exists():
        shutil.rmtree(out)
    for idx, label in enumerate(classes):
        folder = out / label
        folder.mkdir(parents=True)
        for i in range(per_class):
            draw_sample(idx, rng).save(folder / f"{label}_{i:03d}.jpg", quality=90)
    # Ảnh hỏng + ảnh trùng lặp (để test bước kiểm tra dữ liệu).
    (out / classes[0] / "broken.jpg").write_bytes(b"day khong phai anh")
    shutil.copy(out / classes[0] / f"{classes[0]}_000.jpg", out / classes[0] / "duplicate.jpg")
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=ROOT / "data" / "raw_toy")
    p.add_argument("--per-class", type=int, default=60)
    p.add_argument("--classes", default=",".join(DEFAULT_CLASSES))
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    make_toy_dataset(args.out, args.classes.split(","), args.per_class, args.seed)
    print(f"Đã tạo dữ liệu thử tại {args.out}")


if __name__ == "__main__":
    main()
