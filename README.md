# VietCalo

Web app nhận diện món ăn Việt từ ảnh và ước tính calories. Người dùng chụp hoặc tải ảnh lên, model PyTorch đoán
món, web tính kcal và macro (protein, carb, fat) theo khẩu phần rồi ghi vào nhật ký ăn uống. Ảnh nào người dùng
đồng ý chia sẻ thì được giữ lại để train phiên bản model sau.

- Model nhận diện **49 món**, accuracy **86,8%**, top-3 **95,0%** trên tập test (4.465 ảnh).
- Model chọn luôn món có xác suất cao nhất. Nếu đoán sai hoặc món chưa có trong model, người dùng gõ tên để đổi
  (bảng dinh dưỡng có 82 món).
- Toàn bộ viết bằng Python: Django 5.2 (web), PyTorch + timm (model EfficientNet-B0), CSDL MySQL 8 (chạy thử nhanh
  được bằng SQLite).
- 113 test tự động (pytest).

## Chức năng

| Người dùng | Quản trị viên |
|---|---|
| Đăng ký, đăng nhập bằng email | Quản lý các phiên bản model, đổi model không cần restart |
| Chụp ảnh bằng camera hoặc tải ảnh lên, AI chọn món | Sửa bảng dinh dưỡng, duyệt ảnh phản hồi |
| Chọn khẩu phần, lưu vào nhật ký | Xuất ảnh phản hồi để train lại |
| Xem nhật ký theo ngày, biểu đồ theo tuần | |

## Cài đặt và chạy

Cần Python 3.11 trở lên. GPU NVIDIA chỉ cần khi train.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # máy có GPU: .../whl/cu128
pip install -r requirements.txt
Copy-Item .env.example .env
```

Mở `.env`, đặt `SECRET_KEY` và chọn CSDL:

- SQLite (không cần cài gì): `DATABASE_URL=sqlite:///db.sqlite3`
- MySQL 8.0.16 trở lên (không dùng được MariaDB/XAMPP vì thiếu functional index): `mysql -u root -p` rồi chạy

  ```sql
  CREATE DATABASE calories CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER 'calories'@'localhost' IDENTIFIED BY 'dat-mat-khau-o-day';
  GRANT ALL PRIVILEGES ON calories.* TO 'calories'@'localhost';
  GRANT ALL PRIVILEGES ON test_calories.* TO 'calories'@'localhost';  -- database tạm khi chạy test
  FLUSH PRIVILEGES;
  ```

  và đặt `DATABASE_URL=mysql://calories:dat-mat-khau-o-day@localhost:3306/calories`

```powershell
python manage.py migrate
python manage.py seed_foods          # nạp bảng dinh dưỡng từ data/nutrition.csv
python manage.py createsuperuser
```

Model đã train không nằm trong git (file `model.pt` khoảng 16 MB). Giải nén thư mục model vào `models/` rồi đăng ký:

```powershell
python manage.py register_model models\20261107-0125-efficientnet_b0 --activate
python manage.py runserver
```

Mở http://127.0.0.1:8000 (trang quản trị: http://127.0.0.1:8000/admin).

Chạy kiểu demo (`DEBUG=False`, web server waitress, không hiện trang lỗi chi tiết):

```powershell
$env:DEBUG="False"; python manage.py collectstatic --noinput
waitress-serve --listen=127.0.0.1:8000 config.wsgi:application
```

Chạy test (dùng SQLite trong RAM, không cần bật MySQL):

```powershell
$env:DATABASE_URL="sqlite:///:memory:"; python -m pytest
```

## Deploy lên Railway (web) và Aiven (MySQL)

Railway build web từ `Dockerfile` ở gốc repo, CSDL là một service MySQL 8 trên Aiven. Mỗi lần khởi động, container tự
chạy `migrate` rồi `prepare_deploy` (nạp bảng dinh dưỡng nếu bảng còn trống, tải và đăng ký model, tạo tài khoản
admin), sau đó mới chạy web bằng waitress.

1. **Aiven**: tạo service MySQL, vào trang service chép *Service URI* (dạng
   `mysql://avnadmin:...@ten-service.aivencloud.com:12345/defaultdb?ssl-mode=REQUIRED`).
2. **Model**: nén thư mục model (có `model.pt`, `class_list.json`, `metrics.json`) thành file `.zip` rồi đưa lên nơi có
   link tải trực tiếp, ví dụ mục Releases của repo GitHub.
