# VietCalo — Nhận diện món ăn Việt và ước tính calories

Web app viết hoàn toàn bằng Python (Django). Luồng chính: người dùng chụp hoặc tải ảnh món ăn → model PyTorch
nhận diện 30 món Việt → tính calories và macro (protein, carb, fat) theo khẩu phần → lưu vào nhật ký ăn uống.
Ảnh người dùng xác nhận được giữ lại để train phiên bản model sau.

- **Web:** Django 5.2 LTS. Giao diện render phía server bằng template; Tailwind và Chart.js tải qua CDN nên không
  cần Node.js. JavaScript thuần chỉ dùng để xem trước ảnh, tính thử kcal và vẽ biểu đồ.
- **CSDL:** MySQL 8 (chạy thử được bằng SQLite). ERD, ràng buộc và truy vấn thống kê: [docs/database.md](docs/database.md).
- **ML:** PyTorch + timm, transfer learning từ EfficientNet-B0 pretrained ImageNet. Train trên GPU, web dự đoán bằng CPU.

## Tiến độ

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| 1 | CSDL + đăng ký/đăng nhập + seed món ăn + admin cơ bản | ✅ SQLite · ⏳ chờ kiểm tra trên MySQL |
| 2 | Pipeline ML (prepare / train / evaluate / register) | ✅ (đã chạy thử với data tổng hợp; chờ data Kaggle) |
| 3 | Upload ảnh, dự đoán top-3, chọn/sửa món, khẩu phần, lưu bữa ăn, hot-reload model | ✅ |
| 4 | Trang nhật ký ngày/tuần, biểu đồ, sửa/xóa/thêm thủ công bữa ăn, so với mục tiêu | ✅ |
| 5 | Admin nâng cao, duyệt ảnh phản hồi, export_feedback, thống kê độ chính xác & so sánh model | ✅ |
| 6 | Script cài đặt, demo bằng waitress (DEBUG=False), bảo vệ ảnh, dọn ảnh, sao lưu mysqldump | ✅ · ⏳ phần MySQL (setup_mysql, mysqldump/restore) và `-Lan` chờ chạy thử |

## Cài đặt

Yêu cầu: Windows 10/11, Python ≥ 3.11 (đã thử với 3.12), MySQL Server 8.0 (≥ 8.0.13). GPU NVIDIA chỉ cần khi train.
**Không dùng MariaDB/XAMPP**: MariaDB không hỗ trợ functional index mà hệ thống dùng (xem docs/database.md).

### Cách nhanh (script)

```powershell
cd E:\Major\Project\AI\Calories
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

`setup.ps1` làm lần lượt các bước sau:
1. tạo `.venv`;
2. cài thư viện, gồm PyTorch bản CUDA nếu máy có GPU NVIDIA, không thì bản CPU;
3. tạo `.env` với `SECRET_KEY` và mật khẩu MySQL sinh ngẫu nhiên;
4. kiểm tra kết nối CSDL, chạy `migrate`, nạp bảng dinh dưỡng, `collectstatic`;
5. hỏi tạo tài khoản admin.

Chạy lại bao nhiêu lần cũng được.

Lần đầu, script sẽ báo **chưa kết nối được MySQL**. Khi đó mở PowerShell bằng **Run as Administrator** (cần quyền
này để bật service MySQL) và chạy:

```powershell
cd E:\Major\Project\AI\Calories
powershell -ExecutionPolicy Bypass -File scripts\setup_mysql.ps1
```

Script này bật service `MySQL80`, hỏi mật khẩu **root** của MySQL, rồi tạo database `calories` (utf8mb4) cùng tài
khoản `calories` theo thông tin trong `.env`. Nó cũng cấp quyền trên database `test_calories` để chạy test. Sau đó
chạy lại `scripts\setup.ps1`.

Muốn thử nhanh không cần MySQL: `scripts\setup.ps1 -Db sqlite`.

### Cách thủ công

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128   # hoặc .../whl/cpu
pip install -r requirements-ml.txt
Copy-Item .env.example .env      # rồi sửa SECRET_KEY, DATABASE_URL
```

