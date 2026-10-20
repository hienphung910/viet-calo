"""
Chép dataset tải từ Kaggle vào data/raw/<class_label>/ với tên thư mục đã chuẩn hóa.

Dataset Kaggle thường có dạng:
    30VNFoods/Train/Banh beo/*.jpg
    30VNFoods/Validate/Banh beo/*.jpg
    30VNFoods/Test/Banh beo/*.jpg
Script gom tất cả về data/raw/banh_beo/ (prepare_data.py sẽ tự chia lại train/val/test theo seed của mình).

    python -m ml.tools.import_kaggle --src "D:/Downloads/30VNFoods"
    python -m ml.tools.import_kaggle --src ... --rename "Banh mi=banh_mi,Com tam=com_tam"
"""
import argparse
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path

from ml.common import IMAGE_EXTS, ROOT, read_nutrition_labels


def slugify(name: str) -> str:
    """'Bún bò Huế' -> 'bun_bo_hue'."""
    name = name.replace("đ", "d").replace("Đ", "D")
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")  # bỏ dấu
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", required=True, type=Path, help="Thư mục dataset đã giải nén")
    p.add_argument("--dst", default=ROOT / "data" / "raw", type=Path)
    p.add_argument("--rename", default="", help="Đổi tên thủ công: 'Ten goc=class_label,...'")
    p.add_argument("--nutrition", default=ROOT / "data" / "nutrition.csv", type=Path)
    args = p.parse_args()

    manual = dict(item.split("=", 1) for item in args.rename.split(",") if "=" in item)
    counts = Counter()

    # Thư mục lớp = thư mục trực tiếp chứa ảnh.
    for img in sorted(args.src.rglob("*")):
        if img.suffix.lower() not in IMAGE_EXTS or not img.is_file():
            continue
        folder = img.parent.name
        label = manual.get(folder, slugify(folder))
        # Thêm các thư mục phía trên (Train/Test...) vào tên file để không bị trùng khi gộp.
        prefix = "_".join(slugify(part) for part in img.relative_to(args.src).parts[:-2])
        dest = args.dst / label / (f"{prefix}_{img.name}" if prefix else img.name)
        if dest.exists():
            continue  # chạy lại nhiều lần không bị nhân bản
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(img, dest)
        counts[label] += 1

    known = read_nutrition_labels(args.nutrition)
    print(f"{'class_label':<22}{'số ảnh mới':>10}  trong nutrition.csv?")
    for label in sorted(counts):
        print(f"{label:<22}{counts[label]:>10}  {'có' if label in known else 'KHÔNG - thêm dòng CSV hoặc dùng --rename'}")
    print(f"Tổng: {sum(counts.values())} ảnh, {len(counts)} lớp -> {args.dst}")


if __name__ == "__main__":
    main()
