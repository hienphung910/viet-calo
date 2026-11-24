# Image chạy web trên Railway (Railway tự build khi thấy file này ở gốc repo).
FROM python:3.11-slim

# OMP_NUM_THREADS: PyTorch mặc định tạo số luồng bằng số nhân của máy chủ, nhiều hơn phần CPU container được cấp
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2

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
RUN python manage.py collectstatic --noinput

# Railway đặt biến PORT. Mỗi lần khởi động: cập nhật bảng CSDL, nạp dữ liệu ban đầu + model, rồi chạy web.
# --trusted-proxy: Railway đứng trước làm proxy HTTPS, cần tin header X-Forwarded-Proto để Django biết đang là HTTPS.
# --max-request-body-size: 11 MB (ảnh tối đa 10 MB + phần form). Mặc định waitress nhận tới 1 GB mỗi request và
#   ghi tạm ra đĩa trước khi Django kịp kiểm tra, kể cả với người chưa đăng nhập.
CMD python manage.py migrate --noinput \
    && python manage.py prepare_deploy \
    && exec waitress-serve --listen=0.0.0.0:${PORT:-8000} --trusted-proxy='*' --trusted-proxy-headers=x-forwarded-proto --max-request-body-size=11534336 config.wsgi:application