Tạo database: đăng nhập `mysql -u root -p` và chạy:

```sql
CREATE DATABASE calories CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'calories'@'localhost' IDENTIFIED BY 'dat-mat-khau-o-day';
GRANT ALL PRIVILEGES ON calories.* TO 'calories'@'localhost';
GRANT ALL PRIVILEGES ON test_calories.* TO 'calories'@'localhost';  -- database tạm khi chạy test
FLUSH PRIVILEGES;
```

Trong `.env`: `DATABASE_URL=mysql://calories:dat-mat-khau-o-day@localhost:3306/calories`
(hoặc `DATABASE_URL=sqlite:///db.sqlite3`).

> Mật khẩu có ký tự `@ # / : %` thì phải mã hóa trong URL (`@` → `%40`, `#` → `%23`, `/` → `%2F`,
> `:` → `%3A`, `%` → `%25`), nếu không Django sẽ đọc sai địa chỉ CSDL.

```powershell
python manage.py migrate
python manage.py seed_foods
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### Chạy web

| Mục đích | Lệnh | Ghi chú |
|---|---|---|
| Phát triển | `.venv\Scripts\python.exe manage.py runserver` | `DEBUG=True`, tự reload khi sửa code |
| Demo / bảo vệ | `powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1` | waitress, `DEBUG=False`, http://127.0.0.1:8000 |
| Demo trên điện thoại | `...\run_demo.ps1 -Lan` | điện thoại cùng Wi-Fi mở địa chỉ IP mà script in ra |

Trang người dùng: http://127.0.0.1:8000. Quản trị: http://127.0.0.1:8000/admin.

Ở chế độ demo (`DEBUG=False`), lỗi không hiện chi tiết code; file tĩnh do whitenoise phục vụ; ảnh do view
kiểm tra quyền phục vụ (xem [Bảo mật và quyền riêng tư](#bảo-mật-và-quyền-riêng-tư)).

### Chạy test

```powershell
.venv\Scripts\python.exe -m pytest
```

Test chạy trên CSDL cấu hình trong `.env`: Django tự tạo rồi xóa database `test_calories`. Có 120+ test:
ràng buộc CSDL, auth, seed, pipeline ML (model nhỏ trên CPU), nhận diện (model giả), nhật ký, thống kê, admin,
quyền xem ảnh.

## Giao diện

Thiết kế nằm trong file Figma **VietCalo UI**: https://www.figma.com/design/r65rZ68yyEcfNxo1wgfdJe. File gồm:
- bộ màu, khoảng cách, bo góc (dạng variable), 11 kiểu chữ Be Vietnam Pro, đổ bóng;
- các component: Button, Chip, NavBar, StatCard, MealRow, PredictionRow, MacroBar, icon;
- 4 màn hình: Hôm nay, Quét món, Xác nhận món, Tuần.

Cách chuyển thiết kế vào code:
- **Token → Tailwind:** khối `@theme` trong [templates/base.html](templates/base.html) cho ra class `bg-brand-600`,
  `text-ink-900`, `bg-page`, `shadow-card`, `rounded-card`… Kiểu chữ là các utility `type-h1`, `type-body`,
  `type-num-xl`…; component là `card`, `btn btn-primary` / `btn-accent` / `btn-secondary` / `btn-ghost`, `field`.
  Đổi màu ở `@theme` là đổi cho toàn bộ web.
- **Icon:** [templates/icons/](templates/icons/), cùng nét vẽ với icon trong Figma, tô màu bằng `text-*`.
  Dùng: `{% include "icons/camera.svg" with cls="size-5" %}`.
- **Số kiểu Việt Nam:** `{% load vn %}{{ value|num }}` → `1.498` (locale `vi` của Django không tự nhóm hàng nghìn).

## Bảng dinh dưỡng và thêm món mới

Dữ liệu dinh dưỡng nằm ở `data/nutrition.csv` (giá trị **trên 100g**):

```
class_label,name,name_vi,kcal_per_100g,protein,carb,fat,default_portion_g,note
pho,Pho noodle soup,Phở,90,6,12,2,600,...
```

- `class_label`: chỉ gồm `a-z 0-9 _`, **trùng tên thư mục ảnh** trong `data/raw/<class_label>/`.
- Lệnh `seed_foods` chạy lại bao nhiêu lần cũng được: món đã có thì cập nhật, món mới thì thêm.
  Nếu kcal lệch > 15% so với `4×protein + 4×carb + 9×fat`, lệnh sẽ cảnh báo (có thể nhập sai số).
- **Số liệu hiện tại là ước tính ban đầu (cột `note`)**. Nên đối chiếu với *Bảng thành phần thực phẩm
  Việt Nam* (Viện Dinh dưỡng Quốc gia) và ghi nguồn trước khi bảo vệ.

Thêm món mới: thêm thư mục ảnh `data/raw/<class_label>/` + thêm một dòng CSV → `seed_foods` → chạy lại
`prepare_data` và `train` (xem phần dưới).

## Train model

### Cài thư viện ML

Cài PyTorch bản **có CUDA** trước (cài thẳng từ PyPI trên Windows sẽ ra bản chỉ chạy CPU). Lấy lệnh đúng cho
máy tại https://pytorch.org/get-started/locally/. Với RTX 3060:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements-ml.txt
python -c "import torch; print(torch.cuda.is_available())"   # phải in True
```

