# Image chạy web trên Railway (Railway tự build khi thấy file này ở gốc repo).
FROM python:3.11-slim

# OMP_NUM_THREADS: PyTorch mặc định tạo số luồng bằng số nhân của máy chủ, nhiều hơn phần CPU container được cấp
# UPLOAD_CLEANUP_HOURS: cứ 6 giờ web tự xoá ảnh tải lên không còn được CSDL tham chiếu
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2 \
    UPLOAD_CLEANUP_HOURS=6

# mysqlclient không có wheel cho Linux nên phải build từ mã nguồn
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch bản chỉ chạy CPU (nhẹ hơn nhiều so với bản mặc định trên Linux có kèm CUDA)
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# sed: bỏ ký tự xuống dòng kiểu Windows nếu có, vì sh trên Linux không chạy được script có \r
RUN python manage.py collectstatic --noinput \
    && sed -i 's/\r$//' deploy/start.sh

# User thường để chạy web. Mã nguồn trong /app vẫn thuộc root nên web không tự sửa được code của chính nó;
# deploy/start.sh chỉ trao cho user này quyền ghi vào media/ và models/.
RUN useradd --create-home --uid 1000 app

# Railway đặt biến PORT. Mỗi lần khởi động: cập nhật bảng CSDL, nạp dữ liệu ban đầu + model, rồi chạy web
# bằng user "app" (chi tiết trong deploy/start.sh).
CMD ["sh", "/app/deploy/start.sh"]
