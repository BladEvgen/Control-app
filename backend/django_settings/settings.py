import json
import os
import socket
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from django.templatetags.static import static
from dotenv import load_dotenv
from kombu import Queue

# Окружение
HOST_NAMES = ["RogStrix", "MacBook-Pro.local", "MacbookPro", "Rumishka"]
DEBUG = socket.gethostname() in HOST_NAMES
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

# Пути проекта
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

load_dotenv(BASE_DIR / ".env")


def _csv_env_frozenset(name: str, default: str) -> frozenset[str]:
    """Parse comma-separated env var into a normalized frozenset."""
    return frozenset(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _json_env_dict(name: str, default: str = "{}") -> dict:
    raw = os.getenv(name, default)
    if raw is None or not str(raw).strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _jwt_lifetime_minutes(env_name: str, debug_minutes: int, prod_minutes: int) -> int:
    """JWT lifetime in minutes; env override for long-lived browser sessions (security tradeoff)."""
    raw = os.getenv(env_name)
    if raw is None or not str(raw).strip():
        return debug_minutes if DEBUG else prod_minutes
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return debug_minutes if DEBUG else prod_minutes


# Посещаемость
DAYS = 1
# Серийные номера устройств выхода из здания (devSn из API СКУД)
ATTENDANCE_EXIT_DEVICE_SNS = _csv_env_frozenset(
    "ATTENDANCE_EXIT_DEVICE_SNS",
    "CORL223060005,QJT3244400440,CN3R230260001,CN3R230260016,CN3R230260009",
)
ATTENDANCE_AMBIGUOUS_EXIT_DEVICE_SNS = _csv_env_frozenset(
    "ATTENDANCE_AMBIGUOUS_EXIT_DEVICE_SNS",
    "QJT3244400440",
)
ATTENDANCE_REENTRY_DEVICE_SNS = _csv_env_frozenset(
    "ATTENDANCE_REENTRY_DEVICE_SNS",
    "COVS222560013,CN3R230260010,CN3R230260002,CN3R230260003",
)
# Турникеты (Абылайхана, Торекулова, Карасай): в режиме «только турникеты»
# (AttendanceSettings.turnstile_only) отчётные first_in/last_out/время берутся только с них.
ATTENDANCE_TURNSTILE_DEVICE_SNS = _csv_env_frozenset(
    "ATTENDANCE_TURNSTILE_DEVICE_SNS",
    "CN3R230260001,CN3R230260002,CN3R230260003,CN3R230260005,CN3R230260009,"
    "CN3R230260010,CN3R230260015,CN3R230260016,CORL223060005,CORL223060016",
)
# Повторный проход через то же устройство в пределах N секунд — двойное прикладывание
# карты, а не новое движение (иначе 07:05 + 07:06 на турникете = «вошёл и вышел»).
ATTENDANCE_REPEAT_TAP_SECONDS = _int_env("ATTENDANCE_REPEAT_TAP_SECONDS", 120)
ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES = int(
    os.getenv("ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES", "45")
)
ATTENDANCE_WRITE_HMAC_SECRET = os.getenv("ATTENDANCE_WRITE_HMAC_SECRET", "").strip()
ATTENDANCE_WRITE_HMAC_TTL_SECONDS = _int_env("ATTENDANCE_WRITE_HMAC_TTL_SECONDS", 300)
ATTENDANCE_API_TERMINAL_POOLS = _json_env_dict("ATTENDANCE_API_TERMINAL_POOLS")
FACE_VERIFY_THRESHOLD = float(os.getenv("FACE_VERIFY_THRESHOLD", "0.50"))
FACE_RECOGNITION_THRESHOLD = float(os.getenv("FACE_RECOGNITION_THRESHOLD", "0.50"))
FACE_RECOGNITION_MIN_NEIGHBOR_GAP = float(os.getenv("FACE_RECOGNITION_MIN_NEIGHBOR_GAP", "0.05"))
FACE_RUNTIME_INCLUDE_FACE_SAMPLES = os.getenv(
    "FACE_RUNTIME_INCLUDE_FACE_SAMPLES", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_RUNTIME_ADD_CENTROID_PROTOTYPES = os.getenv(
    "FACE_RUNTIME_ADD_CENTROID_PROTOTYPES", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_RUNTIME_CENTROID_MIN_ROWS = int(os.getenv("FACE_RUNTIME_CENTROID_MIN_ROWS", "2"))
FACE_TRAINING_INCLUDE_LESSON_ATTENDANCE = os.getenv(
    "FACE_TRAINING_INCLUDE_LESSON_ATTENDANCE", "1"
).strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
FACE_TRAINING_LESSON_ATTENDANCE_MAX = int(os.getenv("FACE_TRAINING_LESSON_ATTENDANCE_MAX", "80"))
FACE_GALLERY_ENROLLMENT_PAD_VALIDATE = os.getenv(
    "FACE_GALLERY_ENROLLMENT_PAD_VALIDATE", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_GALLERY_ENROLLMENT_PAD_MAX_RISK = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_PAD_MAX_RISK", "0.42")
)
FACE_GALLERY_ENROLLMENT_DET_SCORE_MIN = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_DET_SCORE_MIN", "0.45")
)
FACE_GALLERY_ENROLLMENT_FACE_AREA_RATIO_MIN = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_FACE_AREA_RATIO_MIN", "0.012")
)
FACE_GALLERY_ENROLLMENT_BLUR_MIN = float(os.getenv("FACE_GALLERY_ENROLLMENT_BLUR_MIN", "18.0"))
FACE_GALLERY_ENROLLMENT_BRIGHTNESS_MIN = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_BRIGHTNESS_MIN", "30.0")
)
FACE_GALLERY_ENROLLMENT_BRIGHTNESS_MAX = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_BRIGHTNESS_MAX", "232.0")
)
FACE_GALLERY_ENROLLMENT_MAX_ABS_YAW = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_MAX_ABS_YAW", "38.0")
)
FACE_GALLERY_ENROLLMENT_MAX_ABS_PITCH = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_MAX_ABS_PITCH", "32.0")
)
FACE_GALLERY_ATTENDANCE_MIN_ANCHOR_COS = float(
    os.getenv("FACE_GALLERY_ATTENDANCE_MIN_ANCHOR_COS", "0.54")
)
FACE_GALLERY_ATTENDANCE_MIN_NO_ANCHOR_COUNT = int(
    os.getenv("FACE_GALLERY_ATTENDANCE_MIN_NO_ANCHOR_COUNT", "3")
)
FACE_GALLERY_ENROLLMENT_MIN_CENTROID_COS = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_MIN_CENTROID_COS", "0.46")
)
FACE_GALLERY_REAL_DEDUPE_MAX_COS = float(os.getenv("FACE_GALLERY_REAL_DEDUPE_MAX_COS", "0.9975"))
FACE_GALLERY_REAL_MAX_PROTOTYPES = int(os.getenv("FACE_GALLERY_REAL_MAX_PROTOTYPES", "48"))
FACE_GALLERY_REAL_META_ACCEPTED_DETAIL_LIMIT = int(
    os.getenv("FACE_GALLERY_REAL_META_ACCEPTED_DETAIL_LIMIT", "48")
)
FACE_GALLERY_REAL_META_REJECTED_DETAIL_LIMIT = int(
    os.getenv("FACE_GALLERY_REAL_META_REJECTED_DETAIL_LIMIT", "24")
)