### 1. Lấy dữ liệu

Tải dataset 30 món Việt trên Kaggle (ví dụ *30VNFoods*), giải nén, rồi chép vào `data/raw/` với tên thư mục
đã chuẩn hóa (`Bún bò Huế` → `bun_bo_hue`; các thư mục Train/Validate/Test của Kaggle được gộp lại):

```powershell
python -m ml.tools.import_kaggle --src "D:\Downloads\30VNFoods"
```

Script in ra lớp nào chưa có trong `nutrition.csv`. Tên lệch thì sửa bằng `--rename "Ten goc=class_label"`.

Chưa có data thật mà muốn thử pipeline: `python -m ml.tools.make_toy_dataset` (tạo `data/raw_toy/`, 5 lớp ảnh hình học).

### 2. Chuẩn bị dữ liệu

```powershell
python -m ml.prepare_data
# chạy thử nhanh với 5 lớp, 50 ảnh/lớp:
python -m ml.prepare_data --classes pho,banh_mi,com_tam,bun_bo_hue,goi_cuon --max-per-class 50
```

Kiểm tra mỗi thư mục có dòng trong `nutrition.csv`, loại ảnh hỏng / quá nhỏ / trùng lặp, chia train/val/test
70/15/15 theo từng lớp với seed cố định, resize cạnh ngắn về 256px. Kết quả ở `data/processed/`, kèm
`stats.json`, `split.csv` (ảnh nào thuộc tập nào) và `bad_images.txt`.

### 3. Train

Tham số nằm trong [ml/config.yaml](ml/config.yaml) (backbone, epochs, batch size, learning rate, kích thước ảnh,
augmentation, đóng băng backbone...). Một số tham số ghi đè được bằng CLI.

```powershell
python -m ml.train                          # train theo config.yaml, tự đánh giá trên tập test
python -m ml.train --register --activate    # train xong ghi vào bảng model_versions và dùng luôn
python -m ml.train --epochs 30 --backbone mobilenetv3_large_100 --version v2-mobilenet
```

Kết quả ở `models/<version>/`: `model.pt` (checkpoint có val accuracy cao nhất), `class_list.json`,
`config.yaml`, `history.csv`, `training_curves.png`, `metrics.json`, `eval_test/`.

Gặp lỗi DataLoader trên Windows thì đặt `num_workers: 0` trong config. Thiếu VRAM thì giảm `batch_size`.

### 4. Đánh giá

`train` đã tự đánh giá trên tập test. Muốn chạy lại riêng:

```powershell
python -m ml.evaluate --model-dir models\<version>
```

