# VietCalo

Web app nhận diện món ăn Việt từ ảnh và ước tính calories. Người dùng chụp hoặc tải ảnh lên, model PyTorch đoán
món, web tính kcal và macro (protein, carb, fat) theo khẩu phần rồi ghi vào nhật ký ăn uống. Ảnh nào người dùng
đồng ý chia sẻ thì được giữ lại để train phiên bản model sau.

Model hiện tại nhận diện được 49 món. Bảng dinh dưỡng có 82 món; những món model chưa biết thì người dùng chọn tay
ở ô "Món khác".

Toàn bộ viết bằng Python. Phần web dùng Django 5.2 LTS, render giao diện bằng template phía server. Tailwind và
Chart.js tải qua CDN nên không cần Node.js; JavaScript thuần chỉ dùng để xem trước ảnh, tính thử kcal và vẽ biểu
đồ. CSDL chính là MySQL 8, chạy thử được bằng SQLite. Model dùng PyTorch và timm, transfer learning từ
EfficientNet-B0 đã pretrained trên ImageNet; train trên GPU, còn web dự đoán bằng CPU.

## Trạng thái

Các chức năng chính đã xong và có 124 test: đăng ký/đăng nhập, nhận diện ảnh, nhật ký ngày/tuần, trang quản trị,
thống kê độ chính xác, vòng phản hồi dữ liệu, script cài đặt và demo. Mọi thứ đã chạy trên SQLite. Phần riêng cho
MySQL (`setup_mysql.ps1`, sao lưu bằng `mysqldump`, khôi phục) và chế độ demo qua mạng LAN (`run_demo.ps1 -Lan`)
chưa được chạy thử.

## Cài đặt

Cần Windows 10/11, Python 3.11 trở lên (đã thử với 3.12) và MySQL Server 8.0 (từ 8.0.16; bản cũ hơn bỏ qua CHECK constraint mà không báo lỗi). GPU NVIDIA chỉ cần khi
train. Không dùng được MariaDB hay XAMPP vì MariaDB không hỗ trợ functional index mà bảng `model_versions` dùng để
đảm bảo chỉ có một model đang chạy.

### Cài bằng script

```powershell
cd E:\Major\Project\AI\Calories
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

`setup.ps1` làm lần lượt:

1. tạo `.venv`;
2. cài thư viện, gồm PyTorch bản CUDA nếu máy có GPU NVIDIA, không thì bản CPU;
3. tạo `.env` với `SECRET_KEY` và mật khẩu MySQL sinh ngẫu nhiên;
4. kiểm tra kết nối CSDL, chạy `migrate`, nạp bảng dinh dưỡng, chạy `collectstatic`;
5. hỏi có tạo tài khoản admin không.

Script chạy lại nhiều lần không sao.

Lần đầu chạy, script sẽ báo chưa kết nối được MySQL. Lúc đó mở PowerShell bằng *Run as Administrator* (cần quyền
này để bật service MySQL) rồi chạy:

```powershell
cd E:\Major\Project\AI\Calories
powershell -ExecutionPolicy Bypass -File scripts\setup_mysql.ps1
```

Script này bật service `MySQL80`, hỏi mật khẩu root của MySQL, tạo database `calories` (utf8mb4) và tài khoản
`calories` theo thông tin trong `.env`, đồng thời cấp quyền trên database `test_calories` để chạy test. Xong thì
chạy lại `scripts\setup.ps1`.

Muốn thử nhanh mà không cài MySQL thì dùng `scripts\setup.ps1 -Db sqlite`.

### Cài thủ công

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128   # hoặc .../whl/cpu
pip install -r requirements-ml.txt
Copy-Item .env.example .env      # rồi sửa SECRET_KEY, DATABASE_URL
```

Tạo database: đăng nhập bằng `mysql -u root -p` rồi chạy

```sql
CREATE DATABASE calories CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'calories'@'localhost' IDENTIFIED BY 'dat-mat-khau-o-day';
GRANT ALL PRIVILEGES ON calories.* TO 'calories'@'localhost';
GRANT ALL PRIVILEGES ON test_calories.* TO 'calories'@'localhost';  -- database tạm khi chạy test
FLUSH PRIVILEGES;
```

