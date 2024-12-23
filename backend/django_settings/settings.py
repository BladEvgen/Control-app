import os
import socket
from pathlib import Path
from dotenv import load_dotenv
from celery.schedules import crontab
from datetime import timedelta, datetime

# Host names and DEBUG setting
HOST_NAMES = ["RogStrix", "MacBook-Pro.local", "MacbookPro"]
DEBUG = socket.gethostname() in HOST_NAMES

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# Custom settings
DAYS = 1
FACE_RECOGNITION_THRESHOLD = 0.76
RATE_PERIOD = 600
RATE_LIMIT = 40

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# Secret keys and API configurations
SECRET_KEY = os.getenv("SECRET_KEY")
SECRET_API = os.getenv("SECRET_API")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
MAIN_IP = os.getenv("MAIN_IP")
DB_TYPE = os.getenv("DB_TYPE", "sqlite3").lower()


# Email configurations
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")

# Authentication URLs
LOGIN_URL = "/login_view/"
LOGOUT_URL = "/logout/"


# Function to get the local IP address
def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip_address = s.getsockname()[0]
    except Exception as e:
        print(f"Error getting local IP: {e}")
        ip_address = "127.0.0.1"
    return ip_address


LOCAL_IP = get_local_ip()


# Function to get the external IP address
def get_external_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            external_ip = s.getsockname()[0]
    except Exception as e:
        print(f"Error getting external IP: {e}")
        external_ip = "127.0.0.1"
    return external_ip


EXTERNAL_IP = get_external_ip()

# Allowed hosts and CSRF trusted origins
ALLOWED_HOSTS = ["*"] + (
    [LOCAL_IP, EXTERNAL_IP] if DEBUG else ["control.krmu.edu.kz", "dot.medkrmu.edu.kz"]
)

CSRF_TRUSTED_ORIGINS = (
    [
        f"http://{EXTERNAL_IP}:8000",
        f"http://{EXTERNAL_IP}:5173",
        f"http://{EXTERNAL_IP}:3000",
    ]
    if DEBUG
    else [
        "https://control.krmu.edu.kz",
        "https://dot.medkrmu.kz",
    ]
)

ALLOWED_IPS = [LOCAL_IP, EXTERNAL_IP]

# Data upload settings
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000

# Application definition
INSTALLED_APPS = [
    "daphne",
    "channels",
    "grappelli",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "drf_yasg",
    "monitoring_app",
    "rest_framework",
    "corsheaders",
    "rest_framework_simplejwt",
    "django_extensions",
    "django_admin_geomap",
    "rest_framework.authtoken",
]

# Channel layers configuration
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": (
            "channels.layers.InMemoryChannelLayer"
            if DEBUG
            else "channels_redis.core.RedisChannelLayer"
        ),
        "CONFIG": {} if DEBUG else {"hosts": [("127.0.0.1", 6379)]},
    },
}

# CORS configurations
CORS_ALLOW_ALL_ORIGINS = DEBUG

CORS_ALLOWED_ORIGINS = (
    [
        f"http://{EXTERNAL_IP}:8000",
        f"http://{EXTERNAL_IP}:3000",
        f"http://{EXTERNAL_IP}:5173",
    ]
    if DEBUG
    else [
        "https://dot.medkrmu.kz",
        "https://control.krmu.edu.kz",
    ]
)
# Settings for Custom Middleware
SECURITY_MIDDLEWARE_EXEMPT_PATHS = [
    "/app/",
    "/app/login",
    "/app/logout",
    "/admin/",
    "/swagger/",
    "/redoc/",
]

if DEBUG:
    SECURITY_MIDDLEWARE_EXEMPT_PATHS += [
        "/api/docs/",
        "/api/schema/",
    ]

# Middleware configurations
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "django_settings.urls"

# Template configurations
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [FRONTEND_DIR / "dist", BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "monitoring_app.context_processors.current_year",
            ],
        },
    },
]

# WSGI_APPLICATION = "django_settings.wsgi.application"
ASGI_APPLICATION = "django_settings.asgi.application"

# Cache configurations
if DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://127.0.0.1:6379",
        }
    }
# Database configurations

