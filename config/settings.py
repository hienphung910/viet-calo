"""
Cấu hình Django cho dự án VietCalo.

Mọi giá trị thay đổi theo môi trường (DEBUG, SECRET_KEY, DATABASE_URL...) được đọc
từ file `.env` ở thư mục gốc. Xem `.env.example`.
  - MySQL (chính): DATABASE_URL=mysql://user:pass@localhost:3306/calories
  - SQLite (chạy nhanh/test, mặc định nếu không có .env): DATABASE_URL=sqlite:///db.sqlite3
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CONFIDENCE_THRESHOLD=(float, 0.6),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Các app của dự án (nằm trong thư mục apps/)
    "apps.accounts",
    "apps.foods",
    "apps.recognition",
    "apps.diary",
    "apps.feedback",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Phục vụ file tĩnh (CSS/JS của admin...) khi DEBUG=False, không cần nginx.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.media",  # {{ MEDIA_URL }} trong template
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- CSDL: đổi giữa MySQL và SQLite chỉ bằng biến DATABASE_URL ---
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}

if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3" and DATABASES["default"]["NAME"] != ":memory:":
    # sqlite:///db.sqlite3 -> luôn nằm ở thư mục dự án, dù chạy lệnh từ thư mục nào.
    DATABASES["default"]["NAME"] = str(BASE_DIR / DATABASES["default"]["NAME"])

if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"].setdefault("OPTIONS", {}).update(
        {
            # utf8mb4 để lưu đủ tiếng Việt có dấu (và emoji).
            "charset": "utf8mb4",
            # Strict mode: MySQL báo lỗi thay vì tự cắt/ép dữ liệu sai kiểu.
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    )
    # CSDL tạm mà Django tạo khi chạy test cũng dùng utf8mb4.
    DATABASES["default"]["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}

# --- Auth: dùng User tùy biến, đăng nhập bằng email ---
# Phải khai báo ngay từ migration đầu tiên, Django không cho đổi về sau.
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "diary:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # `manage.py collectstatic` gom file tĩnh về đây
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Nén gzip/brotli sẵn file tĩnh để tải nhanh hơn.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Ảnh upload lưu trên đĩa trong media/, CSDL chỉ lưu đường dẫn tương đối.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cấu hình nghiệp vụ ---
# Top-1 thấp hơn ngưỡng này thì hiện top-3 cho người dùng tự chọn.
CONFIDENCE_THRESHOLD = env("CONFIDENCE_THRESHOLD")
# Hệ số khẩu phần so với default_portion_g của món.
PORTION_MULTIPLIERS = {"small": 0.7, "medium": 1.0, "large": 1.3}
# File bảng dinh dưỡng dùng cho lệnh seed_foods.
NUTRITION_CSV = BASE_DIR / "data" / "nutrition.csv"

# --- Nhận diện ảnh ---
# Thiết bị chạy model trên web: "cpu" (mặc định, chạy được trên mọi máy), "cuda" hoặc "auto".
ML_DEVICE = env("ML_DEVICE", default="cpu")
# Bao lâu (giây) thì hỏi CSDL một lần xem model active có đổi không (hot-reload).
MODEL_CHECK_INTERVAL = env.float("MODEL_CHECK_INTERVAL", default=10)
# Giới hạn ảnh upload.
MAX_UPLOAD_MB = 10
UPLOAD_MAX_SIDE = 1280  # ảnh lưu lại được thu nhỏ để tiết kiệm dung lượng
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
# Nơi export_feedback chép ảnh phản hồi tới (cùng thư mục ảnh gốc để train lại).
FEEDBACK_EXPORT_DIR = BASE_DIR / "data" / "raw"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"apps": {"handlers": ["console"], "level": "INFO"}},
}
