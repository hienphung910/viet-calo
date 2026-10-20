"""
Test pipeline ML trên bộ ảnh tổng hợp nhỏ, chạy CPU, model rất nhỏ, không tải trọng số pretrained.
Mục tiêu là kiểm tra code chạy đúng từ đầu đến cuối, không đo độ chính xác thật.
"""
import csv
import json

import pytest
from django.conf import settings
from django.core.management import call_command

torch = pytest.importorskip("torch")
pytest.importorskip("timm")

from ml.common import load_checkpoint  # noqa: E402
from ml.prepare_data import prepare, split_counts  # noqa: E402
from ml.tools.import_kaggle import slugify  # noqa: E402
from ml.tools.make_toy_dataset import make_toy_dataset  # noqa: E402

CLASSES = ["pho", "banh_mi", "com_tam"]


@pytest.fixture(scope="module")
def toy_raw(tmp_path_factory):
    return make_toy_dataset(tmp_path_factory.mktemp("raw"), CLASSES, per_class=20, seed=1)


def test_slugify():
    assert slugify("Bún bò Huế") == "bun_bo_hue"
    assert slugify("Bánh mì") == "banh_mi"
    assert slugify("Đậu hũ  chiên") == "dau_hu_chien"


def test_load_image_applies_exif_rotation(tmp_path):
    from PIL import Image

    from ml.common import load_image

    # Ảnh lưu nằm ngang 40x20 + EXIF Orientation=6 (điện thoại chụp dọc) -> sau khi load phải là 20x40.
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (40, 20)).save(tmp_path / "a.jpg", exif=exif)
    assert load_image(tmp_path / "a.jpg").size == (20, 40)


@pytest.mark.parametrize("n, expected", [(100, (70, 15, 15)), (20, (14, 3, 3)), (3, (1, 1, 1))])
def test_split_counts(n, expected):
    assert split_counts(n, (0.7, 0.15, 0.15)) == expected


def test_prepare_detects_bad_and_duplicate_and_is_deterministic(toy_raw, tmp_path):
    s1 = prepare(toy_raw, tmp_path / "p1", settings.NUTRITION_CSV, min_images=5, workers=2)
    s2 = prepare(toy_raw, tmp_path / "p2", settings.NUTRITION_CSV, min_images=5, workers=2)
    assert s1["classes"]["pho"]["bad"] == 1           # broken.jpg
    assert s1["classes"]["pho"]["duplicate"] == 1     # duplicate.jpg
    assert s1["totals"] == {"train": 42, "val": 9, "test": 9}
    read = lambda p: list(csv.reader(open(p / "split.csv", encoding="utf-8")))  # noqa: E731
    assert read(tmp_path / "p1") == read(tmp_path / "p2")  # cùng seed -> cùng cách chia


def test_prepare_rejects_class_without_nutrition(toy_raw, tmp_path):
    (toy_raw / "mon_la").mkdir(exist_ok=True)
    try:
        with pytest.raises(SystemExit, match="mon_la"):
            prepare(toy_raw, tmp_path / "p", settings.NUTRITION_CSV)
    finally:
        (toy_raw / "mon_la").rmdir()


@pytest.mark.django_db
def test_train_evaluate_register_end_to_end(toy_raw, tmp_path):
    from ml.train import train

    data = tmp_path / "processed"
    prepare(toy_raw, data, settings.NUTRITION_CSV, size=96, min_images=5, workers=2)
    cfg = {
        "seed": 0,
        "data_dir": str(data),
        "output_dir": str(tmp_path / "models"),
        "model": {"backbone": "mobilenetv3_small_050", "pretrained": False, "drop_rate": 0.0},
        "image": {"size": 64},
        "augmentation": {"crop_scale": [0.8, 1.0], "hflip": True},
        "train": {
            "epochs": 2, "batch_size": 16, "lr": 0.001, "freeze_backbone": True, "freeze_epochs": 1,
            "early_stopping_patience": 5, "amp": False, "num_workers": 0, "class_weighting": True,
        },
    }
    out = train(cfg, version="vtest", device=torch.device("cpu"), quiet=True)

    for f in ["model.pt", "class_list.json", "metrics.json", "history.csv", "training_curves.png",
              "eval_test/confusion_matrix.png", "eval_test/per_class.csv", "eval_test/misclassified.csv"]:
        assert (out / f).exists(), f
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["num_classes"] == 3 and 0 <= metrics["test_accuracy"] <= 1

    model, meta = load_checkpoint(out / "model.pt", torch.device("cpu"))
    assert meta["class_list"] == sorted(CLASSES)
    assert model(torch.zeros(1, 3, 64, 64)).shape == (1, 3)

    # Đăng ký vào CSDL: model đầu tiên được tự kích hoạt.
    from apps.recognition.models import ModelVersion

    call_command("seed_foods")
    call_command("register_model", str(out))
    mv = ModelVersion.objects.get(version="vtest")
    assert mv.is_active and mv.class_list == sorted(CLASSES) and mv.test_accuracy == metrics["test_accuracy"]
