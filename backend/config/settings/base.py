"""Impostazioni comuni a tutti gli ambienti."""

from __future__ import annotations

from pathlib import Path

from config.env import env, env_bool, env_int, env_list, load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BASE_DIR.parent

load_dotenv(REPO_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # terze parti
    "rest_framework",
    "django_filters",
    "corsheaders",
    "simple_history",
    "drf_spectacular",
    # applicazioni di dominio
    "core",
    "directory",
    "projects",
    "canone",
    "wallet",
    "timesheets",
    "ppm",
    "anomalies",
    "imports",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "core.middleware.CurrentUserMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "supplier_ledger"),
        "USER": env("POSTGRES_USER", "supplier_ledger"),
        "PASSWORD": env("POSTGRES_PASSWORD", "supplier_ledger"),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autenticazione -------------------------------------------------------
# v1: solo sessione locale. L'astrazione in core.auth.providers è pronta per
# Microsoft Entra ID (OIDC) ma non attiva.
AUTH_PROVIDER = env("AUTH_PROVIDER", "local")
LOGIN_URL = "/admin/login/"
SESSION_COOKIE_NAME = "sl_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 8)
CSRF_COOKIE_NAME = "sl_csrftoken"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:8080")

# --- Upload ---------------------------------------------------------------
MAX_UPLOAD_BYTES = env_int("MAX_UPLOAD_BYTES", 25 * 1024 * 1024)
ALLOWED_UPLOAD_EXTENSIONS = [".json", ".xlsx", ".pdf"]
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES

# --- DRF ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # I Decimal viaggiano come stringhe, anche fuori dai serializer (vedi api/renderers.py).
    "DEFAULT_RENDERER_CLASSES": ["api.renderers.DaysJSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "api.pagination.StandardCursorPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "core.exceptions.problem_detail_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"login": env("LOGIN_THROTTLE_RATE", "10/min")},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Supplier Ledger API",
    "DESCRIPTION": "Consuntivazione, wallet e canone del fornitore Imola Informatica.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Dominio --------------------------------------------------------------
DAYS_DECIMAL_PLACES = 4
DISPLAY_DECIMAL_PLACES = 2
RESIDUAL_EXPIRING_WINDOW_DAYS = env_int("RESIDUAL_EXPIRING_WINDOW_DAYS", 90)

# --- Seed files -----------------------------------------------------------
_seed_in_app = Path("/app/data/seed/seed_imola_2026-10-16.json")
_seed_in_repo = REPO_DIR / "data" / "seed" / "seed_imola_2026-10-16.json"
_seed_in_base = BASE_DIR / "data" / "seed" / "seed_imola_2026-10-16.json"
_default_seed_path = (
    str(_seed_in_app)
    if _seed_in_app.parent.exists()
    else str(_seed_in_base if _seed_in_base.parent.exists() else _seed_in_repo)
)
SEED_FILE = Path(env("SEED_FILE", _default_seed_path))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "stdout": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["stdout"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["stdout"], "propagate": False},
    },
}