Kết quả trong `eval_test/`: `metrics.json` (accuracy, top-3, macro P/R/F1), `per_class.csv`,
`confusion_matrix.png`, `misclassified.csv` (ảnh bị đoán sai, sai mà tự tin nhất xếp đầu).

### 5. Đăng ký model vào CSDL

Nếu lúc train chưa dùng `--register`:

```powershell
python manage.py register_model models\<version> --activate
```

Lệnh từ chối kích hoạt model có lớp chưa có trong bảng `foods` (web sẽ không tính được calo cho lớp đó).
Đổi model đang dùng: trang admin → *Phiên bản model* → chọn → action *Đặt làm model đang dùng*.

## Nhận diện trên web

1. Người dùng vào **📷 Chụp món** (`/scan/`) và lấy ảnh theo một trong hai cách:
   - **Camera** (webcam laptop hoặc camera điện thoại): bấm *Bật camera*, cho phép trình duyệt dùng camera.
     Nếu bật **Nhận diện trực tiếp**, khoảng mỗi giây trình duyệt gửi một khung hình nhỏ (384px) tới
     `/api/predict/?preview=1` và hiện tên món + độ tin cậy ngay trên khung hình (xanh: đủ tin cậy, vàng: chưa chắc).
     Chế độ này **không lưu ảnh** lên server. Bấm **Chụp** (hoặc phím Space) để chụp ảnh đầy đủ (≤ 1280px).
     Có thể đổi camera nếu máy có nhiều camera; rời trang thì camera tự tắt.
   - **Chọn ảnh có sẵn**: chọn file. Trên điện thoại, nút này cũng mở được camera của máy.

   Ảnh được xem trước ngay trên trình duyệt trước khi gửi.

   > Trình duyệt chỉ cho web dùng camera trên **https** hoặc **localhost / 127.0.0.1**. Mở bằng địa chỉ IP qua
   > mạng LAN (`run_demo.ps1 -Lan`, `http://192.168...`) thì tab Camera bị tắt; điện thoại dùng *Chọn ảnh có sẵn*
   > (vẫn mở được camera của máy).
2. Server xoay ảnh theo EXIF, thu nhỏ (cạnh dài ≤ 1280px), **xóa metadata** (kể cả GPS), lưu vào
   `media/uploads/YYYY/MM/<tên ngẫu nhiên>.jpg`, rồi chạy model.
3. Trang xác nhận hiện top-3 kèm độ tin cậy:
   - top-1 ≥ ngưỡng (`CONFIDENCE_THRESHOLD`, mặc định 0.6): chọn sẵn top-1, người dùng vẫn đổi được;
   - top-1 < ngưỡng: báo "Model chưa chắc chắn", người dùng phải tự chọn;
   - món không có trong top-3: chọn **Món khác** trong danh sách (sửa nhãn).
4. Chọn khẩu phần Nhỏ / Vừa / Lớn (0.7 / 1.0 / 1.3 × khẩu phần mặc định) hoặc nhập số gram. kcal được tính thử
   ngay trên trình duyệt; giá trị lưu thật do server tính lại.
5. Bấm lưu: ghi `meal_logs` (snapshot kcal/macro, top-3, `was_corrected`, phiên bản model). Nếu người dùng tick
   đồng ý: ghi thêm `feedback_images` với bản sao ảnh trong `media/feedback/` (dùng để train lại ở Giai đoạn 5).

Kết quả nhận diện được giữ tạm trong session cho tới khi người dùng bấm lưu, nên không có dòng rác trong CSDL.

**Model trên web**
- `PredictionService` ([apps/recognition/services.py](apps/recognition/services.py)) nạp model active **một lần**
  khi server khởi động (`config/wsgi.py`). Cứ `MODEL_CHECK_INTERVAL` giây (mặc định 10) service hỏi CSDL xem model
  active có đổi không, đổi thì tự nạp model mới. **Không cần restart server**.