3. **Railway**: New Project → Deploy from GitHub repo → chọn repo này, rồi vào tab Variables đặt:

   | Biến | Giá trị |
   |---|---|
   | `SECRET_KEY` | chuỗi ngẫu nhiên, tạo bằng `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `DATABASE_URL` | Service URI của Aiven, giữ nguyên phần `?ssl-mode=REQUIRED` |
   | `MODEL_URL` | link tải file `.zip` ở bước 2 |
   | `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` | tài khoản đăng nhập trang `/admin` |

4. Vào Settings → Networking → Generate Domain để có địa chỉ `https://<tên>.up.railway.app`. Nên đặt thêm Healthcheck
   Path là `/accounts/login/` để Railway chờ web sẵn sàng rồi mới chuyển sang bản mới.
5. Ổ đĩa của container bị xoá mỗi lần deploy. Muốn giữ ảnh người dùng tải lên thì gắn một Volume vào `/app/media`.

Không cần đặt `ALLOWED_HOSTS`: web tự nhận domain qua biến `RAILWAY_PUBLIC_DOMAIN` mà Railway cấp.

**Truy vấn bằng MySQL Workbench**: tạo connection kiểu Standard (TCP/IP) với Hostname, Port, Username (`avnadmin`),
Password lấy từ trang service của Aiven, Default Schema là `defaultdb`; trong tab SSL đặt Use SSL = `Require`. Đây là
CSDL web đang dùng nên `UPDATE`/`DELETE` có hiệu lực ngay trên web.

## Train model

```powershell
python -m ml.import_kaggle --src "<thư mục 30VNFoods>"           # chép ảnh vào data/raw/<class_label>/
python -m ml.import_hf --src "<thư mục dataset Hugging Face>"
python -m ml.prepare_data                                        # lọc ảnh hỏng/trùng, chia 70/15/15
python -m ml.train --register --activate                         # train theo ml/config.yaml, đánh giá, đăng ký
python -m ml.evaluate --model-dir models\<version>               # đánh giá lại riêng
```

Kết quả nằm trong `models/<version>/`: `model.pt`, `class_list.json`, `history.csv`, `training_curves.png`,
`metrics.json` và `eval_test/` (confusion matrix, chỉ số từng lớp, ảnh đoán sai).

### Kết quả

| Phiên bản | Số món | Test accuracy | Top-3 | Thời gian train (RTX 3060) |
|---|---|---|---|---|
| `20261107-0023-efficientnet_b0` | 30 | 87,7% | 95,9% | 16 phút |
| `20261107-0125-efficientnet_b0` (đang dùng) | 49 | 86,8% | 95,0% | 21 phút |
| `ablation-scratch-efficientnet_b0` (không pretrained) | 49 | 59,2% | 79,2% | 20 phút |

Dòng cuối là thí nghiệm train cùng cấu hình nhưng không dùng trọng số pretrained, để so sánh với transfer learning.

### Train lại bằng ảnh phản hồi

```powershell
python manage.py export_feedback    # chép ảnh người dùng đã đồng ý sang data/raw/
python -m ml.prepare_data
python -m ml.train --register
```

## Cấu trúc thư mục

Code web tổ chức theo mô hình MVC, gom trong một app Django là `app/`:

```
app/
  models/        M – bảng CSDL: user, food, model_version, meal_log, feedback_image
  views/         V – giao diện HTML (base.html, accounts/, diary/, recognition/, icons/)
  controllers/   C – nhận request, gọi model/service, trả về view: accounts, diary, recognition, media
  services/      nghiệp vụ: nhận diện ảnh, xử lý ảnh, nhật ký, tổng hợp theo ngày/tuần, ảnh phản hồi, đọc CSV
  forms/         kiểm tra dữ liệu người dùng gửi lên
  admin/         trang quản trị
  management/    lệnh manage.py: seed_foods, register_model, cleanup_uploads, export_feedback, prepare_deploy
  urls.py        ánh xạ URL tới controller
config/          settings, urls, wsgi (nạp model khi khởi động)
Dockerfile       image chạy web khi deploy (Railway)
ml/              nhập dữ liệu, chuẩn bị dữ liệu, train, đánh giá model (config.yaml)
data/            nutrition.csv
models/          model đã train (không đưa lên git)
tests/           113 test (pytest)
```

Django gọi mô hình này là MVT: phần Django gọi là "view" chính là controller (thư mục `controllers/`), còn
"template" là view (thư mục `views/`).

## Nguồn dữ liệu và giấy phép

- 30 món: dataset *30VNFoods* (Kaggle).
- 19 món: [vn-food-combined-2026](https://huggingface.co/datasets/jeandeanny/vn-food-combined-2026) (Hugging Face),
  giấy phép CC BY-NC-SA 4.0, chỉ dùng phi thương mại.
- Số liệu dinh dưỡng là ước tính, tính trên 100 g.

Model train trên dữ liệu này chỉ dùng cho học tập và nghiên cứu.
