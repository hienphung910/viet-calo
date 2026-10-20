"""
Chuẩn bị dữ liệu: data/raw/<class_label>/*.jpg  ->  data/processed/{train,val,test}/<class_label>/*.jpg

Các bước:
  1. Đối chiếu tên thư mục với data/nutrition.csv (mỗi lớp phải có dòng dinh dưỡng).
  2. Loại ảnh hỏng / quá nhỏ, loại ảnh trùng lặp (cùng nội dung file) để tránh rò rỉ train -> test.
  3. Chia 70/15/15 theo TỪNG lớp (stratified), seed cố định -> chạy lại ra đúng kết quả cũ.
  4. Resize cạnh ngắn về --size (mặc định 256), xoay đúng chiều theo EXIF, lưu JPEG.
  5. In thống kê, cảnh báo lớp ít ảnh / mất cân bằng; lưu stats.json, split.csv, bad_images.txt.

    python -m ml.prepare_data
    python -m ml.prepare_data --max-per-class 50 --classes pho,banh_mi,com_tam,bun_bo_hue,goi_cuon
"""
import argparse
import csv
import hashlib
import random
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ml.common import IMAGE_EXTS, ROOT, load_image, read_nutrition_labels, write_json

SPLITS = ("train", "val", "test")


@dataclass
class Checked:
    path: Path
    ok: bool
    reason: str = ""
    md5: str = ""


def check_image(path: Path, min_size: int) -> Checked:
    """Ảnh hợp lệ = mở được, giải mã được, cạnh ngắn >= min_size."""
    try:
        data = path.read_bytes()
        md5 = hashlib.md5(data).hexdigest()
        with Image.open(path) as im:
            im.verify()  # phát hiện file cụt / sai định dạng
        with Image.open(path) as im:
            im.load()
            if min(im.size) < min_size:
                return Checked(path, False, f"quá nhỏ {im.size}")
        return Checked(path, True, md5=md5)
    except Exception as e:  # noqa: BLE001 - mọi lỗi đọc ảnh đều coi là ảnh hỏng
        return Checked(path, False, f"lỗi đọc ảnh: {type(e).__name__}")


def resize_and_save(src: Path, dst: Path, size: int):
    im = load_image(src)  # xoay theo EXIF + RGB, giống hệt lúc dự đoán trên web
    w, h = im.size
    scale = size / min(w, h)
    if scale < 1:  # chỉ thu nhỏ, không phóng to
        im = im.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=90)


def split_counts(n: int, ratios: tuple[float, float, float]) -> tuple[int, int, int]:
    n_val = round(n * ratios[1])
    n_test = round(n * ratios[2])
    if n >= 3:  # lớp nào cũng có ít nhất 1 ảnh val và test
        n_val, n_test = max(1, n_val), max(1, n_test)
    return n - n_val - n_test, n_val, n_test


