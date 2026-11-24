#!/bin/sh
# Lệnh khởi động của container (Dockerfile gọi file này).
# Việc cần làm: cập nhật bảng CSDL, nạp dữ liệu ban đầu + model, rồi chạy web bằng user thường "app".
set -e

APP_USER=app

# --trusted-proxy: Railway đứng trước làm proxy HTTPS, cần tin header X-Forwarded-Proto để Django biết đang là HTTPS.
# --max-request-body-size: 11 MB (ảnh tối đa 10 MB + phần form). Mặc định waitress nhận tới 1 GB mỗi request và
#   ghi tạm ra đĩa trước khi Django kịp kiểm tra, kể cả với người chưa đăng nhập.
RUN_APP='python manage.py migrate --noinput && python manage.py prepare_deploy && exec waitress-serve --listen=0.0.0.0:${PORT:-8000} --trusted-proxy="*" --trusted-proxy-headers=x-forwarded-proto --max-request-body-size=11534336 config.wsgi:application'

# setpriv (có sẵn trong Debian) đổi sang user khác rồi chạy lệnh, không cần cài thêm sudo/gosu
AS_APP="setpriv --reuid=$APP_USER --regid=$APP_USER --init-groups"

if [ "$(id -u)" = "0" ]; then
    # Web chỉ cần ghi vào 2 thư mục này. Volume của Railway luôn được gắn bằng quyền root,
    # nên phải trao lại cho user "app" mỗi lần khởi động.
    mkdir -p /app/media /app/models
    chown -R "$APP_USER:$APP_USER" /app/media /app/models || true

    # Chỉ hạ quyền khi chắc chắn user "app" chạy được và ghi được; nếu không thì chạy như cũ (root)
    # để web không sập chỉ vì bước này.
    if $AS_APP sh -c 'test -w /app/media && test -w /app/models' 2>/dev/null; then
        export HOME="/home/$APP_USER"
        exec $AS_APP sh -c "$RUN_APP"
    fi
    echo "CANH BAO: khong ha duoc quyen xuong user $APP_USER, web dang chay bang root." >&2
fi

exec sh -c "$RUN_APP"
