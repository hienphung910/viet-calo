from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Railway tự đặt biến RAILWAY_PUBLIC_DOMAIN (dạng ten-app.up.railway.app) và đứng trước app làm proxy HTTPS
RAILWAY_PUBLIC_DOMAIN = env("RAILWAY_PUBLIC_DOMAIN", default="")
if RAILWAY_PUBLIC_DOMAIN:
    # khoá mặc định và khoá mẫu trong .env.example đều nằm công khai trên git, ai cũng giả mạo được phiên đăng nhập
    if SECRET_KEY in ("dev-insecure-key-change-me", "thay-bang-chuoi-ngau-nhien-dai"):
        raise ImproperlyConfigured("Chưa đặt biến SECRET_KEY (chuỗi ngẫu nhiên riêng) trên Railway.")
    ALLOWED_HOSTS += [RAILWAY_PUBLIC_DOMAIN, "healthcheck.railway.app"]
    CSRF_TRUSTED_ORIGINS = [f"https://{RAILWAY_PUBLIC_DOMAIN}"]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # trình duyệt nhớ trong 30 ngày là trang này chỉ dùng HTTPS, không thử HTTP thường nữa
    SECURE_HSTS_SECONDS = 30 * 24 * 3600

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "app.apps.VietCaloConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "app.middleware.WeakPasswordMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "app" / "views"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.media",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# đổi giữa MySQL và SQLite bằng biến DATABASE_URL trong .env
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}

if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3" and DATABASES["default"]["NAME"] != ":memory:":
    DATABASES["default"]["NAME"] = str(BASE_DIR / DATABASES["default"]["NAME"])

if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    db_options = DATABASES["default"].setdefault("OPTIONS", {})
    # MySQL trên cloud (Aiven...) bắt buộc SSL và đưa URI dạng ...?ssl-mode=REQUIRED,
    # còn driver mysqlclient nhận tham số tên ssl_mode
    if "ssl-mode" in db_options:
        db_options["ssl_mode"] = db_options.pop("ssl-mode")
    db_options.update(
        {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    )
    DATABASES["default"]["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}
    # Giữ kết nối giữa các request. Mặc định Django mở kết nối mới cho từng request; với MySQL ở xa và có SSL
    # thì riêng việc mở kết nối đã mất nhiều lượt đi-về, làm mọi trang đều chậm.
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=300)
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "app.User"
AUTHENTICATION_BACKENDS = ["app.auth_backend.GuardedModelBackend"]

# Số lần đăng nhập sai tối đa trong LOGIN_LOCK_SECONDS trước khi bị khoá tạm (xem app/services/login_guard.py)
LOGIN_LIMITS = {"ip_email": 5, "ip": 30, "email": 20}
LOGIN_LOCK_SECONDS = 15 * 60
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "diary:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# áp dụng khi đăng ký và khi đổi mật khẩu trong trang quản trị: tối thiểu 8 ký tự, không nằm trong danh sách
# mật khẩu phổ biến, không toàn chữ số, không quá giống email
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PORTION_MULTIPLIERS = {"small": 0.7, "medium": 1.0, "large": 1.3}
NUTRITION_CSV = BASE_DIR / "data" / "nutrition.csv"

MODELS_DIR = BASE_DIR / "models"
# link tải file .zip chứa thư mục model, dùng khi deploy vì model không nằm trong git (xem lệnh prepare_deploy)
MODEL_URL = env("MODEL_URL", default="")
ML_DEVICE = env("ML_DEVICE", default="cpu")
MODEL_CHECK_INTERVAL = env.float("MODEL_CHECK_INTERVAL", default=10)
# Cứ mỗi N giờ web tự xoá ảnh trong media/ không còn được CSDL tham chiếu (lệnh cleanup_uploads). 0 = tắt.
UPLOAD_CLEANUP_HOURS = env.float("UPLOAD_CLEANUP_HOURS", default=0)
MAX_UPLOAD_MB = 10
# Ảnh nén rất nhỏ vẫn có thể bung ra hàng trăm MB trong RAM khi giải mã (vd. PNG một màu 170 megapixel),
# đủ làm sập server. 30 megapixel vẫn nhận được ảnh chụp 24 MP của điện thoại.
MAX_UPLOAD_PIXELS = 30_000_000
UPLOAD_MAX_SIDE = 1280
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
FEEDBACK_EXPORT_DIR = BASE_DIR / "data" / "raw"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    # tên logger phải khớp tên package ("app"), nếu không các dòng log INFO của web không bao giờ được in ra
    "loggers": {"app": {"handlers": ["console"], "level": "INFO"}},
}
