import os
import socket
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv

host_names = ["RogStrix", "MacBook-Pro.local", "MacbookPro"]
DEBUG = True if socket.gethostname() in host_names else False

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
DAYS = 1


DOTENV_PATH = BASE_DIR / ".env"
if DOTENV_PATH.exists():
    load_dotenv(DOTENV_PATH)

SECRET_KEY = os.getenv("SECRET_KEY")
SECRET_API = os.getenv("SECRET_API")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
MAIN_IP = os.getenv("MAIN_IP")
API_KEY = os.getenv("API_KEY")

LOGIN_URL = "/login_view/"
LOGOUT_URL = "/logout/"

#! SET TO DOMAIN
ALLOWED_HOSTS = ["*"]

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 МБ
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 МБ

DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000

# Application definition
INSTALLED_APPS = [
    "grappelli",
    # Default
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Installed apps
    "drf_yasg",
    "monitoring_app",
    "rest_framework",
    "corsheaders",
    "rest_framework_simplejwt",
]

#! On Release set False
CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
]

MIDDLEWARE = [
    "monitoring_app.middleware.CustomCorsMiddleware",
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

WSGI_APPLICATION = "django_settings.wsgi.application"

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
            "LOCATION": f"""redis://{os.getenv("REDIS_HOST")}:{os.getenv("REDIS_PORT")}""",
        }
    }


if DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("db_name"),
            "USER": os.getenv("db_user"),
            "PASSWORD": os.getenv("db_password"),
            "HOST": os.getenv("db_host"),
            "PORT": os.getenv("db_port"),
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        + "UserAttributeSimilarityValidator",
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


LANGUAGE_CODE = "ru"

TIME_ZONE = "Asia/Almaty"

USE_I18N = True

USE_TZ = True


STATIC_URL = "assets/" if DEBUG else "/static/"
STATIC_ROOT = Path(BASE_DIR, "staticroot")

# массив с папками откуда джанго "собирает" статику
STATICFILES_DIRS = [
    Path(BASE_DIR / "static"),
    Path(FRONTEND_DIR / "dist/assets"),
]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "static/media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# * JWT LOGIC GOES HERE
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": (
        # 'rest_framework.permissions.IsAdmin',
        "rest_framework.permissions.IsAuthenticated",
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # 'rest_framework.authentication.BasicAuthentication',
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_HEADER_TYPES": ("Bearer",),  # {headers: {Authorization: `Bearer ${access}`}}
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication."
    + "default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=10),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(hours=1),
}
# DRF-YASG configuration
SWAGGER_SETTINGS = {
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

# Optional settings for ReDoc
REDOC_SETTINGS = {
    "LAZY_RENDERING": True,
}


LOG_DIR = os.path.join(BASE_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO" if DEBUG else "WARNING",
            "class": "logging.FileHandler",
            "filename": os.path.join(
                LOG_DIR, f'log-{datetime.now().strftime("%Y-%m-%d_%H")}.log'
            ),
            "formatter": "verbose",
        },
    },
    "loggers": {
        "": {  
            "handlers": ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "django": {
            "handlers": ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
    },
}
