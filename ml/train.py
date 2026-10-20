"""
Train model nhận diện món ăn bằng transfer learning (timm, pretrained ImageNet).

    python -m ml.train                                  # dùng ml/config.yaml
    python -m ml.train --epochs 30 --backbone mobilenetv3_large_100
    python -m ml.train --register --activate            # train xong ghi vào bảng model_versions và dùng luôn

Chiến lược 2 pha:
  - Pha 1 (freeze_epochs epoch đầu): đóng băng backbone, chỉ train lớp phân loại mới (head).
    Head mới khởi tạo ngẫu nhiên; nếu mở backbone ngay, gradient lớn từ head sẽ phá trọng số pretrained.
  - Pha 2: mở toàn bộ, backbone học với lr nhỏ hơn (backbone_lr_mult) để tinh chỉnh nhẹ.

Kết quả: models/<version>/ gồm model.pt (checkpoint tốt nhất theo val accuracy), class_list.json,
config.yaml, history.csv, training_curves.png, metrics.json, và eval_test/ (nếu có tập test).
"""
import argparse
import copy
import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import torch
import yaml
from torch import nn
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder
from tqdm import tqdm

from ml.common import (
    ROOT, build_model, build_transforms, get_device, load_config, save_checkpoint, set_seed, write_json,
)


def set_backbone_trainable(model: nn.Module, trainable: bool):
    head_ids = {id(p) for p in model.get_classifier().parameters()}
    for p in model.parameters():
        if id(p) not in head_ids:
            p.requires_grad = trainable


def freeze_batchnorm_stats(model: nn.Module):
    """Khi backbone đóng băng, giữ nguyên thống kê BatchNorm đã học trên ImageNet."""
    for m in model.modules():
        if isinstance(m, nn.modules.batchnorm._BatchNorm):
            m.eval()


def run_epoch(model, loader, criterion, device, optimizer=None, scaler=None, use_amp=False, desc=""):
    """Một vòng qua loader. optimizer=None nghĩa là chế độ đánh giá. Trả về (loss, acc, top3)."""
    training = optimizer is not None
    total = correct = correct3 = 0
    loss_sum = 0.0
    with torch.set_grad_enabled(training):
        for x, y in tqdm(loader, desc=desc, leave=False, ncols=90):
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                logits = model(x)
                loss = criterion(logits, y)
            if training:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            n = y.size(0)
            total += n
            loss_sum += loss.item() * n
            top3 = logits.topk(min(3, logits.size(1)), dim=1).indices
            correct += (top3[:, 0] == y).sum().item()
            correct3 += (top3 == y[:, None]).any(dim=1).sum().item()
    return loss_sum / total, correct / total, correct3 / total


def plot_history(history: list[dict], path: Path):
    import matplotlib

    matplotlib.use("Agg")  # vẽ ra file, không cần cửa sổ
    import matplotlib.pyplot as plt

    ep = [h["epoch"] for h in history]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    a1.plot(ep, [h["train_loss"] for h in history], label="train")
    a1.plot(ep, [h["val_loss"] for h in history], label="val")
    a1.set_title("Loss"), a1.set_xlabel("epoch"), a1.legend()
    a2.plot(ep, [h["train_acc"] for h in history], label="train acc")
    a2.plot(ep, [h["val_acc"] for h in history], label="val acc")
    a2.plot(ep, [h["val_top3"] for h in history], label="val top-3", linestyle="--")
    a2.set_title("Accuracy"), a2.set_xlabel("epoch"), a2.set_ylim(0, 1.02), a2.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def make_loader(ds, batch_size, shuffle, num_workers, device):
    return DataLoader(
        ds, batch_size=batch_size, shuffle=shuffle, num_workers=num_workers,
        pin_memory=device.type == "cuda", persistent_workers=num_workers > 0,
        # Train: bỏ batch cuối bị lẻ. Batch quá nhỏ làm BatchNorm không ổn định, và kích thước lạ
        # khiến cuDNN phải chọn lại kernel (đo được ~12 giây mỗi lần trên RTX 3060).
        drop_last=shuffle and len(ds) > batch_size,
    )