- Reload ngay lập tức (chỉ admin): `POST /recognition/reload/`.
- Mặc định chạy CPU (`ML_DEVICE=cpu` trong `.env`) để web chạy được trên mọi máy.
- Tiền xử lý ảnh trên web dùng đúng các hàm của lúc train/evaluate (`ml/common.py`: `load_image`,
  `build_transforms`), để tránh sai khác giữa lúc train và lúc dùng thật.

**API JSON** (cần đăng nhập, gửi kèm CSRF token): `POST /api/predict/` (multipart, field `image`) trả về top-3.
Thêm `?preview=1` thì không lưu ảnh (dùng cho nhận diện trực tiếp bằng camera):

```json
{"model_version": "...", "is_confident": true, "threshold": 0.6,
 "predictions": [{"label": "pho", "confidence": 0.84, "name_vi": "Phở", "kcal_per_100g": 90, "default_portion_g": 600}, ...]}
```

## Nhật ký ăn uống

- **Hôm nay** (`/`, đổi ngày bằng mũi tên hoặc ô chọn ngày): tổng kcal so với mục tiêu (thanh màu xanh dương
  < 90%, xanh lá 90–110%, đỏ > 110%), gram và tỷ lệ năng lượng từ protein/carb/fat, các món theo bữa kèm ảnh.
  Bữa nào được AI nhận diện thì hiện độ tin cậy, và ghi "đã sửa nhãn" nếu người dùng đổi món.
- **Tuần** (`/week/`): biểu đồ cột kcal từng ngày với đường mục tiêu (Chart.js, bấm cột để xem ngày đó),
  biểu đồ tròn nguồn năng lượng, bảng chi tiết, món ăn nhiều nhất, kcal theo bữa. Trung bình/ngày chỉ tính
  những ngày có ghi nhật ký.
- **Sửa bữa ăn:** đổi món, khẩu phần, bữa, giờ ăn. kcal/macro được tính lại. Đổi món của bữa do AI nhận diện
  được ghi nhận là sửa nhãn (`was_corrected`), đồng thời sửa nhãn đúng của ảnh phản hồi (trừ ảnh đã dùng để train).
- **Xóa bữa ăn:** xóa luôn ảnh gốc. Bản sao ảnh phản hồi (nếu người dùng đã đồng ý) vẫn được giữ.
- **Thêm thủ công:** khi model không biết món, hoặc ghi bù ngày trước.

