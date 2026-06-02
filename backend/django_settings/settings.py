import os
import json
import socket
from pathlib import Path
from datetime import datetime, timedelta

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")

from kombu import Queue
from dotenv import load_dotenv
from celery.schedules import crontab

# Host names and DEBUG setting
HOST_NAMES = ["RogStrix", "MacBook-Pro.local", "MacbookPro", "Rumishka"]
DEBUG = socket.gethostname() in HOST_NAMES

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

load_dotenv(BASE_DIR / ".env")


def _csv_env_frozenset(name: str, default: str) -> frozenset[str]:
    """Parse comma-separated env var into a normalized frozenset."""
    return frozenset(
        item.strip() for item in os.getenv(name, default).split(",") if item.strip()
    )


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


# Custom settings
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
ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES = int(
    os.getenv("ATTENDANCE_AMBIGUOUS_EXIT_GRACE_MINUTES", "45")
)
ATTENDANCE_WRITE_HMAC_SECRET = os.getenv("ATTENDANCE_WRITE_HMAC_SECRET", "").strip()
ATTENDANCE_WRITE_HMAC_TTL_SECONDS = _int_env("ATTENDANCE_WRITE_HMAC_TTL_SECONDS", 300)
ATTENDANCE_API_TERMINAL_POOLS = _json_env_dict("ATTENDANCE_API_TERMINAL_POOLS")
# ArcFace/InsightFace cosine thresholds are calibrated on local staff masks/samples.
# Current calibration (1000 staff masks, 50k impostor pairs): impostor max ~=0.413,
# p99 ~=0.220. Keep the accept threshold far above impostors, but low enough for
# glasses/no-glasses and webcam drift when the nearest-other gap is large.
FACE_RECOGNITION_THRESHOLD = float(os.getenv("FACE_RECOGNITION_THRESHOLD", "0.72"))
FACE_RECOGNITION_THRESHOLD_RELAXED = float(os.getenv("FACE_RECOGNITION_THRESHOLD_RELAXED", "0.62"))
FACE_RECOGNITION_MIN_NEIGHBOR_GAP = float(os.getenv("FACE_RECOGNITION_MIN_NEIGHBOR_GAP", "0.10"))
FACE_ENCODING_TTA_ENABLE = os.getenv(
    "FACE_ENCODING_TTA_ENABLE", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_ENCODING_TTA_FOR_BULK_BUILD = os.getenv(
    "FACE_ENCODING_TTA_FOR_BULK_BUILD", "0"
).strip().lower() in ("1", "true", "yes", "on")
FACE_ENCODING_TTA_MAX_EXTRA_VARIANTS = int(
    os.getenv("FACE_ENCODING_TTA_MAX_EXTRA_VARIANTS", "5")
)
FACE_ENCODING_TTA_MIN_CONSENSUS_COS = float(
    os.getenv("FACE_ENCODING_TTA_MIN_CONSENSUS_COS", "0.76")
)
FACE_ENCODING_TTA_MIN_FACE_IOU = float(
    os.getenv("FACE_ENCODING_TTA_MIN_FACE_IOU", "0.20")
)
FACE_RUNTIME_INCLUDE_AUGMENTED_GALLERY = os.getenv(
    "FACE_RUNTIME_INCLUDE_AUGMENTED_GALLERY", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_RUNTIME_AUGMENTED_GALLERY_MAX = int(
    os.getenv("FACE_RUNTIME_AUGMENTED_GALLERY_MAX", "24")
)
FACE_RUNTIME_INCLUDE_FACE_SAMPLES = os.getenv(
    "FACE_RUNTIME_INCLUDE_FACE_SAMPLES", "1"
).strip().lower() in ("1", "true", "yes", "on")
# Runtime variants are not synthetic training data. They are consensus-checked
# templates from the same image used only for matching camera/light/glasses drift.
# 0.84 keeps light/JPEG/sharpness variants close to the original ArcFace vector.
FACE_RUNTIME_CONDITION_VARIANTS_ENABLE = os.getenv(
    "FACE_RUNTIME_CONDITION_VARIANTS_ENABLE", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_RUNTIME_CONDITION_VARIANTS_MAX = int(os.getenv("FACE_RUNTIME_CONDITION_VARIANTS_MAX", "3"))
FACE_RUNTIME_CONDITION_VARIANT_MIN_COS = float(
    os.getenv("FACE_RUNTIME_CONDITION_VARIANT_MIN_COS", "0.84")
)
FACE_RUNTIME_GLASSES_VARIANTS_ENABLE = os.getenv(
    "FACE_RUNTIME_GLASSES_VARIANTS_ENABLE", "1"
).strip().lower() in ("1", "true", "yes", "on")
# Glasses change the periocular region more than lighting TTA, so the consensus
# floor is lower, but still blocks identity-drifting inpaint/overlay variants.
FACE_RUNTIME_GLASSES_VARIANT_MIN_COS = float(
    os.getenv("FACE_RUNTIME_GLASSES_VARIANT_MIN_COS", "0.68")
)
FACE_RUNTIME_GLASSES_VARIANT_INPAINT_DILATE = int(
    os.getenv("FACE_RUNTIME_GLASSES_VARIANT_INPAINT_DILATE", "7")
)
FACE_RUNTIME_GLASSES_VARIANT_INPAINT_RADIUS = int(
    os.getenv("FACE_RUNTIME_GLASSES_VARIANT_INPAINT_RADIUS", "3")
)
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
FACE_TRAINING_LESSON_ATTENDANCE_MAX = int(
    os.getenv("FACE_TRAINING_LESSON_ATTENDANCE_MAX", "80")
)
FACE_GALLERY_ENROLLMENT_PAD_VALIDATE = os.getenv(
    "FACE_GALLERY_ENROLLMENT_PAD_VALIDATE", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_GALLERY_ENROLLMENT_REQUIRE_PAD_MODEL = os.getenv(
    "FACE_GALLERY_ENROLLMENT_REQUIRE_PAD_MODEL", "0"
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
FACE_GALLERY_ENROLLMENT_BLUR_MIN = float(
    os.getenv("FACE_GALLERY_ENROLLMENT_BLUR_MIN", "18.0")
)
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
FACE_GALLERY_REAL_DEDUPE_MAX_COS = float(
    os.getenv("FACE_GALLERY_REAL_DEDUPE_MAX_COS", "0.9975")
)
FACE_GALLERY_REAL_MAX_PROTOTYPES = int(
    os.getenv("FACE_GALLERY_REAL_MAX_PROTOTYPES", "48")
)
FACE_GALLERY_REAL_META_ACCEPTED_DETAIL_LIMIT = int(
    os.getenv("FACE_GALLERY_REAL_META_ACCEPTED_DETAIL_LIMIT", "48")
)
FACE_GALLERY_REAL_META_REJECTED_DETAIL_LIMIT = int(
    os.getenv("FACE_GALLERY_REAL_META_REJECTED_DETAIL_LIMIT", "24")
)

FACE_VERIFY_THRESHOLD_VERIFIED = float(
    os.getenv("FACE_VERIFY_THRESHOLD_VERIFIED", str(FACE_RECOGNITION_THRESHOLD))
)
# Weak gallery: fewer distinct enrollment sources or templates than FACE_VERIFY_MIN_*.
# Compare is still binary YES/NO: weak path requires score >= this stricter cosine floor
# (strong gallery uses FACE_VERIFY_THRESHOLD_VERIFIED only).
FACE_VERIFY_THRESHOLD_VERIFIED_WEAK_GALLERY = float(
    os.getenv("FACE_VERIFY_THRESHOLD_VERIFIED_WEAK_GALLERY", "0.72")
)
FACE_VERIFY_THRESHOLD_REVIEW = float(os.getenv("FACE_VERIFY_THRESHOLD_REVIEW", "0.68"))
FACE_VERIFY_STRONG_GALLERY_RELAXED_ENABLE = os.getenv(
    "FACE_VERIFY_STRONG_GALLERY_RELAXED_ENABLE", "1"
).strip().lower() in ("1", "true", "yes")
FACE_VERIFY_STRONG_GALLERY_RELAXED_THRESHOLD = float(
    os.getenv("FACE_VERIFY_STRONG_GALLERY_RELAXED_THRESHOLD", "0.70")
)
FACE_VERIFY_STRONG_GALLERY_RELAXED_GAP_MIN = float(
    os.getenv("FACE_VERIFY_STRONG_GALLERY_RELAXED_GAP_MIN", "0.18")
)
FACE_VERIFY_MIN_ENROLLMENT_SOURCES = int(
    os.getenv("FACE_VERIFY_MIN_ENROLLMENT_SOURCES", "2")
)
FACE_VERIFY_MIN_TEMPLATES_STRONG = int(
    os.getenv("FACE_VERIFY_MIN_TEMPLATES_STRONG", "2")
)
FACE_VERIFY_MAX_COSINE_FACTOR = float(
    os.getenv("FACE_VERIFY_MAX_COSINE_FACTOR", "0.97")
)
FACE_VERIFY_PROBE_DET_SCORE_MIN = float(
    os.getenv("FACE_VERIFY_PROBE_DET_SCORE_MIN", "0.35")
)
FACE_VERIFY_PROBE_FACE_AREA_RATIO_MIN = float(
    os.getenv("FACE_VERIFY_PROBE_FACE_AREA_RATIO_MIN", "0.008")
)
FACE_VERIFY_PROBE_BLUR_MIN = float(os.getenv("FACE_VERIFY_PROBE_BLUR_MIN", "12.0"))
FACE_VERIFY_PROBE_BRIGHTNESS_MIN = float(
    os.getenv("FACE_VERIFY_PROBE_BRIGHTNESS_MIN", "22.0")
)
FACE_VERIFY_PROBE_BRIGHTNESS_MAX = float(
    os.getenv("FACE_VERIFY_PROBE_BRIGHTNESS_MAX", "238.0")
)
FACE_VERIFY_PROBE_MAX_ABS_YAW = float(
    os.getenv("FACE_VERIFY_PROBE_MAX_ABS_YAW", "40.0")
)
FACE_VERIFY_PROBE_MAX_ABS_PITCH = float(
    os.getenv("FACE_VERIFY_PROBE_MAX_ABS_PITCH", "35.0")
)
FACE_VERIFY_IMPOSTOR_GAP_ENABLE = os.getenv(
    "FACE_VERIFY_IMPOSTOR_GAP_ENABLE", "1"
).strip().lower() in ("1", "true", "yes", "on")
FACE_VERIFY_IMPOSTOR_GAP_MIN = float(os.getenv("FACE_VERIFY_IMPOSTOR_GAP_MIN", "0.06"))
FACE_VERIFY_IMPOSTOR_MIN_OTHER_SCORE = float(
    os.getenv("FACE_VERIFY_IMPOSTOR_MIN_OTHER_SCORE", "0.60")
)
# Cold-start verify: only when runtime gallery has no gallery_real.npy rows (avatar/mask only).
# Softer cosine floor than weak-gallery strict, but stricter probe quality (det + face area).
FACE_VERIFY_THRESHOLD_COLD_START = float(
    os.getenv("FACE_VERIFY_THRESHOLD_COLD_START", "0.835")
)
FACE_VERIFY_COLD_START_DET_MIN = float(
    os.getenv("FACE_VERIFY_COLD_START_DET_MIN", "0.42")
)
FACE_VERIFY_COLD_START_FACE_AREA_MIN = float(
    os.getenv("FACE_VERIFY_COLD_START_FACE_AREA_MIN", "0.012")
)
FACE_VERIFY_COLD_START_STRONG_SCORE_MARGIN = float(
    os.getenv("FACE_VERIFY_COLD_START_STRONG_SCORE_MARGIN", "0.025")
)
FACE_VERIFY_COLD_START_STRONG_DET_MIN = float(
    os.getenv("FACE_VERIFY_COLD_START_STRONG_DET_MIN", "0.72")
)
FACE_VERIFY_COLD_START_STRONG_FACE_AREA_MIN = float(
    os.getenv("FACE_VERIFY_COLD_START_STRONG_FACE_AREA_MIN", "0.04")
)
FACE_VERIFY_SINGLE_PHOTO_RELAXED_ENABLE = os.getenv(
    "FACE_VERIFY_SINGLE_PHOTO_RELAXED_ENABLE", "1"
).strip().lower() in ("1", "true", "yes", "on")
# Single-photo fallback keeps the normal verified threshold, but also requires
# good probe quality, several same-image runtime variants, and a large impostor
# gap. This is for “only one photo exists”, not for lowering security globally.
FACE_VERIFY_SINGLE_PHOTO_THRESHOLD = float(os.getenv("FACE_VERIFY_SINGLE_PHOTO_THRESHOLD", "0.72"))
FACE_VERIFY_SINGLE_PHOTO_GAP_MIN = float(os.getenv("FACE_VERIFY_SINGLE_PHOTO_GAP_MIN", "0.18"))
FACE_VERIFY_SINGLE_PHOTO_MIN_TEMPLATES = int(
    os.getenv("FACE_VERIFY_SINGLE_PHOTO_MIN_TEMPLATES", "3")
)
# Trusted face bootstrap samples (StaffFaceSample): cap and near-duplicate rejection.
FACE_BOOTSTRAP_MAX_ACTIVE_SAMPLES = int(
    os.getenv("FACE_BOOTSTRAP_MAX_ACTIVE_SAMPLES", "5")
)
FACE_SAMPLE_DEDUPE_MAX_COS = float(os.getenv("FACE_SAMPLE_DEDUPE_MAX_COS", "0.992"))

# Staff / Face Lab: server normalizes uploads to JPEG (drops non-image payloads, EXIF, etc.).
STAFF_UPLOAD_JPEG_QUALITY = int(os.getenv("STAFF_UPLOAD_JPEG_QUALITY", "92"))
STAFF_UPLOAD_MAX_MEGAPIXELS = int(os.getenv("STAFF_UPLOAD_MAX_MEGAPIXELS", "36"))
STAFF_AVATAR_UPLOAD_MAX_BYTES = int(
    os.getenv("STAFF_AVATAR_UPLOAD_MAX_BYTES", str(12 * 1024 * 1024))
)

AUGMENT_SYNTH_GLASSES_RANDOM_P = float(
    os.getenv("AUGMENT_SYNTH_GLASSES_RANDOM_P", "0.22")
)
AUGMENT_GLASSES_HEURISTIC_HORIZ_DOM = float(
    os.getenv("AUGMENT_GLASSES_HEURISTIC_HORIZ_DOM", "1.12")
)
AUGMENT_GLASSES_HEURISTIC_BRIDGE_DARK = float(
    os.getenv("AUGMENT_GLASSES_HEURISTIC_BRIDGE_DARK", "0.055")
)
AUGMENT_GLASSES_INPAINT_ENABLE = os.getenv(
    "AUGMENT_GLASSES_INPAINT_ENABLE", "1"
).strip().lower() in ("1", "true", "yes")
FACE_PARSING_ENABLE = os.getenv("FACE_PARSING_ENABLE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
FACE_PARSING_AUTO_DOWNLOAD = os.getenv(
    "FACE_PARSING_AUTO_DOWNLOAD", "0"
).strip().lower() in ("1", "true", "yes")
_face_parsing_path = os.getenv("FACE_PARSING_MODEL_PATH", "").strip()
FACE_PARSING_MODEL_PATH = (
    str(Path(_face_parsing_path).expanduser().resolve()) if _face_parsing_path else None
)
FACE_PARSING_DOWNLOAD_URL = os.getenv(
    "FACE_PARSING_DOWNLOAD_URL",
    "https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx",
)
FACE_PARSING_GLASSES_FRAC_MIN = _float_env("FACE_PARSING_GLASSES_FRAC_MIN", 0.00035)
FACE_PARSING_USE_FOR_AUGMENT = os.getenv(
    "FACE_PARSING_USE_FOR_AUGMENT", "1"
).strip().lower() in ("1", "true", "yes")
FACE_PARSING_USE_FOR_API = os.getenv(
    "FACE_PARSING_USE_FOR_API", "1"
).strip().lower() in ("1", "true", "yes")
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

# Secret keys and API configurations
SECRET_KEY = os.getenv("SECRET_KEY")
SECRET_API = os.getenv("SECRET_API")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
# Face Lab: Edge neural TTS (Microsoft, via edge-tts; no API key). Optional voice overrides.
FACE_LAB_EDGE_TTS_VOICE_RU = os.getenv(
    "FACE_LAB_EDGE_TTS_VOICE_RU", "ru-RU-SvetlanaNeural"
).strip()
FACE_LAB_EDGE_TTS_VOICE_KK = os.getenv(
    "FACE_LAB_EDGE_TTS_VOICE_KK", "kk-KZ-AigulNeural"
).strip()
FACE_LAB_EDGE_TTS_VOICE_EN = os.getenv(
    "FACE_LAB_EDGE_TTS_VOICE_EN", "en-US-JennyNeural"
).strip()
MAIN_IP = os.getenv("MAIN_IP")
DB_TYPE = os.getenv("DB_TYPE", "sqlite3").lower()


# Email configurations
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND")
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "0"))
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

# Data upload settings
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000

# Grappelli Admin Settings
GRAPPELLI_ADMIN_TITLE = "Панель управления мониторинга"
GRAPPELLI_AUTOCOMPLETE_LIMIT = 15
GRAPPELLI_SWITCH_USER = True
GRAPPELLI_CLEAN_INPUT_TYPES = True
GRAPPELLI_INDEX_DASHBOARD = "django_settings.dashboard.CustomIndexDashboard"

# Application definition
INSTALLED_APPS = [
    "daphne",
    "channels",
    "grappelli.dashboard",
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
    "django_celery_beat",
    "django_celery_results",
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

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
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
    "monitoring_app.face_lab_log_middleware.FaceLabRequestLogMiddleware",
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
    # If production using MySQL, PostgreSQL or SQLite
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
    ("mediapipe", FRONTEND_DIR / "dist/mediapipe"),
    ("mediapipe-models", FRONTEND_DIR / "dist/mediapipe-models"),
]

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

BACKUP_DB_DIR = BASE_DIR.parent / "DB"

# Attendance and augment paths
ATTENDANCE_URL = "/attendance_media/"
_attendance_root_env = os.getenv("ATTENDANCE_ROOT")
ATTENDANCE_ROOT = (
    Path(_attendance_root_env).expanduser().resolve()
    if _attendance_root_env
    else (MEDIA_ROOT / "control_image")
)

AUGMENT_URL = "/augment_media/"
_augment_root_env = os.getenv("AUGMENT_ROOT")
_default_augment_template = (
    MEDIA_ROOT / "user_images" / "{staff_pin}" / "augmented_images"
)
AUGMENT_ROOT = (
    _augment_root_env if _augment_root_env else str(_default_augment_template)
)

_general_models_env = os.getenv("GENERAL_MODELS_ROOT")
GENERAL_MODELS_ROOT = (
    Path(_general_models_env).expanduser().resolve()
    if _general_models_env
    else (BASE_DIR / "models")
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST framework configurations
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "monitoring_app.authentication.SessionAuthenticationAllowTokenOrApiKey",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
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

_JWT_ACCESS_MINUTES = _jwt_lifetime_minutes("JWT_ACCESS_LIFETIME_MINUTES", 10, 30)
_JWT_REFRESH_MINUTES = _jwt_lifetime_minutes("JWT_REFRESH_LIFETIME_MINUTES", 30, 120)

SIMPLE_JWT.update(
    {
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=_JWT_ACCESS_MINUTES),
        "REFRESH_TOKEN_LIFETIME": timedelta(minutes=_JWT_REFRESH_MINUTES),
        "SLIDING_TOKEN_LIFETIME": timedelta(minutes=_JWT_ACCESS_MINUTES),
        "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(minutes=_JWT_REFRESH_MINUTES),
    }
)

# Swagger settings
SWAGGER_SETTINGS = {
    "LOGIN_URL": "login_view",
    "LOGOUT_URL": "logout",
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

# ReDoc settings
REDOC_SETTINGS = {
    "LAZY_RENDERING": True,
}

# Celery configurations
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

# Photo PAD (anti-spoof) config
# ----------------------------
PHOTO_PAD_DEVICE = os.getenv("PHOTO_PAD_DEVICE", "auto")
PHOTO_PAD_GLASSES_REFLECTION_ENABLE = os.getenv(
    "PHOTO_PAD_GLASSES_REFLECTION_ENABLE", "1"
).strip().lower() in ("1", "true", "yes")
PHOTO_PAD_GUIDE_MODELS_ROOT = Path(
    os.getenv("PHOTO_PAD_GUIDE_MODELS_ROOT", str(BASE_DIR / "models"))
).expanduser()
PHOTO_PAD_GUIDE_FACE_DETECTOR_PROTO = os.getenv(
    "PHOTO_PAD_GUIDE_FACE_DETECTOR_PROTO",
    str(PHOTO_PAD_GUIDE_MODELS_ROOT / "deploy.prototxt.txt"),
)
PHOTO_PAD_GUIDE_FACE_DETECTOR_MODEL = os.getenv(
    "PHOTO_PAD_GUIDE_FACE_DETECTOR_MODEL",
    str(PHOTO_PAD_GUIDE_MODELS_ROOT / "res10_300x300_ssd_iter_140000.caffemodel"),
)
PHOTO_PAD_GUIDE_COLOR_MODEL = os.getenv(
    "PHOTO_PAD_GUIDE_COLOR_MODEL",
    str(PHOTO_PAD_GUIDE_MODELS_ROOT / "replay-attack_ycrcb_luv_extraTreesClassifier.pkl"),
)
PHOTO_PAD_MINIFASNET_ONNX_MODEL = os.getenv(
    "PHOTO_PAD_MINIFASNET_ONNX_MODEL",
    str(PHOTO_PAD_GUIDE_MODELS_ROOT / "minifasnet_v2.onnx"),
)

# Hourly batch PAD scan (Celery beat)
PHOTO_PAD_HOURLY_BATCH_SIZE = max(1, _int_env("PHOTO_PAD_HOURLY_BATCH_SIZE", 100))
PHOTO_PAD_HOURLY_MAX_RECORDS = max(1, _int_env("PHOTO_PAD_HOURLY_MAX_RECORDS", 200))
PHOTO_PAD_HOURLY_MINUTE = min(max(0, _int_env("PHOTO_PAD_HOURLY_MINUTE", 20)), 59)

# WebSocket-triggered PAD flush
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

PHOTO_PAD_NUMBERS = {
    # --- Presentation detectors (device / screen frame heuristics) ---
    "device_min_conf": _float_env("PHOTO_PAD_DEVICE_MIN_CONF", 0.16),
    "device_min_area_ratio": _float_env("PHOTO_PAD_DEVICE_MIN_AREA_RATIO", 0.015),
    "device_ratio_ref": _float_env("PHOTO_PAD_DEVICE_RATIO_REF", 0.25),
    "device_score_conf_weight": _float_env("PHOTO_PAD_DEVICE_SCORE_CONF_WEIGHT", 0.60),
    "device_score_ratio_weight": _float_env("PHOTO_PAD_DEVICE_SCORE_RATIO_WEIGHT", 0.40),
    # Поиск прямоугольной рамки экрана
    "frame_canny_low": _int_env("PHOTO_PAD_FRAME_CANNY_LOW", 50),
    "frame_canny_high": _int_env("PHOTO_PAD_FRAME_CANNY_HIGH", 160),
    "frame_gaussian_kernel": _int_env("PHOTO_PAD_FRAME_GAUSSIAN_KERNEL", 5),
    "frame_dilate_kernel": _int_env("PHOTO_PAD_FRAME_DILATE_KERNEL", 3),
    "frame_min_area_ratio": _float_env("PHOTO_PAD_FRAME_MIN_AREA_RATIO", 0.10),
    "frame_poly_epsilon": _float_env("PHOTO_PAD_FRAME_POLY_EPSILON", 0.02),
    "frame_min_solidity": _float_env("PHOTO_PAD_FRAME_MIN_SOLIDITY", 0.80),
    "frame_ratio_ref": _float_env("PHOTO_PAD_FRAME_RATIO_REF", 0.55),
    "frame_face_bonus": _float_env("PHOTO_PAD_FRAME_FACE_BONUS", 0.15),
    "frame_border_bonus": _float_env("PHOTO_PAD_FRAME_BORDER_BONUS", 0.08),
    "frame_border_margin_px": _int_env("PHOTO_PAD_FRAME_BORDER_MARGIN_PX", 8),
    "frame_tag_threshold": _float_env("PHOTO_PAD_FRAME_TAG_THRESHOLD", 0.30),
    # --- Quality axis (authenticity vs exposure/blur/small face) ---
    "quality_blur_min": _float_env("PHOTO_PAD_QUALITY_BLUR_MIN", 45.0),
    "quality_brightness_min": _float_env("PHOTO_PAD_QUALITY_BRIGHTNESS_MIN", 35.0),
    "quality_brightness_max": _float_env("PHOTO_PAD_QUALITY_BRIGHTNESS_MAX", 225.0),
    "quality_contrast_min": _float_env("PHOTO_PAD_QUALITY_CONTRAST_MIN", 24.0),
    "quality_face_ratio_min": _float_env("PHOTO_PAD_QUALITY_FACE_RATIO_MIN", 0.035),
    "quality_penalty_blur": _float_env("PHOTO_PAD_QUALITY_PENALTY_BLUR", 0.35),
    "quality_penalty_exposure": _float_env("PHOTO_PAD_QUALITY_PENALTY_EXPOSURE", 0.20),
    "quality_penalty_contrast": _float_env("PHOTO_PAD_QUALITY_PENALTY_CONTRAST", 0.20),
    "quality_penalty_small_face": _float_env("PHOTO_PAD_QUALITY_PENALTY_SMALL_FACE", 0.25),
    "quality_poor_threshold": _float_env("PHOTO_PAD_QUALITY_POOR_THRESHOLD", 0.45),
    # --- Fused spoof risk weights (face ROI; quality not mixed into decision branches) ---
    "risk_weight_deepface": _float_env("PHOTO_PAD_RISK_WEIGHT_DEEPFACE", 0.46),
    "risk_weight_device": _float_env("PHOTO_PAD_RISK_WEIGHT_DEVICE", 0.22),
    "risk_weight_frame": _float_env("PHOTO_PAD_RISK_WEIGHT_FRAME", 0.12),
    # --- Rule engine: FasNet + geometry + recapture + shield ---
    "decision_device_present_min": _float_env("PHOTO_PAD_DECISION_DEVICE_PRESENT_MIN", 0.24),
    "decision_device_confirmed_strong_min": _float_env(
        "PHOTO_PAD_DECISION_DEVICE_CONFIRMED_STRONG_MIN", 0.48
    ),
    "decision_device_confirmed_single_min": _float_env(
        "PHOTO_PAD_DECISION_DEVICE_CONFIRMED_SINGLE_MIN", 0.36
    ),
    "decision_frame_present_min": _float_env("PHOTO_PAD_DECISION_FRAME_PRESENT_MIN", 0.34),
    "decision_strong_device_min": _float_env("PHOTO_PAD_DECISION_STRONG_DEVICE_MIN", 0.40),
    "decision_strong_frame_min": _float_env("PHOTO_PAD_DECISION_STRONG_FRAME_MIN", 0.34),
    "decision_quality_poor_min": _float_env("PHOTO_PAD_DECISION_QUALITY_POOR_MIN", 0.45),
    "decision_deepfake_review_min": _float_env("PHOTO_PAD_DECISION_DEEPFAKE_REVIEW_MIN", 0.65),
    "decision_deepfake_device_min": _float_env("PHOTO_PAD_DECISION_DEEPFAKE_DEVICE_MIN", 0.92),
    "decision_deepfake_very_high": _float_env("PHOTO_PAD_DECISION_DEEPFAKE_VERY_HIGH", 0.985),
    "decision_deepfake_mid_suspicious_min": _float_env(
        "PHOTO_PAD_DECISION_DEEPFAKE_MID_SUSPICIOUS_MIN", 0.82
    ),
    "decision_mid_device_min": _float_env("PHOTO_PAD_DECISION_MID_DEVICE_MIN", 0.20),
    "decision_mid_frame_min": _float_env("PHOTO_PAD_DECISION_MID_FRAME_MIN", 0.24),
    "decision_quality_combined_review_sum_min": _float_env(
        "PHOTO_PAD_DECISION_QUALITY_COMBINED_REVIEW_SUM_MIN", 0.54
    ),
    "decision_quality_device_review_min": _float_env(
        "PHOTO_PAD_DECISION_QUALITY_DEVICE_REVIEW_MIN", 0.20
    ),
    "decision_quality_frame_review_min": _float_env(
        "PHOTO_PAD_DECISION_QUALITY_FRAME_REVIEW_MIN", 0.24
    ),
    "decision_suspicious_device_min": _float_env("PHOTO_PAD_DECISION_SUSPICIOUS_DEVICE_MIN", 0.34),
    "decision_suspicious_frame_min": _float_env("PHOTO_PAD_DECISION_SUSPICIOUS_FRAME_MIN", 0.42),
    "decision_weak_device_min": _float_env("PHOTO_PAD_DECISION_WEAK_DEVICE_MIN", 0.16),
    "decision_weak_frame_min": _float_env("PHOTO_PAD_DECISION_WEAK_FRAME_MIN", 0.20),
    "decision_weak_combined_sum_min": _float_env("PHOTO_PAD_DECISION_WEAK_COMBINED_SUM_MIN", 0.24),
    # --- Glasses reflection guard (soften false device hits on lenses) ---
    "glasses_mask_min_pixels": _int_env("PHOTO_PAD_GLASSES_MASK_MIN_PIXELS", 24),
    "glasses_mask_dilate": _int_env("PHOTO_PAD_GLASSES_MASK_DILATE", 11),
    "glasses_device_overlap_skip": _float_env("PHOTO_PAD_GLASSES_DEVICE_OVERLAP_SKIP", 0.42),
    "glasses_device_overlap_soft": _float_env("PHOTO_PAD_GLASSES_DEVICE_OVERLAP_SOFT", 0.14),
    # Face-centric gating (PAD v4)
    "device_face_expand_scale": _float_env("PHOTO_PAD_DEVICE_FACE_EXPAND_SCALE", 1.38),
    "device_face_iou_min": _float_env("PHOTO_PAD_DEVICE_FACE_IOU_MIN", 0.04),
    "device_face_cover_ratio_min": _float_env("PHOTO_PAD_DEVICE_FACE_COVER_RATIO_MIN", 0.14),
    "frame_face_expand_scale": _float_env("PHOTO_PAD_FRAME_FACE_EXPAND_SCALE", 1.42),
    "frame_face_iou_min": _float_env("PHOTO_PAD_FRAME_FACE_IOU_MIN", 0.08),
    "frame_face_max_quad_area_ratio": _float_env("PHOTO_PAD_FRAME_FACE_MAX_QUAD_AREA_RATIO", 0.48),
    "frame_face_min_cover_when_large_quad": _float_env(
        "PHOTO_PAD_FRAME_FACE_MIN_COVER_WHEN_LARGE_QUAD", 0.40
    ),
    # --- Inner-face recapture (FFT ring + Sobel anisotropy) ---
    "recapture_fft_ring_inner": _int_env("PHOTO_PAD_RECAPTURE_FFT_RING_INNER", 8),
    "recapture_fft_ring_outer": _int_env("PHOTO_PAD_RECAPTURE_FFT_RING_OUTER", 42),
    "recapture_fft_baseline": _float_env("PHOTO_PAD_RECAPTURE_FFT_BASELINE", 0.42),
    "recapture_fft_scale": _float_env("PHOTO_PAD_RECAPTURE_FFT_SCALE", 0.24),
    "recapture_sobel_aniso_min": _float_env("PHOTO_PAD_RECAPTURE_SOBEL_ANISO_MIN", 2.05),
    "recapture_sobel_aniso_scale": _float_env("PHOTO_PAD_RECAPTURE_SOBEL_ANISO_SCALE", 0.35),
    "recapture_mid": _float_env("PHOTO_PAD_RECAPTURE_MID", 0.22),
    "recapture_strong": _float_env("PHOTO_PAD_RECAPTURE_STRONG", 0.38),
    "recapture_isolated_extreme_single_channel_min": _float_env(
        "PHOTO_PAD_RECAPTURE_ISOLATED_EXTREME_REVIEW_MIN", 0.90
    ),
    "recapture_isolated_moire_forgive_min_rec": _float_env(
        "PHOTO_PAD_RECAPTURE_ISOLATED_MOIRE_FORGIVE_MIN_REC", 0.84
    ),
    "recapture_isolated_moire_max_quality_penalty": _float_env(
        "PHOTO_PAD_RECAPTURE_ISOLATED_MOIRE_MAX_QUALITY_PENALTY", 0.10
    ),
    "risk_weight_recapture": _float_env("PHOTO_PAD_RISK_WEIGHT_RECAPTURE", 0.20),
    "decision_recapture_review_min": _float_env("PHOTO_PAD_DECISION_RECAPTURE_REVIEW_MIN", 0.18),
    "decision_recapture_corroboration_min": _float_env(
        "PHOTO_PAD_DECISION_RECAPTURE_CORROBORATION_MIN", 0.26
    ),
    "recapture_inner_face_scale": _float_env("PHOTO_PAD_RECAPTURE_INNER_FACE_SCALE", 0.62),
    "recapture_min_laplacian_var": _float_env("PHOTO_PAD_RECAPTURE_MIN_LAPLACIAN_VAR", 18.0),
    "recapture_blur_dampen_factor": _float_env("PHOTO_PAD_RECAPTURE_BLUR_DAMPEN_FACTOR", 0.38),
    # --- Normal-live shield (blocks weak-geometry → review when other cues are calm) ---
    "shield_max_device_face": _float_env("PHOTO_PAD_SHIELD_MAX_DEVICE_FACE", 0.175),
    "shield_max_frame_face": _float_env("PHOTO_PAD_SHIELD_MAX_FRAME_FACE", 0.205),
    "shield_max_recapture": _float_env("PHOTO_PAD_SHIELD_MAX_RECAPTURE", 0.18),
    "shield_max_quality_penalty": _float_env("PHOTO_PAD_SHIELD_MAX_QUALITY_PENALTY", 0.38),
    "no_fake_susp_min_face_area_ratio": _float_env(
        "PHOTO_PAD_NO_FAKE_SUSP_MIN_FACE_AREA_RATIO", 0.034
    ),
    "quality_degraded_force_review_penalty_min": _float_env(
        "PHOTO_PAD_QUALITY_DEGRADED_FORCE_REVIEW_PENALTY_MIN", 0.55
    ),
    # Texture/recapture spoof conclusions require adequate ROI (face size, sharpness)
    "presentation_texture_min_face_area_ratio": _float_env(
        "PHOTO_PAD_PRESENTATION_TEXTURE_MIN_FACE_AREA_RATIO", 0.042
    ),
    "presentation_texture_max_quality_penalty": _float_env(
        "PHOTO_PAD_PRESENTATION_TEXTURE_MAX_QUALITY_PENALTY", 0.30
    ),
    # --- Face ROI color histograms (YCrCb/Luv, corroborative PAD channel) ---
    "color_hist_inner_face_scale": _float_env("PHOTO_PAD_COLOR_HIST_INNER_FACE_SCALE", 0.76),
    "color_hist_mid": _float_env("PHOTO_PAD_COLOR_HIST_MID", 0.24),
    "color_hist_strong": _float_env("PHOTO_PAD_COLOR_HIST_STRONG", 0.40),
    "color_hist_low_entropy_ref": _float_env("PHOTO_PAD_COLOR_HIST_LOW_ENTROPY_REF", 0.58),
    "color_hist_peak_mass_ref": _float_env("PHOTO_PAD_COLOR_HIST_PEAK_MASS_REF", 0.32),
    "color_hist_sparse_occupancy_ref": _float_env(
        "PHOTO_PAD_COLOR_HIST_SPARSE_OCCUPANCY_REF", 0.56
    ),
    "color_hist_flat_chroma_std": _float_env("PHOTO_PAD_COLOR_HIST_FLAT_CHROMA_STD", 13.0),
    "color_hist_luma_std_min": _float_env("PHOTO_PAD_COLOR_HIST_LUMA_STD_MIN", 22.0),
    "color_hist_min_face_area_ratio": _float_env("PHOTO_PAD_COLOR_HIST_MIN_FACE_AREA_RATIO", 0.034),
    "guide_face_detector_conf_min": _float_env("PHOTO_PAD_GUIDE_FACE_DETECTOR_CONF_MIN", 0.50),
    "guide_color_model_mid": _float_env("PHOTO_PAD_GUIDE_COLOR_MODEL_MID", 0.50),
    "guide_color_model_strong": _float_env("PHOTO_PAD_GUIDE_COLOR_MODEL_STRONG", 0.70),
    "minifasnet_onnx_crop_scale": _float_env("PHOTO_PAD_MINIFASNET_ONNX_CROP_SCALE", 2.70),
    "minifasnet_onnx_mid": _float_env("PHOTO_PAD_MINIFASNET_ONNX_MID", 0.50),
    "minifasnet_onnx_strong": _float_env("PHOTO_PAD_MINIFASNET_ONNX_STRONG", 0.70),
    "spoof_model_family_mid": _float_env("PHOTO_PAD_SPOOF_MODEL_FAMILY_MID", 0.45),
    "spoof_model_family_strong": _float_env("PHOTO_PAD_SPOOF_MODEL_FAMILY_STRONG", 0.70),
    "spoof_model_disagreement_min": _float_env("PHOTO_PAD_SPOOF_MODEL_DISAGREEMENT_MIN", 0.45),
    "ensemble_review_vote_min": _float_env("PHOTO_PAD_ENSEMBLE_REVIEW_VOTE_MIN", 0.35),
    "ensemble_strong_vote_min": _float_env("PHOTO_PAD_ENSEMBLE_STRONG_VOTE_MIN", 0.58),
    "ensemble_suspicious_score_min": _float_env("PHOTO_PAD_ENSEMBLE_SUSPICIOUS_SCORE_MIN", 0.52),
    "ensemble_review_score_min": _float_env("PHOTO_PAD_ENSEMBLE_REVIEW_SCORE_MIN", 0.30),
    "ensemble_suspicious_family_min": _int_env("PHOTO_PAD_ENSEMBLE_SUSPICIOUS_FAMILY_MIN", 2),
    "color_hist_heuristic_only_scale": _float_env(
        "PHOTO_PAD_COLOR_HIST_HEURISTIC_ONLY_SCALE", 0.80
    ),
    "color_hist_strong_feature_min": _float_env(
        "PHOTO_PAD_COLOR_HIST_STRONG_FEATURE_MIN", 0.48
    ),
    "color_hist_full_score_features_min": _int_env(
        "PHOTO_PAD_COLOR_HIST_FULL_SCORE_FEATURES_MIN", 3
    ),
    "risk_weight_color_hist": _float_env("PHOTO_PAD_RISK_WEIGHT_COLOR_HIST", 0.10),
    "shield_max_color_hist": _float_env("PHOTO_PAD_SHIELD_MAX_COLOR_HIST", 0.20),
}

CELERY_TASK_QUEUES = (Queue("control_app_queue", routing_key="control_app_queue"),)

CELERY_TASK_ROUTES = {
    "monitoring_app.tasks.*": {
        "queue": "control_app_queue",
        "routing_key": "control_app_queue",
    },
}

BACKUP_DB_WEEKLY_DAY_OF_WEEK = (
    os.getenv("BACKUP_DB_WEEKLY_DAY_OF_WEEK", "1").strip() or "1"
)
BACKUP_DB_WEEKLY_HOUR = min(max(0, _int_env("BACKUP_DB_WEEKLY_HOUR", 3)), 23)
BACKUP_DB_WEEKLY_MINUTE = min(max(0, _int_env("BACKUP_DB_WEEKLY_MINUTE", 30)), 59)
BACKUP_DB_WEEKLY_KEEP_DAYS = max(1, _int_env("BACKUP_DB_WEEKLY_KEEP_DAYS", 30))
BACKUP_DB_WEEKLY_OUTPUT_DIR = (
    os.getenv("BACKUP_DB_WEEKLY_OUTPUT_DIR", "DB").strip() or "DB"
)
BACKUP_DB_WEEKLY_COMPRESS = os.getenv(
    "BACKUP_DB_WEEKLY_COMPRESS", "1"
).strip().lower() in ("1", "true", "yes", "on")
BACKUP_DB_WEEKLY_FORMAT = os.getenv("BACKUP_DB_WEEKLY_FORMAT", "both").strip().lower()
if BACKUP_DB_WEEKLY_FORMAT not in {"json", "sql", "both"}:
    BACKUP_DB_WEEKLY_FORMAT = "both"


def build_celery_beat_schedule(debug: bool) -> dict[str, dict[str, object]]:
    if debug:
        return {}
    return {
        # Weekly snapshot before the first Monday API_URL attendance pull at 04:00.
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
        "get-attendance-every-day-4am": {
            "task": "monitoring_app.tasks.get_all_attendance_task",
            "schedule": crontab(hour="4", minute="0"),
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
        "clean-old-attendance-photos-daily": {
            "task": "monitoring_app.tasks.clean_old_attendance_photos",
            "schedule": crontab(hour="4", minute="30"),
            "kwargs": {"days_old": 62},
        },
        # "augment-images-every-day": {
        #     "task": "monitoring_app.tasks.augment_user_images",
        #     "schedule": crontab(day_of_month="*/3", hour=1, minute=0), #! Disabled no CUDA driver
        # },
    }


CELERY_BEAT_SCHEDULE = build_celery_beat_schedule(DEBUG)

# Logging configurations
LOG_DIR = BASE_DIR / "logs"
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
        "ignore_pylint": {
            "()": "django_settings.logging_filters.IgnorePylintFilter",
        },
        "admin_request_only": {
            "()": "django_settings.logging_filters.AdminRequestFilter",
        },
    },
    "handlers": {
        "admin_errors_file": {
            "class": "django_settings.logging_handlers.SafeTimedRotatingFileHandler",
            "filename": str(LOG_DIR / "admin_errors.log"),
            "when": "H",
            "interval": 1,
            "backupCount": 24 * 14,
            "utc": True,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "standard",
            "level": ADMIN_ERRORS_LEVEL,
            "filters": ["ignore_shutdown", "ignore_pylint", "admin_request_only"],
        },
        "admin_errors_file_no_filter": {
            "class": "django_settings.logging_handlers.SafeTimedRotatingFileHandler",
            "filename": str(LOG_DIR / "admin_errors.log"),
            "when": "H",
            "interval": 1,
            "backupCount": 24 * 14,
            "utc": True,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "standard",
            "level": ADMIN_ERRORS_LEVEL,
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
        "file": {
            "level": "DEBUG" if DEBUG else "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": get_log_filename("log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 24,  # Keep logs for 24 hours
            "encoding": "utf-8",
            "formatter": "verbose",
            "delay": False,
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
        "console": {
            "level": "INFO" if DEBUG else "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
        "lesson_locations_file": {
            "class": "django_settings.logging_handlers.SafeTimedRotatingFileHandler",
            "filename": str(LOG_DIR / "lesson_locations.log"),
            "when": "H",
            "interval": 1,
            "backupCount": 24 * 7,
            "utc": True,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "standard",
            "level": "INFO",
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
        "ws_user_file": {
            "class": "django_settings.logging_handlers.SafeTimedRotatingFileHandler",
            "filename": str(LOG_DIR / "ws_user.log"),
            "when": "H",
            "interval": 1,
            "backupCount": 24 * 7,
            "utc": True,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "standard",
            "level": "INFO",
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
        "lesson_locations_not_found_file": {
            "class": "django_settings.logging_handlers.SafeTimedRotatingFileHandler",
            "filename": str(LOG_DIR / "lesson_locations_not_found.log"),
            "when": "H",
            "interval": 1,
            "backupCount": 24 * 14,
            "utc": True,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "standard",
            "level": "INFO",
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
        "photo_verdict_file": {
            "class": "django_settings.logging_handlers.SafeTimedRotatingFileHandler",
            "filename": str(LOG_DIR / "photo_verdict.log"),
            "when": "H",
            "interval": 1,
            "backupCount": 24 * 14,
            "utc": True,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "standard",
            "level": "INFO",
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
        "face_lab_file": {
            "class": "django_settings.logging_handlers.SafeTimedRotatingFileHandler",
            "filename": str(LOG_DIR / "face_lab.log"),
            "when": "H",
            "interval": 1,
            "backupCount": 24 * 14,
            "utc": True,
            "encoding": "utf-8",
            "delay": True,
            "formatter": "standard",
            "level": "INFO",
            "filters": ["ignore_shutdown", "ignore_pylint"],
        },
    },
    "loggers": {
        "": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": True,
        },
        "django": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app.views": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": True,
        },
        "monitoring_app.lesson_attendance": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app.lesson_locations": {
            "handlers": ["lesson_locations_file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app.lesson_locations.not_found": {
            "handlers": ["lesson_locations_not_found_file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app.photo_verdict": {
            "handlers": ["photo_verdict_file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app.serializers": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": True,
        },
        "monitoring_app.permissions": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": True,
        },
        "monitoring_app.middleware": {
            "handlers": ["file", "console"] if DEBUG else ["file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app.admin": {
            "handlers": ["admin_errors_file_no_filter", "console"],
            "level": MONITORING_ADMIN_LEVEL,
            "propagate": False,
        },
        "monitoring_app.ws_user": {
            "handlers": ["file", "console", "ws_user_file"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "monitoring_app.face_lab": {
            "handlers": ["face_lab_file", "file"] + (["console"] if DEBUG else []),
            "level": "INFO",
            "propagate": False,
        },
    },
}

_django_request_handlers = ["file", "console"] if DEBUG else ["file"]
LOGGING["loggers"]["django.request"] = {
    "handlers": _django_request_handlers,
    "level": "INFO" if DEBUG else "WARNING",
    "propagate": False,
}
LOGGING["loggers"]["django.security.csrf"] = {
    "handlers": _django_request_handlers,
    "level": "WARNING",
    "propagate": False,
}