def train(cfg: dict, version: str | None = None, device: torch.device | None = None,
          evaluate_test: bool = True, quiet: bool = False) -> Path:
    log = (lambda *a, **k: None) if quiet else print
    set_seed(cfg["seed"])
    device = device or get_device()
    mcfg, tcfg, img_size = cfg["model"], cfg["train"], cfg["image"]["size"]
    data_dir = Path(cfg["data_dir"])

    train_ds = ImageFolder(data_dir / "train", build_transforms(img_size, True, cfg.get("augmentation")))
    val_ds = ImageFolder(data_dir / "val", build_transforms(img_size, False))
    if train_ds.classes != val_ds.classes:
        raise SystemExit("Tập train và val có danh sách lớp khác nhau. Chạy lại prepare_data.py.")
    class_list = train_ds.classes  # ImageFolder sắp xếp theo tên -> thứ tự cố định = chỉ số output
    log(f"Thiết bị: {device}{' (' + torch.cuda.get_device_name(0) + ')' if device.type == 'cuda' else ''}")
    log(f"{len(class_list)} lớp | train {len(train_ds)} ảnh | val {len(val_ds)} ảnh")

    nw = tcfg.get("num_workers", 0)
    train_loader = make_loader(train_ds, tcfg["batch_size"], True, nw, device)
    val_loader = make_loader(val_ds, tcfg["batch_size"] * 2, False, nw, device)

    model = build_model(mcfg["backbone"], len(class_list), mcfg.get("pretrained", True), mcfg.get("drop_rate", 0))
    model.to(device)

    # Trọng số lớp (tùy chọn): lớp ít ảnh được tính loss nặng hơn.
    weight = None
    if tcfg.get("class_weighting"):
        counts = torch.bincount(torch.tensor(train_ds.targets), minlength=len(class_list)).float()
        weight = (counts.sum() / (len(class_list) * counts.clamp(min=1))).to(device)
    criterion = nn.CrossEntropyLoss(weight=weight, label_smoothing=tcfg.get("label_smoothing", 0))

    head_params = list(model.get_classifier().parameters())
    head_ids = {id(p) for p in head_params}
    backbone_params = [p for p in model.parameters() if id(p) not in head_ids]
    optimizer = torch.optim.AdamW(
        [
            {"params": backbone_params, "lr": tcfg["lr"] * tcfg.get("backbone_lr_mult", 0.1)},
            {"params": head_params, "lr": tcfg["lr"]},
        ],
        weight_decay=tcfg.get("weight_decay", 1e-4),
    )
    epochs = tcfg["epochs"]
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    use_amp = bool(tcfg.get("amp", True)) and device.type == "cuda"
    scaler = torch.amp.GradScaler(device.type, enabled=use_amp)
    freeze_until = tcfg.get("freeze_epochs", 0) if tcfg.get("freeze_backbone", False) else 0

    version = version or f"{datetime.now():%Y%m%d-%H%M}-{mcfg['backbone']}"
    out = Path(cfg["output_dir"]) / version
    if out.exists():
        raise SystemExit(f"{out} đã tồn tại, đặt --version khác.")
    out.mkdir(parents=True)

    history, best_acc, best_loss, best_epoch, bad_epochs = [], -1.0, float("inf"), 0, 0
    patience = tcfg.get("early_stopping_patience", 0)
    t0 = time.time()
    for epoch in range(1, epochs + 1):
        frozen = epoch <= freeze_until
        set_backbone_trainable(model, not frozen)
        model.train()
        if frozen:
            freeze_batchnorm_stats(model)
        tr_loss, tr_acc, _ = run_epoch(model, train_loader, criterion, device, optimizer, scaler, use_amp,
                                       desc=f"epoch {epoch}/{epochs} train")
        model.eval()
        va_loss, va_acc, va_top3 = run_epoch(model, val_loader, criterion, device, use_amp=use_amp,
                                             desc=f"epoch {epoch}/{epochs} val")
        lr_head = optimizer.param_groups[1]["lr"]
        scheduler.step()

        history.append({
            "epoch": epoch, "frozen": frozen, "lr": lr_head, "train_loss": round(tr_loss, 4),
            "train_acc": round(tr_acc, 4), "val_loss": round(va_loss, 4), "val_acc": round(va_acc, 4),
            "val_top3": round(va_top3, 4),
        })
        # Tốt hơn = val accuracy cao hơn; bằng nhau thì chọn val loss thấp hơn.
        # Chỉ xét accuracy thì checkpoint đầu tiên đạt mức đó được giữ mãi, dù các epoch sau
        # tự tin hơn (loss thấp hơn). Mà web dùng ngưỡng độ tin cậy, nên điều này quan trọng.
        improved = va_acc > best_acc or (va_acc == best_acc and va_loss < best_loss)
        log(f"epoch {epoch:>3}/{epochs} {'[freeze]' if frozen else '        '} "
            f"train loss {tr_loss:.3f} acc {tr_acc:.3f} | val loss {va_loss:.3f} acc {va_acc:.3f} "
            f"top3 {va_top3:.3f}{'  *best' if improved else ''}")

        if improved:
            # Chỉ giữ checkpoint tốt nhất theo val accuracy.
            best_acc, best_loss, best_top3, best_epoch, bad_epochs = va_acc, va_loss, va_top3, epoch, 0
            save_checkpoint(out / "model.pt", model, backbone=mcfg["backbone"], class_list=class_list,
                            img_size=img_size, extra={"epoch": epoch, "val_accuracy": va_acc})
        elif not frozen:
            # Không tính patience trong pha đóng băng: model còn đang "khởi động".
            bad_epochs += 1
            if patience and bad_epochs >= patience:
                log(f"Early stopping: val accuracy không tăng sau {patience} epoch.")
                break

    train_secs = time.time() - t0
    with open(out / "history.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0]))
        w.writeheader()
        w.writerows(history)
    plot_history(history, out / "training_curves.png")
    write_json(out / "class_list.json", class_list)
    resolved = copy.deepcopy(cfg)
    (out / "config.yaml").write_text(yaml.safe_dump(resolved, allow_unicode=True, sort_keys=False), encoding="utf-8")

    metrics = {
        "version": version,
        "backbone": mcfg["backbone"],
        "num_classes": len(class_list),
        "img_size": img_size,
        "best_epoch": best_epoch,
        "epochs_ran": len(history),
        "val_accuracy": round(best_acc, 4),
        "top3_accuracy": round(best_top3, 4),
        "train_images": len(train_ds),
        "val_images": len(val_ds),
        "train_time_sec": round(train_secs, 1),
        "device": str(device),
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    log(f"\nTốt nhất: epoch {best_epoch}, val acc {best_acc:.4f}, val top-3 {best_top3:.4f} "
        f"({train_secs / 60:.1f} phút)")

    if evaluate_test and (data_dir / "test").exists():
        from ml.evaluate import evaluate

        res = evaluate(out, data_dir, "test", batch_size=tcfg["batch_size"] * 2, num_workers=nw,
                       device=device, quiet=quiet)
        metrics["test_accuracy"] = res["accuracy"]
        metrics["test_top3_accuracy"] = res["top3_accuracy"]

    write_json(out / "metrics.json", metrics)
    log(f"Đã lưu vào {out}")
    return out


def register(model_dir: Path, activate: bool):
    """Gọi lệnh Django để ghi vào bảng model_versions (script ML không phụ thuộc trực tiếp vào Django)."""
    cmd = [sys.executable, str(ROOT / "manage.py"), "register_model", str(model_dir)]
    if activate:
        cmd.append("--activate")
    subprocess.run(cmd, check=True, cwd=ROOT)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=ROOT / "ml" / "config.yaml")
    p.add_argument("--data", help="Ghi đè data_dir")
    p.add_argument("--version", help="Tên phiên bản (mặc định: <ngày-giờ>-<backbone>)")
    p.add_argument("--backbone")
    p.add_argument("--epochs", type=int)
    p.add_argument("--batch-size", type=int)
    p.add_argument("--lr", type=float)
    p.add_argument("--img-size", type=int)
    p.add_argument("--num-workers", type=int)
    p.add_argument("--no-pretrained", action="store_true", help="Không dùng trọng số ImageNet")
    p.add_argument("--cpu", action="store_true", help="Bắt buộc chạy CPU")
    p.add_argument("--no-test", action="store_true", help="Không đánh giá trên tập test sau khi train")
    p.add_argument("--register", action="store_true", help="Ghi kết quả vào bảng model_versions")
    p.add_argument("--activate", action="store_true", help="(cùng --register) đặt làm model đang dùng")
    args = p.parse_args()

    cfg = load_config(args.config)
    overrides = {
        ("data_dir",): args.data, ("model", "backbone"): args.backbone, ("train", "epochs"): args.epochs,
        ("train", "batch_size"): args.batch_size, ("train", "lr"): args.lr, ("image", "size"): args.img_size,
        ("train", "num_workers"): args.num_workers,
    }
    for keys, val in overrides.items():
        if val is not None:
            node = cfg
            for k in keys[:-1]:
                node = node[k]
            node[keys[-1]] = val
    if args.no_pretrained:
        cfg["model"]["pretrained"] = False
    # Đường dẫn tương đối trong config tính từ thư mục gốc dự án.
    for key in ("data_dir", "output_dir"):
        if not Path(cfg[key]).is_absolute():
            cfg[key] = str(ROOT / cfg[key])

    out = train(cfg, args.version, torch.device("cpu") if args.cpu else None, evaluate_test=not args.no_test)
    if args.register:
        register(out, args.activate)


if __name__ == "__main__":  # bắt buộc trên Windows khi DataLoader dùng num_workers > 0
    main()