DATABASES = {"default": {}}


if DEBUG:
    # If debug using SQLite3
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
else:
    # If production using MySQL or PostgreSQL
    if DB_TYPE == "mysql":
        DATABASES["default"] = {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "3306"),
        }
    elif DB_TYPE == "postgresql":
        DATABASES["default"] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    else:
        raise ValueError(f"Unsupported database type: {DB_TYPE}")

# Password validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Almaty"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "assets/" if DEBUG else "/static/"
STATIC_ROOT = BASE_DIR / "staticroot"

STATICFILES_DIRS = [
    BASE_DIR / "static",
    FRONTEND_DIR / "dist/assets",
]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "static/media"

# Attendance and augment paths
ATTENDANCE_URL = "/attendance_media/"
ATTENDANCE_ROOT = MEDIA_ROOT / "control_image" if DEBUG else "/mnt/disk/control_image/"

AUGMENT_URL = "/augment_media/"
AUGMENT_ROOT = (
    MEDIA_ROOT / "user_images" / "{staff_pin}" / "augmented_images"
    if DEBUG
    else "/mnt/disk/augment_images/augmented_images/{staff_pin}"
)

GENERAL_MODELS_ROOT = BASE_DIR / "models" if DEBUG else "/mnt/disk/model_ml"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST framework configurations
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

# JWT configurations
SIMPLE_JWT = {
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),  # {headers: {Authorization: `Bearer ${access}`}}
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "JTI_CLAIM": "jti",
}

# Token lifetimes based on DEBUG
SIMPLE_JWT.update(
    {
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
        "REFRESH_TOKEN_LIFETIME": (
            timedelta(minutes=30) if DEBUG else timedelta(hours=1)
        ),
        "SLIDING_TOKEN_LIFETIME": timedelta(minutes=10),
        "SLIDING_TOKEN_REFRESH_LIFETIME": (
            timedelta(minutes=30) if DEBUG else timedelta(hours=1)
        ),
    }
)

# Swagger settings
SWAGGER_SETTINGS = {
    "LOGIN_URL": "login_view",
    "LOGOUT_URL": "logout",
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
        }
    },
    "USE_SESSION_AUTH": True,
    "DEFAULT_AUTO_SCHEMA_CLASS": "drf_yasg.inspectors.SwaggerAutoSchema",
}

# ReDoc settings
REDOC_SETTINGS = {
    "LAZY_RENDERING": True,
}

# Celery configurations
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

CELERY_BEAT_SCHEDULE = (
    {}
    if DEBUG
    else {
        "get-attendance-every-day-5am": {
            "task": "monitoring_app.tasks.get_all_attendance_task",
            "schedule": crontab(hour=5, minute=0),
        },
        "update-lesson-attendance-last-out-every-10-minutes": {
            "task": "monitoring_app.tasks.update_lesson_attendance_last_out",
            "schedule": crontab(minute="*/5"),
        },
        "augment-images-every-day": {
            "task": "monitoring_app.tasks.augment_user_images",
            "schedule": crontab(day_of_month="*/3", hour=1, minute=0),
        },
    }
)

# Logging configurations
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


# Custom function to generate log filenames
def get_log_filename(log_name):
    return LOG_DIR / f'{log_name}_{datetime.now().strftime("%Y-%m-%d_%H")}.log'


# Function to remove old logs
def clean_old_logs(log_directory, days_to_keep=7):
    now = datetime.now()
    for filename in os.listdir(log_directory):
        if filename.endswith(".log"):
            file_path = log_directory / filename
            file_modified_time = datetime.fromtimestamp(file_path.stat().st_mtime)
            if (now - file_modified_time).days > days_to_keep:
                file_path.unlink()


# Clean old logs
clean_old_logs(LOG_DIR, days_to_keep=7)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{levelname} {asctime} {name} {module} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO" if DEBUG else "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": get_log_filename("log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 24,  # Keep logs for 24 hours
            "encoding": "utf-8",
            "formatter": "standard",
        },
    },
    "loggers": {
        "": {
            "handlers": ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": True,
        },
        "django": {
            "handlers": ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": True,
        },
    },
}