Truy vấn thống kê và SQL tương đương: [docs/database.md](docs/database.md#truy-vấn-thống-kê).

## Quản trị và vòng phản hồi dữ liệu

Tài khoản admin (`is_staff`) thấy thêm 2 mục trên menu:

- **Thống kê** (`/recognition/stats/`): độ chính xác **thực tế** của model, tức món người dùng xác nhận có trùng
  với model đoán không:
  - top-1, top-3, độ tin cậy trung bình, tỷ lệ phải hỏi người dùng (dưới ngưỡng);
  - **so sánh các phiên bản model**: val/test accuracy lúc train đặt cạnh độ chính xác thực tế (biểu đồ + bảng);
  - **độ chính xác theo nhóm độ tin cậy**: kiểm tra model "tự tin" có đáng tin không, dùng để chọn ngưỡng;
  - cặp món hay bị nhầm, món nhận diện kém nhất, số ảnh phản hồi, món phổ biến trên toàn hệ thống;
  - nút **Nạp lại model**.
- **Quản trị** (`/admin/`):
  - *Món ăn*: sửa dinh dưỡng ngay trong danh sách, số lần được ăn / số ảnh phản hồi của mỗi món, nút
    **Nạp lại từ nutrition.csv**.
  - *Ảnh phản hồi*: ảnh thu nhỏ, **sửa nhãn đúng ngay trong danh sách**, lọc ảnh model đoán sai. Action:
    xuất sang `data/raw`, loại ảnh xấu khỏi dữ liệu train, đánh dấu chưa dùng (để xuất lại).
  - *Phiên bản model*: val/test accuracy, số lượt dùng, độ chính xác thực tế. Action *Đặt làm model đang dùng*
    (nạp ngay), nút *Thống kê & so sánh*, *Nạp lại model*.
  - *Nhật ký ăn uống*: ảnh thu nhỏ, lọc theo model / sửa nhãn / ngày.

### Train lại bằng ảnh phản hồi

```powershell
python -m ml.export_feedback --dry-run          # xem sẽ xuất bao nhiêu ảnh, mỗi lớp mấy ảnh
python -m ml.export_feedback                    # chép sang data/raw/<class_label>/feedback_<id>.jpg
python -m ml.prepare_data                       # chia lại train/val/test (ảnh trùng tự bị loại)
python -m ml.train --register                   # train phiên bản mới, ghi vào model_versions
```

So sánh phiên bản mới với phiên bản cũ ở trang **Thống kê**, rồi kích hoạt bản mới trong admin.

- Chỉ xuất ảnh người dùng **đã đồng ý** và **chưa dùng để train**. Ràng buộc CSDL chặn việc đánh dấu
  "đã train" cho ảnh chưa được đồng ý.
- Nhãn là **món người dùng xác nhận**, không phải nhãn model đoán.
- `--only-corrected`: chỉ xuất ảnh model đoán sai (có giá trị nhất để model học lại).
- Chạy lại bao nhiêu lần cũng được: ảnh đã xuất không bị xuất lần hai.
- Nên duyệt ảnh trong admin trước khi xuất: người dùng có thể chọn nhầm món, và ảnh nhãn sai sẽ làm model tệ đi.
  Nếu ảnh **đã xuất** mà admin loại ra, sửa nhãn hoặc xóa, file trong `data/raw` cũng được gỡ theo. Riêng ảnh
  sửa nhãn sẽ được xuất lại vào đúng thư mục nhãn mới ở lần chạy sau.

## Vận hành

### Sao lưu và khôi phục

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1              # backups\calories_<ngày_giờ>.sql
powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1 -WithMedia   # kèm ảnh: backups\media_<ngày_giờ>.zip
powershell -ExecutionPolicy Bypass -File scripts\restore_db.ps1 backups\calories_20261019_2300.sql
```

- MySQL dùng `mysqldump --single-transaction`: InnoDB cho phép sao lưu nhất quán mà không khóa bảng, nên web
  vẫn chạy được trong lúc sao lưu.
- Mật khẩu CSDL được đưa cho `mysqldump` qua file cấu hình tạm (xóa ngay sau khi dùng), không ghi trên dòng lệnh.
- Với SQLite, script chép file `db.sqlite3`. `restore_db.ps1` hỏi xác nhận trước khi ghi đè.

### Dọn ảnh bỏ ngang

Ảnh tải lên mà người dùng không bấm lưu, ảnh gửi qua API dự đoán, hoặc ảnh còn sót lại sau lỗi sẽ thành "ảnh mồ côi"
(không còn dòng nào trong CSDL trỏ tới):

```powershell
.venv\Scripts\python.exe manage.py cleanup_uploads --dry-run   # liệt kê
.venv\Scripts\python.exe manage.py cleanup_uploads             # xóa ảnh mồ côi cũ hơn 24 giờ
```

Chỉ xóa ảnh cũ hơn `--hours` (mặc định 24), để không đụng ảnh của người đang ở trang xác nhận. Có thể đặt lịch chạy
hằng ngày bằng Task Scheduler của Windows.

## Bảo mật và quyền riêng tư

- **Ảnh là dữ liệu cá nhân.** Mọi URL `/media/...` đi qua view kiểm tra quyền ([config/media.py](config/media.py)).
  Người dùng chỉ xem được ảnh bữa ăn của mình, hoặc ảnh vừa tải lên trong phiên của mình. Ảnh phản hồi chỉ admin
  xem được. Không có quyền thì nhận 404, kể cả khi đoán đúng URL.
- Ảnh lưu lại được ghi mới từ pixel nên **không còn metadata EXIF** (kể cả tọa độ GPS). Tên file là chuỗi ngẫu nhiên.
- Ảnh chỉ được dùng để train khi người dùng **tick đồng ý**, và điều này được ràng buộc ngay trong CSDL. Admin có
  thể loại ảnh khỏi dữ liệu train.
- Xóa bữa ăn thì xóa luôn ảnh gốc.
- Mật khẩu băm PBKDF2 (Django). Form có CSRF token. Đăng xuất chỉ nhận POST.
- Mọi truy vấn nhật ký đều lọc theo người đang đăng nhập: sửa/xóa bữa ăn của người khác trả về 404.
- Chế độ demo `DEBUG=False`: không lộ trang lỗi chi tiết; `SECRET_KEY` và mật khẩu CSDL nằm trong `.env`
  (không đưa lên git).
- Upload: kiểm tra đúng là ảnh (Pillow), chỉ nhận JPG/PNG/WEBP, tối đa 10 MB.

## Lựa chọn kỹ thuật (để trình bày khi bảo vệ)

### Web và CSDL

- **Django thay vì FastAPI:** có sẵn ORM + migration + auth + trang admin, phủ phần lớn yêu cầu đồ án (đăng nhập,
  CSDL, trang quản trị) mà không phải tự viết. FastAPI mạnh ở API bất đồng bộ, mà đồ án không cần.
- **Render phía server (Django template):** toàn bộ logic nằm ở Python; không cần React hay Node.
- **MySQL 8:** CHECK constraint (≥ 8.0.16), functional index (≥ 8.0.13), JSON, InnoDB transaction.
  Các quyết định riêng cho MySQL (một model active, cột `eaten_date`, utf8mb4) có trong
  [docs/database.md](docs/database.md#các-quyết-định-thiết-kế-để-trình-bày-khi-bảo-vệ).
- **Truy vấn thống kê bằng ORM:** chạy được trên cả MySQL lẫn SQLite. SQL tương đương có trong docs để trình bày.
- **PredictionService tách riêng:** view không phụ thuộc PyTorch; model nạp một lần mỗi process; hot-reload khi
  admin đổi model; dễ test bằng model giả.
- **waitress + whitenoise:** chạy được trên Windows, thuần Python, không cần cấu hình nginx/IIS khi demo.

### Machine learning

- **Transfer learning:** backbone đã học đặc trưng ảnh (cạnh, kết cấu, hình dạng) trên 1,2 triệu ảnh ImageNet,
  chỉ cần học lại lớp phân loại cho 30 món. Vài trăm ảnh mỗi lớp là đủ, train trên RTX 3060 chỉ mất vài chục phút.
- **EfficientNet-B0:** khoảng 5,3 triệu tham số, chính xác hơn MobileNetV3 mà vẫn dự đoán trên CPU trong vài
  chục ms. Web có thể chạy trên laptop không cần GPU.
- **Train 2 pha (freeze → fine-tune):** lớp phân loại mới khởi tạo ngẫu nhiên. Mở backbone ngay thì gradient
  lớn sẽ phá trọng số pretrained, nên train head trước rồi mới tinh chỉnh backbone với lr nhỏ hơn 10 lần.
- **Augmentation** (cắt, lật, xoay, đổi màu, che một phần): mô phỏng ảnh chụp thật (góc chụp, ánh sáng quán ăn,
  đũa/thìa che món) để model không học thuộc ảnh train.
- **Early stopping + lưu checkpoint tốt nhất theo val accuracy (bằng nhau thì chọn val loss thấp hơn):** tránh
  overfit. Tập test chỉ dùng đúng một lần ở cuối nên kết quả test là khách quan. Có tie-break theo loss vì web dùng
  ngưỡng độ tin cậy: hai checkpoint cùng accuracy nhưng checkpoint loss thấp hơn tự tin hơn
  (đo thực tế trên data thử: 44% → 84%).
- **Khởi tạo lại lớp phân loại với trọng số nhỏ:** mặc định của timm cho logit ban đầu rất lớn khi số lớp ít
  (loss khởi đầu 4.07 thay vì ln 5 ≈ 1.61), làm model học chậm hẳn.
- **Loại ảnh trùng trước khi chia:** ảnh trùng nằm ở cả train và test sẽ làm accuracy test cao giả.
- **Mixed precision (AMP):** tính bằng float16 trên GPU, nhanh hơn và tốn ít VRAM hơn, không giảm độ chính xác đáng kể.

## Cấu trúc thư mục

```
config/            settings.py, urls.py, wsgi.py (nạp model khi khởi động), media.py (phục vụ ảnh có kiểm tra quyền)
apps/
  accounts/        User (đăng nhập bằng email), đăng ký/đăng nhập/hồ sơ
  foods/           Food, csv_loader.py, lệnh seed_foods
  recognition/     ModelVersion, PredictionService, lưu ảnh, trang upload/xác nhận, API, register_model
  diary/           MealLog, trang chủ/nhật ký
  feedback/        FeedbackImage
templates/         base.html (design tokens + menu), _form.html, _stat_card.html, icons/, 404.html, 500.html, admin/
ml/                common.py, prepare_data.py, train.py, evaluate.py, export_feedback.py, config.yaml
  tools/           import_kaggle.py, make_toy_dataset.py
models/            model đã train (không đưa lên git)
data/              nutrition.csv, raw/, processed/
docs/              database.md (ERD + giải thích)
tests/             pytest
scripts/           setup.ps1, setup_mysql.ps1, run_demo.ps1, backup_db.ps1, restore_db.ps1
backups/           file sao lưu (không đưa lên git)
media/             ảnh upload (không đưa lên git)
```

## Giới hạn của hệ thống

- **Calories chỉ là ước tính.** Ảnh 2D không cho biết khối lượng thật; khẩu phần dựa trên giá trị mặc định
  và lựa chọn của người dùng, sai số có thể ±30% trở lên.
- Bảng dinh dưỡng là **giá trị trung bình**, cách nấu mỗi nơi mỗi khác.
- Model chỉ biết các món đã train (tập lớp đóng), mỗi ảnh một món, không xử lý mâm nhiều món.
- Ảnh HEIC (iPhone) chưa được hỗ trợ trực tiếp; trình duyệt trên iPhone thường tự chuyển sang JPEG khi upload.
- Ảnh upload rồi bỏ ngang chỉ bị dọn khi chạy `cleanup_uploads` (chưa tự động).
- Độ chính xác "thực tế" dựa trên việc người dùng có sửa nhãn hay không. Người dùng lười sửa khi model sai sẽ làm
  con số này cao hơn thật.
- Chạy demo trên máy cá nhân qua HTTP. Triển khai thật cần HTTPS, web server phía trước (nginx/IIS) và
  cấu hình `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `setup.ps1` báo chưa kết nối được MySQL | Chạy `scripts\setup_mysql.ps1` bằng PowerShell *Run as Administrator* |
| `Start-Service MySQL80`: Cannot open service | Cần quyền Administrator, hoặc mở `services.msc` → MySQL80 → Start |
| `UnicodeEncodeError` khi in tiếng Việt | Đã xử lý trong `manage.py` và `ml/`. Nếu còn gặp: `$env:PYTHONUTF8=1` |
| DataLoader treo/lỗi trên Windows khi train | Đặt `num_workers: 0` trong `ml/config.yaml` |
| `CUDA out of memory` khi train | Giảm `batch_size` (32 → 16) |
| `torch.cuda.is_available()` là False | Đang cài PyTorch bản CPU: cài lại theo lệnh CUDA ở mục *Cài thư viện ML* |
| Trang web không có ảnh/CSS khi `DEBUG=False` | Chạy `manage.py collectstatic`; ảnh chỉ hiện cho người có quyền |
| Điện thoại không vào được khi chạy `-Lan` | Cho phép Python qua Windows Firewall; điện thoại và máy cùng mạng Wi-Fi |
| Web báo "Chưa có model nào được kích hoạt" | Train rồi `register_model ... --activate`, hoặc kích hoạt trong admin |