FACE_VERIFY_PROBE_DET_SCORE_MIN = float(os.getenv("FACE_VERIFY_PROBE_DET_SCORE_MIN", "0.35"))
FACE_VERIFY_PROBE_FACE_AREA_RATIO_MIN = float(
    os.getenv("FACE_VERIFY_PROBE_FACE_AREA_RATIO_MIN", "0.008")
)
FACE_VERIFY_PROBE_MAX_ABS_YAW = float(os.getenv("FACE_VERIFY_PROBE_MAX_ABS_YAW", "40.0"))
FACE_VERIFY_PROBE_MAX_ABS_PITCH = float(os.getenv("FACE_VERIFY_PROBE_MAX_ABS_PITCH", "35.0"))
FACE_VERIFY_IMPOSTOR_GAP_ENABLE = os.getenv(
    "FACE_VERIFY_IMPOSTOR_GAP_ENABLE", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_VERIFY_IMPOSTOR_GAP_MIN = float(os.getenv("FACE_VERIFY_IMPOSTOR_GAP_MIN", "0.05"))
# Эталонные фото: ограничение количества и отбраковка дубликатов.
FACE_BOOTSTRAP_MAX_ACTIVE_SAMPLES = int(os.getenv("FACE_BOOTSTRAP_MAX_ACTIVE_SAMPLES", "5"))
FACE_SAMPLE_DEDUPE_MAX_COS = float(os.getenv("FACE_SAMPLE_DEDUPE_MAX_COS", "0.992"))

# Загружаемые фото нормализуются в JPEG без EXIF.
STAFF_UPLOAD_JPEG_QUALITY = int(os.getenv("STAFF_UPLOAD_JPEG_QUALITY", "92"))
STAFF_UPLOAD_MAX_MEGAPIXELS = int(os.getenv("STAFF_UPLOAD_MAX_MEGAPIXELS", "36"))
STAFF_AVATAR_UPLOAD_MAX_BYTES = int(
    os.getenv("STAFF_AVATAR_UPLOAD_MAX_BYTES", str(12 * 1024 * 1024))
)

FACE_PARSING_ENABLE = os.getenv("FACE_PARSING_ENABLE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
FACE_PARSING_AUTO_DOWNLOAD = os.getenv("FACE_PARSING_AUTO_DOWNLOAD", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
_face_parsing_path = os.getenv("FACE_PARSING_MODEL_PATH", "").strip()
FACE_PARSING_MODEL_PATH = (
    str(Path(_face_parsing_path).expanduser().resolve()) if _face_parsing_path else None
)
FACE_PARSING_DOWNLOAD_URL = os.getenv(
    "FACE_PARSING_DOWNLOAD_URL",
    "https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx",
)
FACE_PARSING_GLASSES_FRAC_MIN = _float_env("FACE_PARSING_GLASSES_FRAC_MIN", 0.00035)
FACE_PARSING_USE_FOR_API = os.getenv("FACE_PARSING_USE_FOR_API", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
RATE_PERIOD = 600
RATE_LIMIT = 40
NO_ALBUMENTATIONS_UPDATE: int = int(os.getenv("NO_ALBUMENTATIONS_UPDATE", "1"))
LESSON_ATTENDANCE_AUTO_CLOSE_DEFAULT_MINUTES = _int_env(
    "LESSON_ATTENDANCE_AUTO_CLOSE_DEFAULT_MINUTES",
    120,
)
LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_START_HOUR = _int_env(
    "LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_START_HOUR",
    18,
)
LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_MINUTES = _int_env(
    "LESSON_ATTENDANCE_AUTO_CLOSE_EVENING_MINUTES",
    90,
)
LESSON_ATTENDANCE_AUTO_CLOSE_LATE_START_HOUR = _int_env(
    "LESSON_ATTENDANCE_AUTO_CLOSE_LATE_START_HOUR",
    20,
)
LESSON_ATTENDANCE_AUTO_CLOSE_LATE_MINUTES = _int_env(
    "LESSON_ATTENDANCE_AUTO_CLOSE_LATE_MINUTES",
    60,
)

# Ключи и внешние API
SECRET_KEY = os.getenv("SECRET_KEY")
SECRET_API = os.getenv("SECRET_API")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
# Озвучка Face Lab через Edge TTS
FACE_LAB_EDGE_TTS_VOICE_RU = os.getenv("FACE_LAB_EDGE_TTS_VOICE_RU", "ru-RU-SvetlanaNeural").strip()
FACE_LAB_EDGE_TTS_VOICE_KK = os.getenv("FACE_LAB_EDGE_TTS_VOICE_KK", "kk-KZ-AigulNeural").strip()
FACE_LAB_EDGE_TTS_VOICE_EN = os.getenv("FACE_LAB_EDGE_TTS_VOICE_EN", "en-US-JennyNeural").strip()
MAIN_IP = os.getenv("MAIN_IP")
DB_TYPE = os.getenv("DB_TYPE", "sqlite3").lower()


# Почта
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "0"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS") == "True"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")

# Авторизация
LOGIN_URL = "/admin/login/"
LOGOUT_URL = "/admin/logout/"


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

# Хосты и CSRF
ALLOWED_HOSTS = ["*"] + (
    [LOCAL_IP, EXTERNAL_IP]
    if DEBUG
    else ["control.krmu.edu.kz", "dot.medkrmu.edu.kz", "commander.medkrmu.kz"]
)

CSRF_TRUSTED_ORIGINS = (
    [
        f"http://{EXTERNAL_IP}:8000",
        f"http://{EXTERNAL_IP}:5173",
        f"http://{EXTERNAL_IP}:3000",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    if DEBUG
    else [
        "https://control.krmu.edu.kz",
        "https://dot.medkrmu.kz",
        "https://commander.medkrmu.kz",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
)

ALLOWED_IPS = [LOCAL_IP, EXTERNAL_IP]

# Загрузка файлов
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000


# Оформление админки
ADMIN_PALETTES = {
    "teal": (
        "98.4% .014 180.72",
        "95.3% .051 180.801",
        "91% .096 180.426",
        "85.5% .138 181.071",
        "77.7% .152 181.912",
        "70.4% .14 182.503",
        "60% .118 184.704",
        "51.1% .096 186.391",
        "43.7% .078 188.216",
        "38.6% .063 188.416",
        "27.7% .046 192.524",
    ),
    "sky": (
        "97.7% .013 236.62",
        "95.1% .026 236.824",
        "90.1% .058 230.902",
        "82.8% .111 230.318",
        "74.6% .16 232.661",
        "68.5% .169 237.323",
        "58.8% .158 241.966",
        "50% .134 242.749",
        "44.3% .11 240.79",
        "39.1% .09 240.876",
        "29.3% .066 243.157",
    ),
    "emerald": (
        "97.9% .021 166.113",
        "95% .052 163.051",
        "90.5% .093 164.15",
        "84.5% .143 164.978",
        "76.5% .177 163.223",
        "69.6% .17 162.48",
        "59.6% .145 163.225",
        "50.8% .118 165.612",
        "43.2% .095 166.913",
        "37.8% .077 168.94",
        "26.2% .051 172.552",
    ),
    "cyan": (
        "98.4% 0.019 200.873",
        "95.6% 0.045 203.388",
        "91.7% 0.08 205.041",
        "86.5% 0.127 207.078",
        "78.9% 0.154 211.53",
        "71.5% 0.143 215.221",
        "60.9% 0.126 221.723",
        "52% 0.105 223.128",
        "45% 0.085 224.283",
        "39.8% 0.07 227.392",
        "30.2% 0.056 229.695",
    ),
    "blue": (
        "97% 0.014 254.604",
        "93.2% 0.032 255.585",
        "88.2% 0.059 254.128",
        "80.9% 0.105 251.813",
        "70.7% 0.165 254.624",
        "62.3% 0.214 259.815",
        "54.6% 0.245 262.881",
        "48.8% 0.243 264.376",
        "42.4% 0.199 265.638",
        "37.9% 0.146 265.522",
        "28.2% 0.091 267.935",
    ),
    "indigo": (
        "96.2% 0.018 272.314",
        "93% 0.034 272.788",
        "87% 0.065 274.039",
        "78.5% 0.115 274.713",
        "67.3% 0.182 276.935",
        "58.5% 0.233 277.117",
        "51.1% 0.262 276.966",
        "45.7% 0.24 277.023",
        "39.8% 0.195 277.366",
        "35.9% 0.144 278.697",
        "25.7% 0.09 281.288",
    ),
    "violet": (
        "96.9% 0.016 293.756",
        "94.3% 0.029 294.588",
        "89.4% 0.057 293.283",
        "81.1% 0.111 293.571",
        "70.2% 0.183 293.541",
        "60.6% 0.25 292.717",
        "54.1% 0.281 293.009",
        "49.1% 0.27 292.581",
        "43.2% 0.232 292.759",
        "38% 0.189 293.745",
        "28.3% 0.141 291.089",
    ),
    "fuchsia": (
        "97.7% 0.017 320.058",
        "95.2% 0.037 318.852",
        "90.3% 0.076 319.62",
        "83.3% 0.145 321.434",
        "74% 0.238 322.16",
        "66.7% 0.295 322.15",
        "59.1% 0.293 322.896",
        "51.8% 0.253 323.949",
        "45.2% 0.211 324.591",
        "40.1% 0.17 325.612",
        "29.3% 0.136 325.661",
    ),
    "rose": (
        "96.9% 0.015 12.422",
        "94.1% 0.03 12.58",
        "89.2% 0.058 10.001",
        "81% 0.117 11.638",
        "71.2% 0.194 13.428",
        "64.5% 0.246 16.439",
        "58.6% 0.253 17.585",
        "51.4% 0.222 16.935",
        "45.5% 0.188 13.697",
        "41% 0.159 10.272",
        "27.1% 0.105 12.094",
    ),
    "orange": (
        "98% 0.016 73.684",
        "95.4% 0.038 75.164",
        "90.1% 0.076 70.697",
        "83.7% 0.128 66.29",
        "75% 0.183 55.934",
        "70.5% 0.213 47.604",
        "64.6% 0.222 41.116",
        "55.3% 0.195 38.402",
        "47% 0.157 37.304",
        "40.8% 0.123 38.172",
        "26.6% 0.079 36.259",
    ),
    "amber": (
        "98.7% 0.022 95.277",
        "96.2% 0.059 95.617",
        "92.4% 0.12 95.746",
        "87.9% 0.169 91.605",
        "82.8% 0.189 84.429",
        "76.9% 0.188 70.08",
        "66.6% 0.179 58.318",
        "55.5% 0.163 48.998",
        "47.3% 0.137 46.201",
        "41.4% 0.112 45.904",
        "27.9% 0.077 45.635",
    ),
    "lime": (
        "98.6% 0.031 120.757",
        "96.7% 0.067 122.328",
        "93.8% 0.127 124.321",
        "89.7% 0.196 126.665",
        "84.1% 0.238 128.85",
        "76.8% 0.233 130.85",
        "64.8% 0.2 131.684",
        "53.2% 0.157 131.589",
        "45.3% 0.124 130.933",
        "40.5% 0.101 131.063",
        "27.4% 0.072 132.109",
    ),
}
ADMIN_COLOR_SHADES = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")
ADMIN_PRIMARY_COLOR = os.getenv("ADMIN_PRIMARY_COLOR", "teal").strip().lower()
if ADMIN_PRIMARY_COLOR not in ADMIN_PALETTES:
    ADMIN_PRIMARY_COLOR = "teal"

UNFOLD = {
    "SITE_TITLE": "Мониторинг КРМУ",
    "SITE_HEADER": "Мониторинг КРМУ",
    "SITE_SUBHEADER": "Панель управления",
    "SITE_SYMBOL": "monitoring",
    "SITE_URL": "/app/",
    "DASHBOARD_CALLBACK": "django_settings.dashboard.dashboard_callback",
    "STYLES": [lambda request: static("admin/css/custom_admin.css")],
    "COLORS": {"primary": "django_settings.admin_theme.primary_colors"},
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": "django_settings.dashboard.sidebar_navigation",
    },
}


# Приложения
INSTALLED_APPS = [
    "daphne",
    "channels",
    "unfold",
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
    "rest_framework_simplejwt.token_blacklist",
    "django_extensions",
    "django_admin_geomap",
    "rest_framework.authtoken",
    "django_celery_beat",
    "django_celery_results",
]

# WebSocket и Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": (
            "channels.layers.InMemoryChannelLayer"
            if DEBUG or TESTING
            else "channels_redis.core.RedisChannelLayer"
        ),
        "CONFIG": (
            {}
            if DEBUG or TESTING
            else {
                "hosts": [
                    (
                        os.getenv("REDIS_HOST", "127.0.0.1"),
                        int(os.getenv("REDIS_PORT", "6379")),
                    )
                ]
            }
        ),
    },
}

# CORS
CORS_ALLOW_ALL_ORIGINS = DEBUG

CORS_ALLOWED_ORIGINS = (
    [
        f"http://{EXTERNAL_IP}:8000",
        f"http://{EXTERNAL_IP}:3000",
        f"http://{EXTERNAL_IP}:5173",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    if DEBUG
    else [
        "https://dot.medkrmu.kz",
        "https://control.krmu.edu.kz",
        "https://commander.medkrmu.kz",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
)

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-api-key",
    "x-api-token",
    "x-attendance-timestamp",
    "x-attendance-nonce",
    "x-attendance-signature",
]

CORS_EXPOSE_HEADERS = [
    "x-tts-text",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
# Исключения для middleware
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

# Middleware
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "monitoring_app.middleware.StaffActivityMiddleware",
    "monitoring_app.face_lab_log_middleware.FaceLabRequestLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "django_settings.urls"

# Шаблоны
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


ASGI_APPLICATION = "django_settings.asgi.application"

# Кеш
if DEBUG or TESTING:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": f"redis://{os.getenv('REDIS_HOST', '127.0.0.1')}:{os.getenv('REDIS_PORT', '6379')}",
        }
    }
# База данных

DATABASES = {"default": {}}


if DEBUG or TESTING:
    # Debug и тесты SQLite
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
else:
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
    elif DB_TYPE == "sqlite3":
        DATABASES["default"] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    else:
        raise ValueError(f"Unsupported database type: {DB_TYPE}")

# Валидация паролей
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

# Язык и часовой пояс
LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Almaty"
USE_I18N = True
USE_TZ = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Статика
STATIC_URL = "assets/" if DEBUG else "/static/"
STATIC_ROOT = BASE_DIR / "staticroot"

STATICFILES_DIRS = [
    BASE_DIR / "static",
    FRONTEND_DIR / "dist/assets",
    ("mediapipe", FRONTEND_DIR / "dist/mediapipe"),
    ("mediapipe-models", FRONTEND_DIR / "dist/mediapipe-models"),
]

# Медиафайлы
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

BACKUP_DB_DIR = BASE_DIR.parent / "DB"

# Файлы посещаемости
ATTENDANCE_URL = "/attendance_media/"
_attendance_root_env = os.getenv("ATTENDANCE_ROOT")
ATTENDANCE_ROOT = (
    Path(_attendance_root_env).expanduser().resolve()
    if _attendance_root_env
    else (MEDIA_ROOT / "control_image")
)

_general_models_env = os.getenv("GENERAL_MODELS_ROOT")
GENERAL_MODELS_ROOT = (
    Path(_general_models_env).expanduser().resolve()
    if _general_models_env
    else (BASE_DIR / "models")
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "monitoring_app.authentication.SessionAuthenticationAllowTokenOrApiKey",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_RATES": {"staff_login": "10/min", "staff_login_pin": "5/min"},
}

STAFF_JWT_ACCESS_MINUTES = int(os.getenv("STAFF_JWT_ACCESS_MINUTES", "15"))
STAFF_JWT_REFRESH_MINUTES = int(os.getenv("STAFF_JWT_REFRESH_MINUTES", "120"))
STAFF_JWT_SESSION_MAX_HOURS = int(os.getenv("STAFF_JWT_SESSION_MAX_HOURS", "10"))
STAFF_LOGIN_REPLAY_COSINE = float(os.getenv("STAFF_LOGIN_REPLAY_COSINE", "0.97"))

# JWT
SIMPLE_JWT = {
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
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

_JWT_ACCESS_MINUTES = _jwt_lifetime_minutes("JWT_ACCESS_LIFETIME_MINUTES", 10, 30)
_JWT_REFRESH_MINUTES = _jwt_lifetime_minutes("JWT_REFRESH_LIFETIME_MINUTES", 30, 120)

JWT_SESSION_MAX_HOURS = _jwt_lifetime_minutes("JWT_SESSION_MAX_HOURS", 24, 12)

SIMPLE_JWT.update(
    {
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=_JWT_ACCESS_MINUTES),
        "REFRESH_TOKEN_LIFETIME": timedelta(minutes=_JWT_REFRESH_MINUTES),
        "SLIDING_TOKEN_LIFETIME": timedelta(minutes=_JWT_ACCESS_MINUTES),
        "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(minutes=_JWT_REFRESH_MINUTES),
    }
)

# Swagger
SWAGGER_SETTINGS = {
    "LOGIN_URL": "admin:login",
    "LOGOUT_URL": "admin:logout",
    "VALIDATOR_URL": None,
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT токен в формате: Bearer {token}",
        },
        "X-API-KEY": {
            "type": "apiKey",
            "name": "X-API-KEY",
            "in": "header",
            "description": "API ключ для аутентификации",
        },
    },
    "USE_SESSION_AUTH": True,
    "DEFAULT_AUTO_SCHEMA_CLASS": "monitoring_app.views.FormOnlySwaggerAutoSchema",
}

