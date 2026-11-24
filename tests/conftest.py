import pytest
from django.utils import timezone

from app.models import User
from app.models import Food
from app.models import ModelVersion

PASSWORD = "MatKhauTest#2026"


@pytest.fixture(autouse=True)
def clear_cache():
    # bộ đếm đăng nhập sai nằm trong cache, phải xoá để test này không ảnh hưởng test khác
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="an@example.com", password=PASSWORD)


@pytest.fixture
def pho(db):
    return Food.objects.create(
        name="Pho", name_vi="Phở", class_label="pho",
        kcal_per_100g=90, protein=6, carb=12, fat=2, default_portion_g=600,
    )


@pytest.fixture
def make_model_version(db):
    def _make(version, is_active=False, **kw):
        return ModelVersion.objects.create(
            version=version, file_path=f"models/{version}/model.pt", class_list=["pho"],
            trained_at=timezone.now(), is_active=is_active, **kw,
        )
    return _make
