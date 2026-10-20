import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.foods.csv_loader import NutritionCSVError, load_nutrition_csv
from apps.foods.models import Food

HEADER = "class_label,name,name_vi,kcal_per_100g,protein,carb,fat,default_portion_g\n"


def write_csv(tmp_path, body):
    p = tmp_path / "n.csv"
    p.write_text(HEADER + body, encoding="utf-8")
    return p


def test_real_csv_is_valid_and_has_30_foods():
    rows, warnings = load_nutrition_csv(settings.NUTRITION_CSV)
    assert len(rows) == 30
    assert warnings == []


@pytest.mark.parametrize(
    "body, msg",
    [
        ("Pho Bo,Pho,Phở,90,6,12,2,600\n", "chỉ được chứa"),
        ("pho,Pho,Phở,90,6,12,2,600\npho,Pho,Phở,90,6,12,2,600\n", "bị trùng"),
        ("pho,Pho,Phở,-1,6,12,2,600\n", "giá trị âm"),
        ("pho,Pho,Phở,abc,6,12,2,600\n", "không hợp lệ"),
    ],
)
def test_invalid_rows_rejected(tmp_path, body, msg):
    with pytest.raises(NutritionCSVError, match=msg):
        load_nutrition_csv(write_csv(tmp_path, body))


def test_missing_column(tmp_path):
    p = tmp_path / "n.csv"
    p.write_text("class_label,name\npho,Pho\n", encoding="utf-8")
    with pytest.raises(NutritionCSVError, match="Thiếu cột"):
        load_nutrition_csv(p)


def test_macro_mismatch_is_warning_not_error(tmp_path):
    rows, warnings = load_nutrition_csv(write_csv(tmp_path, "pho,Pho,Phở,500,6,12,2,600\n"))
    assert len(rows) == 1 and "lệch" in warnings[0]


@pytest.mark.django_db
class TestSeedCommand:
    def test_seed_is_idempotent(self):
        call_command("seed_foods")
        call_command("seed_foods")
        assert Food.objects.count() == 30
        pho = Food.objects.get(class_label="pho")
        assert pho.name_vi == "Phở" and pho.default_portion_g == 600

    def test_seed_updates_existing(self, tmp_path, pho):
        call_command("seed_foods", csv=str(write_csv(tmp_path, "pho,Pho,Phở,100,6,12,2,500\n")))
        pho.refresh_from_db()
        assert pho.kcal_per_100g == 100 and pho.default_portion_g == 500

    def test_deactivate_missing(self, tmp_path, pho):
        call_command("seed_foods", csv=str(write_csv(tmp_path, "com_tam,Broken rice,Cơm tấm,190,9,25,6,450\n")),
                     deactivate_missing=True)
        pho.refresh_from_db()
        assert pho.is_active is False

    def test_invalid_csv_writes_nothing(self, tmp_path):
        bad = write_csv(tmp_path, "pho,Pho,Phở,90,6,12,2,600\nbad label,X,X,1,1,1,1,1\n")
        with pytest.raises(CommandError):
            call_command("seed_foods", csv=str(bad))
        assert Food.objects.count() == 0


def test_nutrition_for(db, pho):
    assert pho.nutrition_for(300) == {"kcal": 270.0, "protein_g": 18.0, "carb_g": 36.0, "fat_g": 6.0}