# ReDoc
REDOC_SETTINGS = {
    "LAZY_RENDERING": True,
}

# Celery
CELERY_BROKER_URL = (
    "memory://"
    if TESTING
    else f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/0"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

# Проверка подлинности фото
PHOTO_PAD_DEVICE = os.getenv("PHOTO_PAD_DEVICE", "auto")
# Потоки torch на процесс; 0 сохраняет настройки библиотеки.
PHOTO_PAD_TORCH_THREADS = _int_env("PHOTO_PAD_TORCH_THREADS", 4)

# Пакетная проверка фото по расписанию
PHOTO_PAD_HOURLY_BATCH_SIZE = max(1, _int_env("PHOTO_PAD_HOURLY_BATCH_SIZE", 100))
PHOTO_PAD_HOURLY_MAX_RECORDS = max(1, _int_env("PHOTO_PAD_HOURLY_MAX_RECORDS", 200))
PHOTO_PAD_HOURLY_MINUTE = min(max(0, _int_env("PHOTO_PAD_HOURLY_MINUTE", 20)), 59)

# Проверка фото из WebSocket
PHOTO_PAD_WS_SCAN_ENABLED = os.getenv("PHOTO_PAD_WS_SCAN_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
PHOTO_PAD_WS_SCAN_FLUSH_DELAY = max(
    0.1,
    _float_env("PHOTO_PAD_WS_SCAN_FLUSH_DELAY", 0.8),
)
PHOTO_PAD_WS_SCAN_MAX_WAIT = max(
    PHOTO_PAD_WS_SCAN_FLUSH_DELAY,
    _float_env("PHOTO_PAD_WS_SCAN_MAX_WAIT", 2.5),
)
PHOTO_PAD_WS_SCAN_MAX_ITEMS = max(1, _int_env("PHOTO_PAD_WS_SCAN_MAX_ITEMS", 60))
PHOTO_PAD_WS_SCAN_LOCK_TTL = max(10, _int_env("PHOTO_PAD_WS_SCAN_LOCK_TTL", 180))

CELERY_TASK_QUEUES = (Queue("control_app_queue", routing_key="control_app_queue"),)

CELERY_TASK_ROUTES = {
    "monitoring_app.tasks.*": {
        "queue": "control_app_queue",
        "routing_key": "control_app_queue",
    },
}

BACKUP_DB_WEEKLY_DAY_OF_WEEK = os.getenv("BACKUP_DB_WEEKLY_DAY_OF_WEEK", "0").strip() or "0"
BACKUP_DB_WEEKLY_HOUR = min(max(0, _int_env("BACKUP_DB_WEEKLY_HOUR", 23)), 23)
BACKUP_DB_WEEKLY_MINUTE = min(max(0, _int_env("BACKUP_DB_WEEKLY_MINUTE", 30)), 59)
BACKUP_DB_WEEKLY_KEEP_DAYS = max(1, _int_env("BACKUP_DB_WEEKLY_KEEP_DAYS", 30))
BACKUP_DB_WEEKLY_OUTPUT_DIR = os.getenv("BACKUP_DB_WEEKLY_OUTPUT_DIR", "DB").strip() or "DB"
BACKUP_DB_WEEKLY_COMPRESS = os.getenv("BACKUP_DB_WEEKLY_COMPRESS", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
BACKUP_DB_WEEKLY_FORMAT = os.getenv("BACKUP_DB_WEEKLY_FORMAT", "both").strip().lower()
if BACKUP_DB_WEEKLY_FORMAT not in {"json", "sql", "both"}:
    BACKUP_DB_WEEKLY_FORMAT = "both"


def build_celery_beat_schedule(debug: bool) -> dict[str, dict[str, object]]:
    if debug:
        return {}
    return {
        "backup-db-weekly-before-api-attendance-sync": {
            "task": "monitoring_app.tasks.backup_db_task",
            "schedule": crontab(
                day_of_week=BACKUP_DB_WEEKLY_DAY_OF_WEEK,
                hour=str(BACKUP_DB_WEEKLY_HOUR),
                minute=str(BACKUP_DB_WEEKLY_MINUTE),
            ),
            "kwargs": {
                "backup_format": BACKUP_DB_WEEKLY_FORMAT,
                "compress": BACKUP_DB_WEEKLY_COMPRESS,
                "output_dir": BACKUP_DB_WEEKLY_OUTPUT_DIR,
                "keep_days": BACKUP_DB_WEEKLY_KEEP_DAYS,
            },
        },
        "flush-expired-jwt-daily": {
            "task": "monitoring_app.tasks.flush_expired_jwt_task",
            "schedule": crontab(hour="3", minute="30"),
        },
        "get-attendance-every-day-0005": {
            "task": "monitoring_app.tasks.get_all_attendance_task",
            "schedule": crontab(hour="0", minute="5"),
        },
        "sync-staff-from-api-twice-weekly": {
            "task": "monitoring_app.tasks.sync_staff_from_api_task",
            "schedule": crontab(
                day_of_week="1,4",
                hour="5",
                minute="30",
            ),
        },
        "update-lesson-attendance-last-out-every-10-minutes": {
            "task": "monitoring_app.tasks.update_lesson_attendance_last_out",
            "schedule": crontab(minute="*/5"),
        },
        "warmup-cache-every-hour": {
            "task": "monitoring_app.tasks.warmup_cache_task",
            "schedule": crontab(minute="0"),
            "kwargs": {"force": False},
        },
        "rotate-department-confirmation-cache-hourly": {
            "task": "monitoring_app.tasks.rotate_department_confirmation_cache_epoch",
            "schedule": crontab(minute="5"),
        },
        "warmup-cache-hot-daily": {
            "task": "monitoring_app.tasks.warmup_cache_task",
            "schedule": crontab(hour="6", minute="0"),
            "kwargs": {"force": True},
        },
        "warmup-class-location-buffers-every-30-min": {
            "task": "monitoring_app.tasks.warmup_class_location_buffers",
            "schedule": crontab(minute="*/30"),
        },
        "scan-lesson-attendance-photos-hourly": {
            "task": "monitoring_app.tasks.scan_lesson_attendance_photos_hourly",
            "schedule": crontab(minute=str(PHOTO_PAD_HOURLY_MINUTE)),
            "kwargs": {
                "batch_size": PHOTO_PAD_HOURLY_BATCH_SIZE,
                "max_records": PHOTO_PAD_HOURLY_MAX_RECORDS,
                "device": PHOTO_PAD_DEVICE,
                "only_today": True,
            },
        },
        "scan-lesson-attendance-photos-backlog-hourly": {
            "task": "monitoring_app.tasks.scan_lesson_attendance_photos_backlog",
            "schedule": crontab(minute=str((PHOTO_PAD_HOURLY_MINUTE + 30) % 60)),
            "kwargs": {
                "batch_size": min(PHOTO_PAD_HOURLY_BATCH_SIZE, 50),
                "max_records": max(50, min(PHOTO_PAD_HOURLY_MAX_RECORDS // 4, 100)),
                "device": PHOTO_PAD_DEVICE,
            },
        },
        "retrain-photo-pad-weekly": {
            "task": "monitoring_app.tasks.retrain_photo_pad",
            "schedule": crontab(day_of_week="sun", hour="3", minute="0"),
        },
        "clean-old-attendance-photos-daily": {
            "task": "monitoring_app.tasks.clean_old_attendance_photos",
            "schedule": crontab(hour="4", minute="30"),
            "kwargs": {"days_old": 62},
        },
    }


CELERY_BEAT_SCHEDULE = build_celery_beat_schedule(DEBUG)

# Логирование
LOG_DIR = Path(tempfile.mkdtemp(prefix="control_test_logs_")) if TESTING else BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_log_level(value, default):
    if not value:
        return default
    cleaned = str(value).strip().upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    return cleaned if cleaned in allowed else default


def get_log_level(prefix, default=None, override=None):
    """Уровень логирования: по умолчанию зависит от DEBUG, можно override через env."""
    base_default = default or ("DEBUG" if DEBUG else "WARNING")
    if override:
        return _normalize_log_level(override, base_default)
    env_value = os.getenv(f"{prefix}_LOG_LEVEL") or os.getenv("LOG_LEVEL")
    return _normalize_log_level(env_value, base_default)


ADMIN_ERRORS_LEVEL = get_log_level("ADMIN_ERRORS", default="DEBUG")
MONITORING_ADMIN_LEVEL = get_log_level(
    "MONITORING_ADMIN", default=("DEBUG" if DEBUG else "WARNING")
)


APP_LOG_LEVEL = get_log_level("APP", default="INFO" if DEBUG else "WARNING")
_DEFAULT_HANDLERS = ["file", "console"] if DEBUG else ["file"]


def _log_file(name: str, *, formatter: str = "standard", level: str = "INFO") -> dict:
    return {
        "class": "logging.handlers.WatchedFileHandler",
        "filename": str(LOG_DIR / f"{name}.log"),
        "encoding": "utf-8",
        "delay": True,
        "formatter": formatter,
        "level": level,
        "filters": ["ignore_shutdown"],
    }


def _own_file(handler: str, level: str = APP_LOG_LEVEL) -> dict:
    return {"handlers": [handler], "level": level, "propagate": False}


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {module} {funcName} {lineno} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "standard": {
            "format": "{levelname} {asctime} {name} {module} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "filters": {
        "ignore_shutdown": {
            "()": "django_settings.logging_filters.IgnoreShutdownErrorsFilter",
        },
    },
    "handlers": {
        "file": _log_file("app", formatter="verbose", level="DEBUG" if DEBUG else "INFO"),
        "console": {
            "level": "INFO" if DEBUG else "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["ignore_shutdown"],
        },
        "admin_errors_file": _log_file("admin_errors", level=ADMIN_ERRORS_LEVEL),
        "lesson_locations_file": _log_file("lesson_locations"),
        "lesson_locations_not_found_file": _log_file("lesson_locations_not_found"),
        "ws_user_file": _log_file("ws_user"),
        "photo_verdict_file": _log_file("photo_verdict"),
        "face_lab_file": _log_file("face_lab"),
    },
    "root": {"handlers": _DEFAULT_HANDLERS, "level": APP_LOG_LEVEL},
    "loggers": {
        # Свои хендлеры + propagate=False: иначе запись уходит ещё и в родительский файл.
        "django": {"handlers": _DEFAULT_HANDLERS, "level": APP_LOG_LEVEL, "propagate": False},
        "monitoring_app": {
            "handlers": _DEFAULT_HANDLERS,
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "monitoring_app.lesson_locations": _own_file("lesson_locations_file"),
        "monitoring_app.lesson_locations.not_found": _own_file("lesson_locations_not_found_file"),
        "monitoring_app.photo_verdict": _own_file("photo_verdict_file"),
        "monitoring_app.ws_user": _own_file("ws_user_file"),
        "monitoring_app.admin": _own_file("admin_errors_file", MONITORING_ADMIN_LEVEL),
        "monitoring_app.face_lab": _own_file("face_lab_file", "INFO"),
    },
}
