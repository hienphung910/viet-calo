import json
import shutil
import urllib.error
import zipfile

import pytest
from django.core.management import call_command

from app.management.commands.prepare_deploy import Command
from app.models import Food, ModelVersion, User


def make_model_dir(parent, version, test_accuracy=0.9):
    d = parent / version
    d.mkdir(parents=True)
    (d / "model.pt").write_bytes(b"fake")
    (d / "class_list.json").write_text(json.dumps(["pho"]), encoding="utf-8")
    (d / "metrics.json").write_text(
        json.dumps({"version": version, "backbone": "efficientnet_b0", "test_accuracy": test_accuracy}),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def models_dir(settings, tmp_path):
    settings.MODELS_DIR = tmp_path / "models"
    settings.MODEL_URL = ""
    return settings.MODELS_DIR


@pytest.mark.django_db
def test_seeds_foods_only_when_table_is_empty(models_dir):
    call_command("prepare_deploy")
    assert Food.objects.count() >= 30

    Food.objects.filter(class_label="pho").update(kcal_per_100g=999)
    call_command("prepare_deploy")
    assert Food.objects.get(class_label="pho").kcal_per_100g == 999  # không ghi đè số liệu admin đã sửa


@pytest.mark.django_db
def test_registers_models_and_activates_the_best_one(models_dir):
    make_model_dir(models_dir, "v-kem", test_accuracy=0.6)
    make_model_dir(models_dir, "v-tot", test_accuracy=0.9)
    call_command("prepare_deploy")
    assert ModelVersion.objects.count() == 2
    assert ModelVersion.objects.get(is_active=True).version == "v-tot"


@pytest.mark.django_db
def test_downloads_model_zip_when_file_is_missing(models_dir, settings, tmp_path, monkeypatch):
    src = make_model_dir(tmp_path / "src", "v-zip")
    zip_path = tmp_path / "model.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in src.iterdir():
            z.write(f, f"v-zip/{f.name}")
    monkeypatch.setattr("urllib.request.urlretrieve", lambda url, dest: shutil.copy(zip_path, dest))
    settings.MODEL_URL = "https://example.com/model.zip"

    call_command("prepare_deploy")
    assert (models_dir / "v-zip" / "model.pt").exists()
    assert ModelVersion.objects.get(is_active=True).version == "v-zip"

    # server deploy lại: file mất nhưng CSDL vẫn còn bản ghi -> tải lại, không tạo bản ghi mới
    shutil.rmtree(models_dir)
    call_command("prepare_deploy")
    assert (models_dir / "v-zip" / "model.pt").exists()
    assert ModelVersion.objects.count() == 1


@pytest.mark.django_db
def test_reads_zip_made_on_windows_with_backslash_paths(models_dir, settings, tmp_path, monkeypatch):
    # Compress-Archive (Windows PowerShell) ghi tên file dạng "thu-muc\model.pt"
    src = make_model_dir(tmp_path / "src", "v-win")
    zip_path = tmp_path / "model.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in src.iterdir():
            info = zipfile.ZipInfo("x")
            info.filename = f"v-win\\{f.name}"  # gán sau khi tạo để zipfile không tự đổi \ thành /
            z.writestr(info, f.read_bytes())
    monkeypatch.setattr("urllib.request.urlretrieve", lambda url, dest: shutil.copy(zip_path, dest))
    settings.MODEL_URL = "https://example.com/model.zip"

    call_command("prepare_deploy")
    assert (models_dir / "v-win" / "model.pt").read_bytes() == b"fake"
    assert ModelVersion.objects.get(is_active=True).version == "v-win"


def test_extract_skips_paths_outside_destination(tmp_path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for name in ("..\\..\\ra-ngoai.txt", "../ra-ngoai-2.txt", "trong\\ok.txt"):
            info = zipfile.ZipInfo("x")
            info.filename = name
            z.writestr(info, b"x")
    Command._extract(zip_path, tmp_path / "a" / "b" / "out")
    found = [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.txt")]
    assert found == ["a/b/out/trong/ok.txt"]


@pytest.mark.django_db
def test_broken_model_url_does_not_stop_startup(models_dir, settings, tmp_path, monkeypatch, capsys):
    def fail(url, dest):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr("urllib.request.urlretrieve", fail)
    settings.MODEL_URL = "https://example.com/khong-co.zip"
    call_command("prepare_deploy")  # không ném lỗi
    assert "Không tải được model" in capsys.readouterr().err
    assert not ModelVersion.objects.exists()

    # link trả về trang HTML thay vì file .zip
    monkeypatch.setattr("urllib.request.urlretrieve", lambda url, dest: open(dest, "w").write("<html>"))
    call_command("prepare_deploy")
    assert not ModelVersion.objects.exists()


@pytest.mark.django_db
def test_creates_admin_from_env_once(models_dir, monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "Admin@Example.com")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "MatKhauTest#2026")
    call_command("prepare_deploy")
    call_command("prepare_deploy")
    admin = User.objects.get(email="admin@example.com")
    assert admin.is_superuser and admin.check_password("MatKhauTest#2026")
    assert User.objects.count() == 1
