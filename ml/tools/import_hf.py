"""
Chép ảnh từ bộ dữ liệu Hugging Face "jeandeanny/vn-food-combined-2026" (103 món Việt, định dạng parquet)
vào data/raw/<class_label>/. Chỉ lấy các món trong MAPPING bên dưới (món còn thiếu ảnh), KHÔNG lấy lại
30 món cũ: bộ này gộp cả 30VNFoods nên lấy lại sẽ sinh ảnh gần trùng giữa train và test.

Giấy phép: CC BY-NC-SA 4.0 (chỉ dùng phi thương mại, phải ghi nguồn). Xem README, mục "Nguồn dữ liệu".

Cách dùng:
    # 1. Tải bộ dữ liệu (~5,7 GB) về một thư mục bất kỳ
    python -c "from huggingface_hub import snapshot_download; snapshot_download('jeandeanny/vn-food-combined-2026', repo_type='dataset', local_dir=r'D:\\hf_vnfood103')"
    # 2. Chép các món cần vào data/raw (cần: pip install pyarrow)
    python -m ml.tools.import_hf --src D:\\hf_vnfood103
"""
import argparse
import io
from collections import Counter
from pathlib import Path

from PIL import Image

from ml.common import ROOT, read_nutrition_labels

# Nhãn trong bộ HF -> class_label trong data/nutrition.csv.
# Chỉ ghép khi hai bên là CÙNG một món nhìn giống nhau. Món khác hẳn (vd mì xào giòn vs mì xào mềm) thì
# tạo lớp riêng thay vì ghép bừa, nếu không model sẽ học lẫn.
MAPPING = {
    "banh-bao": "banh_bao",
    "banh-cong": "banh_cong",
    "banh-da-cua": "banh_da_cua",
    "banh-hoi": "banh_hoi",
    "banh-trung-thu": "banh_trung_thu",
    "bo-kho": "bo_kho",
    "bo-luc-lac": "bo_luc_lac",
    "bun-cha": "bun_cha",
    "ca-ri-ga": "ca_ri_ga",
    "canh-cua": "canh_cua",
    "cha-ca-la-vong": "cha_ca",
    "com-chien": "com_rang",
    "com-ga-xoi-mo": "com_ga",
    "nem-nuong-nha-trang": "nem_nuong",
    "rau-muong-xao": "rau_muong_xao_toi",
    "thit-kho-tau": "thit_kho_tau",
    "xoi-gac": "xoi_gac",
    # Lớp mới (đã thêm dòng vào nutrition.csv):
    "mi-xao-gion": "mi_xao_gion",
    "ga-chien-nuoc-mam": "ga_chien_nuoc_mam",
}


def label_names(pf) -> list[str]:
    """Đọc danh sách tên nhãn (ClassLabel) từ metadata 'huggingface' của file parquet."""
    import json

    meta = pf.schema_arrow.metadata or {}
    info = json.loads(meta[b"huggingface"])
    return info["info"]["features"]["label"]["names"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", required=True, type=Path, help="Thư mục đã tải bằng snapshot_download")
    p.add_argument("--dst", default=ROOT / "data" / "raw", type=Path)
    p.add_argument("--nutrition", default=ROOT / "data" / "nutrition.csv", type=Path)
    args = p.parse_args()

    import pyarrow.parquet as pq  # import muộn: chỉ script này cần pyarrow

    known = read_nutrition_labels(args.nutrition)
    missing = sorted(set(MAPPING.values()) - known)
    if missing:
        raise SystemExit("Các lớp sau chưa có dòng trong nutrition.csv: " + ", ".join(missing))

    files = sorted(args.src.rglob("*.parquet"))
    if not files:
        raise SystemExit(f"Không thấy file .parquet nào trong {args.src}")

    counts, skipped = Counter(), Counter()
    for f in files:
        split = f.name.split("-")[0]  # train / validation / test: gộp hết, prepare_data tự chia lại
        pf = pq.ParquetFile(f)
        names = label_names(pf)
        row = 0
        # Đọc từng lô nhỏ để không phải nạp cả file 600 MB vào RAM.
        for batch in pf.iter_batches(batch_size=256, columns=["image", "label"]):
            images, labels = batch.column("image").to_pylist(), batch.column("label").to_pylist()
            for img, lbl in zip(images, labels):
                row += 1
                hf_name = names[lbl]
                label = MAPPING.get(hf_name)
                if label is None:
                    skipped[hf_name] += 1
                    continue
                data = img["bytes"]
                with Image.open(io.BytesIO(data)) as im:  # lấy đúng đuôi theo định dạng thật của ảnh
                    ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp"}.get(im.format, ".jpg")
                dest = args.dst / label / f"hf_{f.stem}_{row:05d}{ext}"
                if dest.exists():
                    continue  # chạy lại nhiều lần không bị nhân bản
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                counts[label] += 1
        print(f"Xong {f.name} ({split})")

    print(f"\n{'class_label':<22}{'số ảnh mới':>10}")
    for label in sorted(counts):
        print(f"{label:<22}{counts[label]:>10}")
    print(f"Tổng: {sum(counts.values())} ảnh, {len(counts)} lớp -> {args.dst}")
    print(f"Bỏ qua {sum(skipped.values())} ảnh thuộc {len(skipped)} món không có trong MAPPING")


if __name__ == "__main__":
    main()
