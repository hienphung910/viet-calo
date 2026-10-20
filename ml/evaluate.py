"""
Đánh giá một model đã train trên tập test (hoặc val).

    python -m ml.evaluate --model-dir models/20261019-1530-efficientnet_b0
    python -m ml.evaluate --model-dir models/... --split val

Kết quả trong <model-dir>/eval_<split>/:
  metrics.json          accuracy, top-3 accuracy, macro precision/recall/F1
  per_class.csv         precision / recall / F1 / số ảnh theo từng lớp
  confusion_matrix.png  ma trận nhầm lẫn (chuẩn hóa theo hàng = tỷ lệ của lớp thật)
  misclassified.csv     danh sách ảnh đoán sai, sắp theo độ tin cậy giảm dần (sai mà "tự tin" nhất lên đầu)
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder
from tqdm import tqdm

from ml.common import ROOT, build_transforms, get_device, load_checkpoint, predict_topk, write_json


def plot_confusion(cm: np.ndarray, labels: list[str], path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(labels)
    norm = cm / cm.sum(axis=1, keepdims=True).clip(min=1)
    size = max(6, n * 0.45)
    fig, ax = plt.subplots(figsize=(size + 1.5, size))
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(n), labels, rotation=90, fontsize=8)
    ax.set_yticks(range(n), labels, fontsize=8)
    ax.set_xlabel("Dự đoán")
    ax.set_ylabel("Thực tế")
    ax.set_title("Confusion matrix (tỷ lệ theo hàng)")
    if n <= 15:  # ít lớp thì ghi số lên từng ô
        for i in range(n):
            for j in range(n):
                if cm[i, j]:
                    ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=7,
                            color="white" if norm[i, j] > 0.5 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


@torch.no_grad()
def evaluate(model_dir, data_dir, split="test", batch_size=64, num_workers=0, device=None, quiet=False) -> dict:
    log = (lambda *a, **k: None) if quiet else print
    model_dir, data_dir = Path(model_dir), Path(data_dir)
    device = device or get_device()
    model, meta = load_checkpoint(model_dir / "model.pt", device)
    class_list = meta["class_list"]

    ds = ImageFolder(data_dir / split, build_transforms(meta["img_size"], train=False))
    # Thứ tự lớp của tập dữ liệu có thể khác của model -> ánh xạ qua tên lớp.
    unknown = [c for c in ds.classes if c not in class_list]
    if unknown:
        raise SystemExit(f"Tập {split} có lớp model chưa từng học: {unknown}")
    to_model_idx = [class_list.index(c) for c in ds.classes]
    loader = DataLoader(ds, batch_size=batch_size, num_workers=num_workers, pin_memory=device.type == "cuda")

    y_true, y_pred, confs, top3s = [], [], [], []
    for x, y in tqdm(loader, desc=f"evaluate {split}", leave=False, ncols=90):
        probs, idx = predict_topk(model, x.to(device), k=3)
        y_true += [to_model_idx[t] for t in y.tolist()]
        y_pred += idx[:, 0].tolist()
        confs += probs[:, 0].tolist()
        top3s += [list(zip(i, p)) for i, p in zip(idx.tolist(), probs.tolist())]

    y_true_a, y_pred_a = np.array(y_true), np.array(y_pred)
    acc = float((y_true_a == y_pred_a).mean())
    top3 = float(np.mean([t in [i for i, _ in tp] for t, tp in zip(y_true, top3s)]))
    present = sorted(set(y_true))  # chỉ báo cáo các lớp có trong tập này
    names = [class_list[i] for i in present]
    report = classification_report(y_true, y_pred, labels=present, target_names=names,
                                   output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=present)

    out = model_dir / f"eval_{split}"
    out.mkdir(exist_ok=True)
    plot_confusion(cm, names, out / "confusion_matrix.png")

    with open(out / "per_class.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "precision", "recall", "f1", "support"])
        for n in names:
            r = report[n]
            w.writerow([n, f"{r['precision']:.4f}", f"{r['recall']:.4f}", f"{r['f1-score']:.4f}", r["support"]])

    wrong = [i for i in range(len(y_true)) if y_true[i] != y_pred[i]]
    wrong.sort(key=lambda i: -confs[i])
    with open(out / "misclassified.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["image", "true", "predicted", "confidence", "top3"])
        for i in wrong:
            path = Path(ds.samples[i][0]).relative_to(data_dir).as_posix()
            t3 = "; ".join(f"{class_list[c]} {p:.2f}" for c, p in top3s[i])
            w.writerow([path, class_list[y_true[i]], class_list[y_pred[i]], f"{confs[i]:.4f}", t3])

    confusions = Counter((class_list[y_true[i]], class_list[y_pred[i]]) for i in wrong).most_common(10)
    result = {
        "split": split,
        "num_images": len(y_true),
        "accuracy": round(acc, 4),
        "top3_accuracy": round(top3, 4),
        "macro_precision": round(report["macro avg"]["precision"], 4),
        "macro_recall": round(report["macro avg"]["recall"], 4),
        "macro_f1": round(report["macro avg"]["f1-score"], 4),
        "num_misclassified": len(wrong),
        "top_confusions": [{"true": t, "predicted": p, "count": c} for (t, p), c in confusions],
    }
    write_json(out / "metrics.json", result)

    log(f"\n[{split}] {len(y_true)} ảnh | accuracy {acc:.4f} | top-3 {top3:.4f} | macro F1 {result['macro_f1']:.4f}")
    worst = sorted(names, key=lambda n: report[n]["f1-score"])[:5]
    log("Lớp yếu nhất (F1): " + ", ".join(f"{n} {report[n]['f1-score']:.2f}" for n in worst))
    if confusions:
        log("Hay nhầm nhất: " + ", ".join(f"{t}->{p} ({c})" for (t, p), c in confusions[:5]))
    log(f"Chi tiết: {out}")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--data", type=Path, default=ROOT / "data" / "processed")
    p.add_argument("--split", default="test", choices=["train", "val", "test"])
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--num-workers", type=int, default=0)
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args()
    evaluate(args.model_dir, args.data, args.split, args.batch_size, args.num_workers,
             torch.device("cpu") if args.cpu else None)


if __name__ == "__main__":
    main()
