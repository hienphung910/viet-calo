"""Đọc và kiểm tra file data/nutrition.csv (tách riêng khỏi lệnh seed để dễ test)."""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = [
    "class_label", "name", "name_vi", "kcal_per_100g", "protein", "carb", "fat", "default_portion_g",
]
NUMERIC_COLUMNS = ["kcal_per_100g", "protein", "carb", "fat", "default_portion_g"]
LABEL_RE = re.compile(r"^[a-z0-9_]+$")  # class_label = tên thư mục ảnh, chỉ ASCII thường


class NutritionCSVError(ValueError):
    pass


@dataclass
class FoodRow:
    class_label: str
    name: str
    name_vi: str
    kcal_per_100g: float
    protein: float
    carb: float
    fat: float
    default_portion_g: float

    def macro_kcal(self) -> float:
        """kcal tính lại từ macro theo hệ số Atwater: 4 kcal/g protein, 4 kcal/g carb, 9 kcal/g fat."""
        return 4 * self.protein + 4 * self.carb + 9 * self.fat


def load_nutrition_csv(path: Path) -> tuple[list[FoodRow], list[str]]:
    """
    Trả về (danh sách dòng hợp lệ, danh sách cảnh báo).
    Ném NutritionCSVError nếu có lỗi nghiêm trọng (thiếu cột, số âm, trùng nhãn...).
    """
    path = Path(path)
    if not path.exists():
        raise NutritionCSVError(f"Không tìm thấy file {path}")

    # utf-8-sig: chấp nhận cả file có BOM (Excel hay lưu kiểu này).
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise NutritionCSVError(f"Thiếu cột: {', '.join(missing)}")
        raw_rows = list(reader)

    rows, errors, warnings, seen = [], [], [], set()
    for line_no, raw in enumerate(raw_rows, start=2):  # dòng 1 là header
        label = (raw["class_label"] or "").strip()
        if not LABEL_RE.match(label):
            errors.append(f"Dòng {line_no}: class_label '{label}' chỉ được chứa a-z, 0-9, _")
            continue
        if label in seen:
            errors.append(f"Dòng {line_no}: class_label '{label}' bị trùng")
            continue
        seen.add(label)

        try:
            nums = {c: float(raw[c]) for c in NUMERIC_COLUMNS}
        except (TypeError, ValueError):
            errors.append(f"Dòng {line_no} ({label}): giá trị số không hợp lệ")
            continue
        if any(v < 0 for v in nums.values()) or nums["default_portion_g"] <= 0:
            errors.append(f"Dòng {line_no} ({label}): giá trị âm hoặc khẩu phần <= 0")
            continue

        row = FoodRow(class_label=label, name=raw["name"].strip(), name_vi=raw["name_vi"].strip(), **nums)
        # Cảnh báo (không chặn) nếu kcal lệch nhiều so với kcal tính từ macro -> có thể nhập sai.
        if row.kcal_per_100g > 0:
            diff = abs(row.macro_kcal() - row.kcal_per_100g) / row.kcal_per_100g
            if diff > 0.15:
                warnings.append(
                    f"{label}: kcal={row.kcal_per_100g:g} nhưng 4P+4C+9F={row.macro_kcal():.0f} (lệch {diff:.0%})"
                )
        rows.append(row)

    if errors:
        raise NutritionCSVError("\n".join(errors))
    return rows, warnings