def prepare(
    raw: Path,
    out: Path,
    nutrition: Path,
    size: int = 256,
    ratios=(0.7, 0.15, 0.15),
    seed: int = 42,
    min_size: int = 64,
    min_images: int = 50,
    max_per_class: int | None = None,
    classes: list[str] | None = None,
    workers: int = 8,
) -> dict:
    if abs(sum(ratios) - 1) > 1e-6:
        raise SystemExit("Tổng tỷ lệ train/val/test phải bằng 1")
    class_dirs = sorted(d for d in raw.iterdir() if d.is_dir() and not d.name.startswith("."))
    if classes:
        class_dirs = [d for d in class_dirs if d.name in classes]
    if not class_dirs:
        raise SystemExit(f"Không có thư mục lớp nào trong {raw}")

    # 1. Đối chiếu với bảng dinh dưỡng: lớp không có dinh dưỡng thì web không tính được calo.
    known = read_nutrition_labels(nutrition)
    missing = [d.name for d in class_dirs if d.name not in known]
    if missing:
        raise SystemExit(
            "Các thư mục sau KHÔNG có dòng trong nutrition.csv: "
            + ", ".join(missing)
            + "\n-> Thêm dòng CSV (class_label trùng tên thư mục) hoặc đổi tên thư mục."
        )

    # 2. Kiểm tra ảnh (song song cho nhanh).
    files = {d.name: sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS) for d in class_dirs}
    with ThreadPoolExecutor(workers) as ex:
        checked = {lbl: list(ex.map(lambda p: check_image(p, min_size), paths)) for lbl, paths in files.items()}

    bad, seen_md5, stats = [], {}, {}
    plan = []  # (split, label, src, dst)
    for label, items in checked.items():
        good = []
        n_dup = 0
        for c in items:
            if not c.ok:
                bad.append((c.path, c.reason))
            elif c.md5 in seen_md5:
                n_dup += 1
                bad.append((c.path, f"trùng với {seen_md5[c.md5]}"))
            else:
                seen_md5[c.md5] = c.path.relative_to(raw).as_posix()
                good.append(c.path)

        # 3. Chia theo từng lớp. Seed riêng cho mỗi lớp -> thêm lớp mới không làm xáo trộn lớp cũ.
        rng = random.Random(f"{seed}-{label}")
        rng.shuffle(good)
        if max_per_class:
            good = good[:max_per_class]
        n_train, n_val, _ = split_counts(len(good), ratios)
        parts = {"train": good[:n_train], "val": good[n_train:n_train + n_val], "test": good[n_train + n_val:]}
        for split, paths in parts.items():
            for src in paths:
                # Đổi đuôi sang .jpg; giữ đuôi cũ trong tên để không trùng (a.png vs a.jpg).
                dst = out / split / label / f"{src.stem}_{src.suffix.lstrip('.').lower()}.jpg"
                plan.append((split, label, src, dst))
        stats[label] = {
            "total": len(items),
            "bad": sum(not c.ok for c in items),
            "duplicate": n_dup,
            **{s: len(p) for s, p in parts.items()},
        }

    # 4. Ghi ảnh. Xóa kết quả cũ để không lẫn ảnh của lần chạy trước.
    for split in SPLITS:
        shutil.rmtree(out / split, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda t: resize_and_save(t[2], t[3], size), plan))

    with open(out / "split.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "label", "source", "file"])
        for split, label, src, dst in plan:
            w.writerow([split, label, src.relative_to(raw).as_posix(), dst.relative_to(out).as_posix()])
    (out / "bad_images.txt").write_text(
        "\n".join(f"{p.relative_to(raw).as_posix()}\t{r}" for p, r in bad), encoding="utf-8"
    )

    # 5. Thống kê + cảnh báo.
    warnings = []
    usable = {lbl: s["train"] + s["val"] + s["test"] for lbl, s in stats.items()}
    for lbl, n in usable.items():
        if n < min_images:
            warnings.append(f"Lớp '{lbl}' chỉ có {n} ảnh dùng được (< {min_images})")
    lo, hi = min(usable.values()), max(usable.values())
    if lo and hi / lo > 3:
        warnings.append(
            f"Mất cân bằng: lớp nhiều nhất {hi} ảnh, ít nhất {lo} ảnh (gấp {hi / lo:.1f} lần). "
            "Cân nhắc đặt class_weighting: true trong config.yaml hoặc bổ sung ảnh."
        )
    summary = {
        "seed": seed,
        "ratios": list(ratios),
        "size": size,
        "num_classes": len(stats),
        "totals": {s: sum(v[s] for v in stats.values()) for s in SPLITS},
        "bad_or_duplicate": len(bad),
        "classes": stats,
        "warnings": warnings,
    }
    write_json(out / "stats.json", summary)
    return summary


def print_summary(s: dict):
    print(f"\n{'Lớp':<22}{'tổng':>6}{'hỏng':>6}{'trùng':>6}{'train':>7}{'val':>6}{'test':>6}")
    for lbl, v in s["classes"].items():
        print(f"{lbl:<22}{v['total']:>6}{v['bad']:>6}{v['duplicate']:>6}{v['train']:>7}{v['val']:>6}{v['test']:>6}")
    t = s["totals"]
    print(f"{'TỔNG':<40}{t['train']:>7}{t['val']:>6}{t['test']:>6}")
    print(f"{s['num_classes']} lớp, {s['bad_or_duplicate']} ảnh bị loại (xem bad_images.txt)")
    for w in s["warnings"]:
        print(f"CẢNH BÁO: {w}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    p.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    p.add_argument("--nutrition", type=Path, default=ROOT / "data" / "nutrition.csv")
    p.add_argument("--size", type=int, default=256, help="Cạnh ngắn sau khi resize")
    p.add_argument("--ratios", type=float, nargs=3, default=(0.7, 0.15, 0.15), metavar=("TRAIN", "VAL", "TEST"))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-size", type=int, default=64, help="Loại ảnh có cạnh ngắn nhỏ hơn")
    p.add_argument("--min-images", type=int, default=50, help="Cảnh báo lớp có ít ảnh hơn")
    p.add_argument("--max-per-class", type=int, help="Chỉ lấy tối đa N ảnh/lớp (chạy thử nhanh)")
    p.add_argument("--classes", help="Chỉ lấy các lớp này, phân cách bằng dấu phẩy")
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()

    summary = prepare(
        args.raw, args.out, args.nutrition, args.size, tuple(args.ratios), args.seed, args.min_size,
        args.min_images, args.max_per_class, args.classes.split(",") if args.classes else None, args.workers,
    )
    print_summary(summary)
    print(f"\nĐã ghi vào {args.out}")


if __name__ == "__main__":
    sys.exit(main())