Trong `.env`, đặt `DATABASE_URL=mysql://calories:dat-mat-khau-o-day@localhost:3306/calories`
(hoặc `DATABASE_URL=sqlite:///db.sqlite3` nếu dùng SQLite).

> Nếu mật khẩu có ký tự `@ # / : %` thì phải mã hóa chúng trong URL (`@` → `%40`, `#` → `%23`, `/` → `%2F`,
> `:` → `%3A`, `%` → `%25`). Nếu không, Django sẽ đọc sai địa chỉ CSDL.

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
| Demo, bảo vệ đồ án | `powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1` | waitress, `DEBUG=False`, http://127.0.0.1:8000 |
| Demo trên điện thoại | `...\run_demo.ps1 -Lan` | điện thoại bắt cùng Wi-Fi, mở địa chỉ IP mà script in ra |

Trang người dùng ở http://127.0.0.1:8000, trang quản trị ở http://127.0.0.1:8000/admin.

Ở chế độ demo (`DEBUG=False`) trang lỗi không hiện chi tiết code. File tĩnh do whitenoise phục vụ, còn ảnh đi qua
một view kiểm tra quyền (xem [Bảo mật và quyền riêng tư](#bảo-mật-và-quyền-riêng-tư)).

### Chạy test

```powershell
.venv\Scripts\python.exe -m pytest
```

Test dùng CSDL cấu hình trong `.env`; Django tự tạo database `test_calories` rồi xóa khi xong. 124 test phủ ràng
buộc CSDL, đăng nhập, nạp dữ liệu món, pipeline ML (model nhỏ chạy trên CPU), nhận diện (dùng model giả), nhật ký,
thống kê, admin và quyền xem ảnh.

## Giao diện

Thiết kế nằm trong file Figma *VietCalo UI*: https://www.figma.com/design/r65rZ68yyEcfNxo1wgfdJe. File có bộ màu,
khoảng cách và bo góc (dạng variable), 11 kiểu chữ Be Vietnam Pro, đổ bóng; các component Button, Chip, NavBar,
StatCard, MealRow, PredictionRow, MacroBar và bộ icon; cùng 4 màn hình Hôm nay, Quét món, Xác nhận món, Tuần.

Thiết kế được đưa vào code như sau:

- Token màu và kích thước nằm trong khối `@theme` của [templates/base.html](templates/base.html), sinh ra các class
  `bg-brand-600`, `text-ink-900`, `bg-page`, `shadow-card`, `rounded-card`… Kiểu chữ là các utility `type-h1`,
  `type-body`, `type-num-xl`…; component là `card`, `btn btn-primary` / `btn-accent` / `btn-secondary` /
  `btn-ghost`, `field`. Sửa màu trong `@theme` thì cả web đổi theo.
- Icon nằm trong [templates/icons/](templates/icons/), cùng nét vẽ với icon trong Figma và tô màu bằng `text-*`.
  Cách dùng: `{% include "icons/camera.svg" with cls="size-5" %}`.
- Số viết kiểu Việt Nam: `{% load vn %}{{ value|num }}` cho ra `1.498`. Locale `vi` của Django không tự nhóm hàng
  nghìn nên cần filter này.

## Bảng dinh dưỡng và thêm món mới

Dữ liệu dinh dưỡng nằm trong `data/nutrition.csv`, mọi giá trị tính trên 100 g:

```
class_label,name,name_vi,kcal_per_100g,protein,carb,fat,default_portion_g,note
pho,Pho noodle soup,Phở,90,6,12,2,600,...
```

- `class_label` chỉ gồm `a-z 0-9 _` và phải trùng tên thư mục ảnh `data/raw/<class_label>/`.
- `seed_foods` chạy lại bao nhiêu lần cũng được: món đã có thì cập nhật, món mới thì thêm. Nếu kcal lệch quá 15% so
  với `4×protein + 4×carb + 9×fat`, lệnh sẽ cảnh báo vì nhiều khả năng nhập sai số.
- Số liệu hiện tại là ước tính ban đầu (ghi ở cột `note`). Trước khi bảo vệ nên đối chiếu với *Bảng thành phần thực
  phẩm Việt Nam* của Viện Dinh dưỡng Quốc gia và ghi nguồn.

Để thêm món mới: tạo thư mục ảnh `data/raw/<class_label>/`, thêm một dòng vào CSV, chạy `seed_foods`, rồi chạy lại
`prepare_data` và `train` như phần dưới.

## Train model

### Cài thư viện ML

Cài PyTorch bản có CUDA trước. Trên Windows, cài thẳng từ PyPI sẽ ra bản chỉ chạy CPU. Lệnh đúng cho từng máy lấy
ở https://pytorch.org/get-started/locally/. Với RTX 3060:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements-ml.txt
python -c "import torch; print(torch.cuda.is_available())"   # phải in True
```

### 1. Lấy dữ liệu

30 món đầu lấy từ dataset trên Kaggle (ví dụ *30VNFoods*). Giải nén rồi chạy lệnh dưới để chép vào `data/raw/`.
Tên thư mục được chuẩn hóa (`Bún bò Huế` thành `bun_bo_hue`) và các thư mục Train/Validate/Test của Kaggle được gộp
lại:

```powershell
python -m ml.tools.import_kaggle --src "D:\Downloads\30VNFoods"
```

Script in ra những lớp chưa có trong `nutrition.csv`. Tên nào lệch thì sửa bằng `--rename "Ten goc=class_label"`.

19 món còn lại (bún chả, bánh bao, bò kho, cơm rang, mì xào giòn...) lấy từ bộ
[vn-food-combined-2026](https://huggingface.co/datasets/jeandeanny/vn-food-combined-2026) trên Hugging Face
(khoảng 5,7 GB, định dạng parquet). Bảng ghép tên món nằm trong `MAPPING` của `ml/tools/import_hf.py`:

```powershell
pip install pyarrow
python -c "from huggingface_hub import snapshot_download; snapshot_download('jeandeanny/vn-food-combined-2026', repo_type='dataset', local_dir=r'D:\hf_vnfood103')"
python -m ml.tools.import_hf --src "D:\hf_vnfood103"
```

Các món có trong `nutrition.csv` nhưng chưa có ảnh (phở xào, phở cuốn, nem rán, trứng chiên...) thì model không
nhận diện được. Người dùng chọn tay ở ô "Món khác", và ảnh họ đồng ý chia sẻ sau này xuất ra bằng
`ml.export_feedback` để train.

Chưa có dữ liệu thật mà muốn thử pipeline thì chạy `python -m ml.tools.make_toy_dataset`. Lệnh này tạo
`data/raw_toy/` gồm 5 lớp ảnh hình học.

### 2. Chuẩn bị dữ liệu

```powershell
python -m ml.prepare_data
# chạy thử nhanh với 5 lớp, 50 ảnh/lớp:
python -m ml.prepare_data --classes pho,banh_mi,com_tam,bun_bo_hue,goi_cuon --max-per-class 50
```

Lệnh kiểm tra mỗi thư mục ảnh đều có dòng tương ứng trong `nutrition.csv`, loại ảnh hỏng, quá nhỏ hoặc trùng lặp,
chia train/val/test theo tỉ lệ 70/15/15 trong từng lớp với seed cố định, và resize cạnh ngắn về 256 px. Kết quả nằm
trong `data/processed/`, kèm `stats.json`, `split.csv` (ảnh nào thuộc tập nào) và `bad_images.txt`.

### 3. Train

Tham số nằm trong [ml/config.yaml](ml/config.yaml): backbone, số epoch, batch size, learning rate, kích thước ảnh,
augmentation, đóng băng backbone, trọng số theo lớp... Một số tham số ghi đè được từ dòng lệnh.

```powershell
python -m ml.train                          # train theo config.yaml, tự đánh giá trên tập test
python -m ml.train --register --activate    # train xong ghi vào bảng model_versions và dùng luôn
python -m ml.train --epochs 30 --backbone mobilenetv3_large_100 --version v2-mobilenet
```

Kết quả nằm trong `models/<version>/`: `model.pt` (checkpoint có val accuracy cao nhất), `class_list.json`,
`config.yaml`, `history.csv`, `training_curves.png`, `metrics.json` và `eval_test/`.

Nếu DataLoader báo lỗi trên Windows thì đặt `num_workers: 0` trong config. Thiếu VRAM thì giảm `batch_size`.

`class_weighting` đang bật vì dữ liệu lệch: các món lấy từ Hugging Face chỉ có khoảng 150 đến 250 ảnh, còn các món
từ Kaggle có 500 đến 1000 ảnh.

### Kết quả hiện tại

Phiên bản `20261107-0125-efficientnet_b0`, train trên RTX 3060:

| Chỉ số | Giá trị |
|---|---|
| Số món | 49 |
| Ảnh train / val | 20.850 / 4.465 |
| Accuracy trên tập test | 86,8% |
| Top-3 accuracy trên tập test | 95,0% |
| Thời gian train | khoảng 21 phút (25 epoch) |

Bản trước đó (`20261107-0023-efficientnet_b0`, 30 món) đạt 87,7% test accuracy và 95,9% top-3.

### 4. Đánh giá

`train` đã tự đánh giá trên tập test. Muốn chạy lại riêng:

```powershell
python -m ml.evaluate --model-dir models\<version>
```

Kết quả nằm trong `eval_test/`: `metrics.json` (accuracy, top-3, macro precision/recall/F1), `per_class.csv`,
`confusion_matrix.png` và `misclassified.csv` (các ảnh bị đoán sai, ảnh sai mà model tự tin nhất xếp đầu).

### 5. Đăng ký model vào CSDL

Nếu lúc train chưa dùng `--register`:

```powershell
python manage.py register_model models\<version> --activate
```

Lệnh sẽ từ chối kích hoạt nếu model có lớp chưa có trong bảng `foods`, vì web không tính được calo cho lớp đó. Muốn
đổi model đang dùng thì vào admin, mục *Phiên bản model*, chọn model rồi chạy action *Đặt làm model đang dùng*.

## Nhận diện trên web

1. Người dùng bấm *Quét món* (`/scan/`) và lấy ảnh theo một trong hai cách.
   - Camera (webcam laptop hoặc camera điện thoại): bấm *Bật camera* và cho trình duyệt dùng camera. Khi bật
     *Nhận diện trực tiếp*, khoảng mỗi giây trình duyệt gửi một khung hình nhỏ (384 px) tới
     `/api/predict/?preview=1` và hiện tên món cùng độ tin cậy ngay trên khung hình: xanh là đủ tin cậy, vàng là
     chưa chắc. Chế độ này không lưu ảnh lên server. Bấm *Chụp* (hoặc phím Space) để chụp ảnh đầy đủ, tối đa
     1280 px. Máy có nhiều camera thì đổi được camera; rời trang thì camera tự tắt.
   - Chọn ảnh có sẵn. Trên điện thoại, nút này cũng mở được camera của máy.

   Ảnh được xem trước trên trình duyệt trước khi gửi.

   > Trình duyệt chỉ cho web dùng camera khi trang chạy trên https hoặc localhost / 127.0.0.1. Mở bằng địa chỉ IP
   > qua mạng LAN (`run_demo.ps1 -Lan`, `http://192.168...`) thì tab Camera bị tắt. Khi đó điện thoại dùng
   > *Chọn ảnh có sẵn*, nút này vẫn mở được camera của máy.
2. Server xoay ảnh theo EXIF, thu nhỏ để cạnh dài không quá 1280 px, xóa metadata (kể cả GPS), lưu vào
   `media/uploads/YYYY/MM/<tên ngẫu nhiên>.jpg`, rồi chạy model.
3. Trang xác nhận hiện 3 món model đoán cao nhất kèm độ tin cậy.
   - Nếu món đầu đạt ngưỡng (`CONFIDENCE_THRESHOLD`, mặc định 0.6), món đó được chọn sẵn và người dùng vẫn đổi được.
   - Nếu dưới ngưỡng, trang báo "Model chưa chắc chắn" và người dùng phải tự chọn.
   - Nếu món đúng không nằm trong 3 món đó, người dùng gõ tên vào ô "Món khác" (tìm được cả khi gõ không dấu). Như
     vậy là sửa nhãn.
4. Người dùng chọn khẩu phần Nhỏ / Vừa / Lớn (0.7 / 1.0 / 1.3 lần khẩu phần mặc định) hoặc nhập số gram. Trình
   duyệt tính thử kcal ngay; giá trị được lưu là do server tính lại.
5. Bấm lưu thì web ghi một dòng `meal_logs` (lưu lại kcal/macro tại thời điểm đó, 3 món model đoán,
   `was_corrected`, phiên bản model). Nếu người dùng tick đồng ý, web ghi thêm `feedback_images` kèm một bản sao
   ảnh trong `media/feedback/` để train lại sau.

Kết quả nhận diện được giữ tạm trong session đến khi người dùng bấm lưu, nên CSDL không có dòng rác.

### Model trên web

`PredictionService` ([apps/recognition/services.py](apps/recognition/services.py)) nạp model đang active một lần
khi server khởi động (`config/wsgi.py`). Cứ mỗi `MODEL_CHECK_INTERVAL` giây (mặc định 10), service hỏi CSDL xem
model active có đổi không, nếu đổi thì tự nạp model mới mà không cần restart server. Admin muốn nạp lại ngay thì gửi
`POST /recognition/reload/`.

Mặc định model chạy trên CPU (`ML_DEVICE=cpu` trong `.env`) để web chạy được trên mọi máy. Bước tiền xử lý ảnh trên
web dùng chung hàm với lúc train và evaluate (`load_image`, `build_transforms` trong `ml/common.py`), nên ảnh đưa vào
model lúc dùng thật giống hệt lúc train.

### API JSON

`POST /api/predict/` (multipart, field `image`) trả về 3 món đoán cao nhất. API cần đăng nhập và gửi kèm CSRF
token. Thêm `?preview=1` thì ảnh không được lưu; camera dùng chế độ này khi nhận diện trực tiếp.

```json
{"model_version": "...", "is_confident": true, "threshold": 0.6,
 "predictions": [{"label": "pho", "confidence": 0.84, "name_vi": "Phở", "kcal_per_100g": 90, "default_portion_g": 600}, ...]}
```

## Nhật ký ăn uống

Trang *Hôm nay* (`/`) hiện tổng kcal so với mục tiêu. Thanh tiến độ màu xanh dương khi dưới 90%, xanh lá khi từ 90
đến 110%, đỏ khi vượt 110%. Bên dưới là số gram và tỉ lệ năng lượng từ protein, carb, fat, rồi danh sách món theo
từng bữa kèm ảnh. Bữa nào do AI nhận diện thì có độ tin cậy, và ghi "đã sửa nhãn" nếu người dùng đổi món. Đổi ngày
bằng mũi tên hoặc ô chọn ngày.

Trang *Tuần* (`/week/`) có biểu đồ cột kcal từng ngày với đường mục tiêu (bấm vào cột để mở ngày đó), biểu đồ tròn
nguồn năng lượng, bảng chi tiết, các món ăn nhiều nhất và kcal theo bữa. Trung bình mỗi ngày chỉ tính những ngày có
ghi nhật ký.

Người dùng có thể:

- sửa bữa ăn: đổi món, khẩu phần, bữa, giờ ăn, và kcal/macro được tính lại. Đổi món của bữa do AI nhận diện được
  tính là sửa nhãn (`was_corrected`) và nhãn của ảnh phản hồi cũng đổi theo, trừ ảnh đã dùng để train;
- xóa bữa ăn: ảnh gốc bị xóa theo, còn bản sao ảnh phản hồi (nếu đã đồng ý) vẫn được giữ;
- thêm bữa thủ công khi model không biết món hoặc khi ghi bù ngày trước.

## Quản trị và vòng phản hồi dữ liệu

Tài khoản admin (`is_staff`) thấy thêm hai mục trên menu.

Trang *Thống kê* (`/recognition/stats/`) đo độ chính xác thực tế của model, tức là món người dùng xác nhận có trùng
với món model đoán không. Trang có:

- accuracy top-1, top-3, độ tin cậy trung bình và tỉ lệ phải hỏi lại người dùng (dưới ngưỡng);
- bảng và biểu đồ so sánh các phiên bản model, đặt val/test accuracy lúc train cạnh độ chính xác thực tế;
- độ chính xác theo từng nhóm độ tin cậy, để xem khi model "tự tin" thì có đúng thật không và chọn ngưỡng cho hợp;
- các cặp món hay bị nhầm, món nhận diện kém nhất, số ảnh phản hồi, món phổ biến trên toàn hệ thống;
- nút *Nạp lại model*.

Trang *Quản trị* (`/admin/`) gồm:

- *Món ăn*: sửa dinh dưỡng ngay trong danh sách, xem mỗi món được ăn bao nhiêu lần và có bao nhiêu ảnh phản hồi,
  nút *Nạp lại từ nutrition.csv*.
- *Ảnh phản hồi*: ảnh thu nhỏ, sửa nhãn đúng ngay trong danh sách, lọc những ảnh model đoán sai. Các action: xuất
  sang `data/raw`, loại ảnh xấu khỏi dữ liệu train, đánh dấu chưa dùng để xuất lại.
- *Phiên bản model*: val/test accuracy, số lượt dùng, độ chính xác thực tế, action *Đặt làm model đang dùng* (nạp
  ngay), nút *Thống kê & so sánh* và *Nạp lại model*.
- *Nhật ký ăn uống*: ảnh thu nhỏ, lọc theo model, theo sửa nhãn hoặc theo ngày.

### Train lại bằng ảnh phản hồi

```powershell
python -m ml.export_feedback --dry-run          # xem sẽ xuất bao nhiêu ảnh, mỗi lớp mấy ảnh
python -m ml.export_feedback                    # chép sang data/raw/<class_label>/feedback_<id>.jpg
python -m ml.prepare_data                       # chia lại train/val/test (ảnh trùng tự bị loại)
python -m ml.train --register                   # train phiên bản mới, ghi vào model_versions
```

Sau đó so sánh bản mới với bản cũ ở trang *Thống kê*, rồi kích hoạt bản mới trong admin.

- Chỉ ảnh người dùng đã đồng ý và chưa dùng để train mới được xuất. CSDL có ràng buộc chặn việc đánh dấu "đã train"
  cho ảnh chưa được đồng ý.
- Nhãn của ảnh là món người dùng xác nhận, không lấy món model đoán.
- `--only-corrected` chỉ xuất những ảnh model đoán sai. Đây là những ảnh model cần học lại nhất.
- Lệnh chạy lại nhiều lần được; ảnh đã xuất sẽ không bị xuất lần hai.
- Nên duyệt ảnh trong admin trước khi xuất, vì người dùng có thể chọn nhầm món và ảnh sai nhãn làm model tệ đi. Nếu
  admin loại, sửa nhãn hoặc xóa một ảnh đã xuất, file trong `data/raw` cũng bị gỡ theo; ảnh được sửa nhãn sẽ xuất
  lại vào thư mục nhãn mới ở lần chạy sau.

## Vận hành

### Sao lưu và khôi phục

```powershell
powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1              # backups\calories_<ngày_giờ>.sql
powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1 -WithMedia   # kèm ảnh: backups\media_<ngày_giờ>.zip
powershell -ExecutionPolicy Bypass -File scripts\restore_db.ps1 backups\calories_20261019_2300.sql
```

Với MySQL, script dùng `mysqldump --single-transaction`. InnoDB cho phép sao lưu nhất quán mà không khóa bảng nên
web vẫn chạy trong lúc sao lưu. Mật khẩu CSDL được đưa cho `mysqldump` qua một file cấu hình tạm và file này bị xóa
ngay sau đó, nên mật khẩu không xuất hiện trên dòng lệnh. Với SQLite, script chép file `db.sqlite3`.
`restore_db.ps1` hỏi xác nhận trước khi ghi đè.

### Dọn ảnh bỏ ngang

Ảnh tải lên mà người dùng không bấm lưu, ảnh gửi qua API dự đoán, hay ảnh sót lại sau lỗi đều thành ảnh mồ côi:
không còn dòng nào trong CSDL trỏ tới.

```powershell
.venv\Scripts\python.exe manage.py cleanup_uploads --dry-run   # liệt kê
.venv\Scripts\python.exe manage.py cleanup_uploads             # xóa ảnh mồ côi cũ hơn 24 giờ
```

Lệnh chỉ xóa ảnh cũ hơn `--hours` (mặc định 24) để không đụng tới ảnh của người đang ở trang xác nhận. Có thể đặt
lịch chạy hằng ngày bằng Task Scheduler của Windows.

## Bảo mật và quyền riêng tư

- Ảnh món ăn được coi là dữ liệu cá nhân. Mọi URL `/media/...` đều đi qua view kiểm tra quyền
  ([config/media.py](config/media.py)). Người dùng chỉ xem được ảnh bữa ăn của mình hoặc ảnh vừa tải lên trong phiên
  của mình; ảnh phản hồi chỉ admin xem được. Không có quyền thì nhận 404, kể cả khi đoán đúng URL.
- Ảnh được ghi lại từ pixel nên không còn metadata EXIF, kể cả tọa độ GPS. Tên file là chuỗi ngẫu nhiên.
- Ảnh chỉ được dùng để train khi người dùng tick đồng ý, và điều này được ràng buộc ngay trong CSDL. Admin có thể
  loại ảnh khỏi dữ liệu train.
- Xóa bữa ăn thì ảnh gốc bị xóa theo.
- Mật khẩu được băm bằng PBKDF2 (mặc định của Django). Form có CSRF token. Đăng xuất chỉ nhận POST.
- Mọi truy vấn nhật ký đều lọc theo người đang đăng nhập, nên sửa hay xóa bữa ăn của người khác sẽ nhận 404.
- Ở chế độ demo (`DEBUG=False`) không lộ trang lỗi chi tiết. `SECRET_KEY` và mật khẩu CSDL nằm trong `.env`, file
  này không đưa lên git.
- Upload được kiểm tra bằng Pillow để chắc là ảnh thật, chỉ nhận JPG/PNG/WEBP, tối đa 10 MB.

## Lựa chọn kỹ thuật (để trình bày khi bảo vệ)

### Web và CSDL

- Chọn Django thay vì FastAPI vì Django có sẵn ORM, migration, đăng nhập và trang admin, đủ cho phần lớn yêu cầu
  của đồ án mà không phải tự viết. Thế mạnh của FastAPI là API bất đồng bộ, đồ án không cần.
- Render phía server bằng Django template để toàn bộ logic nằm ở Python, không cần React hay Node.
- MySQL 8 có CHECK constraint (từ 8.0.16), functional index (từ 8.0.13), kiểu JSON và transaction của InnoDB.
  Functional index được dùng để đảm bảo tại một thời điểm chỉ có một model active. Bảng `meal_logs` có thêm cột
  `eaten_date` kiểu DATE vì nhóm theo ngày bằng `TruncDate` trên MySQL cần bảng múi giờ, mà MySQL trên Windows mặc
  định không có; cột riêng còn đánh index được. CSDL dùng bảng mã utf8mb4.
- Truy vấn thống kê viết bằng ORM nên chạy được trên cả MySQL lẫn SQLite.
- `PredictionService` tách riêng khỏi view: view không phụ thuộc PyTorch, model chỉ nạp một lần mỗi process, tự nạp
  lại khi admin đổi model, và dễ test bằng model giả.
- waitress và whitenoise viết thuần Python, chạy được trên Windows, khi demo không phải cấu hình nginx hay IIS.

### Machine learning

- Transfer learning: backbone đã học các đặc trưng ảnh (cạnh, kết cấu, hình dạng) trên 1,2 triệu ảnh ImageNet, nên
  chỉ cần học lại lớp phân loại cho 49 món. Vài trăm ảnh mỗi lớp là đủ, và train trên RTX 3060 mất khoảng 20 phút.
- EfficientNet-B0 có khoảng 5,3 triệu tham số, chính xác hơn MobileNetV3 mà vẫn dự đoán trên CPU trong vài chục ms,
  nên web chạy được trên laptop không có GPU.
- Train hai pha, đóng băng backbone trước rồi mới tinh chỉnh. Lớp phân loại mới được khởi tạo ngẫu nhiên; nếu mở
  backbone ngay thì gradient lớn sẽ phá trọng số pretrained. Vì vậy model train riêng lớp phân loại vài epoch đầu,
  sau đó mới tinh chỉnh backbone với learning rate nhỏ hơn 10 lần.
- Augmentation (cắt, lật, xoay, đổi màu, che một phần ảnh) mô phỏng ảnh chụp thật, với góc chụp khác nhau, ánh sáng
  quán ăn, đũa thìa che món, để model không học thuộc ảnh train.
- Early stopping và lưu checkpoint tốt nhất theo val accuracy để tránh overfit; hai checkpoint bằng accuracy thì
  chọn cái có val loss thấp hơn. Tập test chỉ dùng đúng một lần ở cuối nên kết quả test khách quan. Phải so thêm
  loss vì web dùng ngưỡng độ tin cậy: với cùng accuracy, checkpoint loss thấp hơn tự tin hơn. Trên dữ liệu thử, độ
  tin cậy đo được tăng từ 44% lên 84%.
- Lớp phân loại được khởi tạo lại với trọng số nhỏ. Mặc định của timm cho logit ban đầu rất lớn khi số lớp ít (loss
  khởi đầu 4.07 thay vì ln 5 ≈ 1.61), làm model học chậm hẳn.
- Loại ảnh trùng trước khi chia tập. Nếu một ảnh nằm ở cả train lẫn test, accuracy trên test sẽ cao giả.
- Mixed precision (AMP) tính bằng float16 trên GPU, nhanh hơn và tốn ít VRAM hơn mà độ chính xác gần như không đổi.
- Trọng số loss theo lớp (`class_weighting`) bù cho các món ít ảnh, để model không thiên về các món nhiều ảnh.

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
  tools/           import_kaggle.py, import_hf.py, make_toy_dataset.py
models/            model đã train (không đưa lên git)
data/              nutrition.csv, raw/, processed/
tests/             pytest
scripts/           setup.ps1, setup_mysql.ps1, run_demo.ps1, backup_db.ps1, restore_db.ps1
backups/           file sao lưu (không đưa lên git)
media/             ảnh upload (không đưa lên git)
```

## Giới hạn

- Calories chỉ là ước tính. Ảnh 2D không cho biết khối lượng thật; khẩu phần dựa vào giá trị mặc định và lựa chọn
  của người dùng, nên sai số có thể từ ±30% trở lên.
- Bảng dinh dưỡng là giá trị trung bình, trong khi mỗi nơi nấu một kiểu.
- Model chỉ biết những món đã train. Mỗi ảnh chỉ nhận một món; ảnh cả mâm nhiều món thì không xử lý được.
- Chưa đọc trực tiếp ảnh HEIC của iPhone. Thường thì trình duyệt trên iPhone tự chuyển sang JPEG khi upload.
- Ảnh tải lên rồi bỏ ngang chỉ bị dọn khi chạy `cleanup_uploads`, chưa có lịch tự động.
- Độ chính xác thực tế dựa vào việc người dùng có sửa nhãn hay không. Nếu người dùng lười sửa khi model đoán sai,
  con số này sẽ cao hơn thật.
- Bản demo chạy trên máy cá nhân qua HTTP. Triển khai thật cần HTTPS, một web server đứng trước (nginx hoặc IIS) và
  bật `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

## Nguồn dữ liệu và giấy phép

Ảnh của 19 món thêm sau lấy từ *Vietnamese Food Combined 2026* (jeandeanny, Hugging Face). Bộ này là bản làm sạch
của *VNFood 30 + 3 + 100* (Lê Anh Duy, Kaggle), vốn gộp từ 30VNFoods, Vietnamese-foods-extended và 100 Vietnamese
Food. Giấy phép là CC BY-NC-SA 4.0: chỉ dùng phi thương mại, phải ghi nguồn, và bản phái sinh phải giữ cùng giấy
phép. Model train trên dữ liệu này cũng chỉ nên dùng cho học tập và nghiên cứu.

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `setup.ps1` báo chưa kết nối được MySQL | Chạy `scripts\setup_mysql.ps1` trong PowerShell mở bằng *Run as Administrator* |
| `Start-Service MySQL80`: Cannot open service | Cần quyền Administrator, hoặc mở `services.msc`, chọn MySQL80 rồi bấm Start |
| `UnicodeEncodeError` khi in tiếng Việt | `manage.py` và `ml/` đã xử lý. Nếu vẫn gặp thì đặt `$env:PYTHONUTF8=1` |
| DataLoader treo hoặc lỗi trên Windows khi train | Đặt `num_workers: 0` trong `ml/config.yaml` |
| `CUDA out of memory` khi train | Giảm `batch_size`, ví dụ từ 32 xuống 16 |
| `torch.cuda.is_available()` trả về False | Máy đang cài PyTorch bản CPU. Cài lại theo lệnh CUDA ở mục *Cài thư viện ML* |
| Web không có ảnh/CSS khi `DEBUG=False` | Chạy `manage.py collectstatic`. Ảnh chỉ hiện với người có quyền xem |
| Điện thoại không vào được khi chạy `-Lan` | Cho Python qua Windows Firewall; điện thoại và máy tính phải cùng mạng Wi-Fi |
| Web báo "Chưa có model nào được kích hoạt" | Train rồi chạy `register_model ... --activate`, hoặc kích hoạt trong admin |
