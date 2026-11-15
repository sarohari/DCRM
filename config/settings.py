"""Django settings for the Duroflex CRM."""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", default=True)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
DEVELOPMENT_SECRET = "local-development-only-change-before-deploying"
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = DEVELOPMENT_SECRET
    else:
        raise RuntimeError("Set DJANGO_SECRET_KEY when DJANGO_DEBUG is false.")

raw_allowed_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS")
ALLOWED_HOSTS = ['*']

if not DEBUG:
    if SECRET_KEY == DEVELOPMENT_SECRET:
        raise RuntimeError("DJANGO_SECRET_KEY must not use the development placeholder in production.")
    if not raw_allowed_hosts or not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise RuntimeError("Set explicit DJANGO_ALLOWED_HOSTS values for production.")
    configured_db_engine = os.environ.get("DB_ENGINE", "sqlite").strip().lower()
    if configured_db_engine not in {"sqlite", "postgres", "postgresql"}:
        raise RuntimeError("DB_ENGINE must be sqlite or postgres.")
    if configured_db_engine == "sqlite":
        sqlite_path = os.environ.get("DJANGO_SQLITE_PATH", "").strip()
        if not sqlite_path or not Path(sqlite_path).is_absolute():
            raise RuntimeError("Set DJANGO_SQLITE_PATH to an absolute persistent file path in production.")


INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts.apps.AccountsConfig",
    "tenancy.apps.TenancyConfig",
    "core.apps.CoreConfig",
    "leads.apps.LeadsConfig",
    "followups.apps.FollowupsConfig",
    "sales.apps.SalesConfig",
]

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrPhoneBackend"]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SessionPolicyMiddleware",
    "core.middleware.SafeRequestLoggingMiddleware",
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
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.environ.get("DB_ENGINE", "sqlite").strip().lower() in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "duroflex_crm"),
            "USER": os.environ.get("DB_USER", "duroflex_crm"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            # Production hosts must point this at a persistent writable path.
            # The repository-local default keeps local development unchanged.
            "NAME": os.environ.get("DJANGO_SQLITE_PATH", str(BASE_DIR / "local.sqlite3")),
            "OPTIONS": {
                "timeout": int(os.environ.get("DJANGO_SQLITE_TIMEOUT", "20")),
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 12 * 60 * 60
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env_bool("DJANGO_TRUST_PROXY_SSL_HEADER", default=False)
    else None
)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "privacy_safe": {
            "format": "%(levelname)s request_id=%(request_id)s route=%(route)s method=%(method)s status=%(status_code)s duration_ms=%(duration_ms)s %(message)s",
        },
    },
    "handlers": {
        "privacy_safe_console": {
            "class": "logging.StreamHandler",
            "formatter": "privacy_safe",
        },
    },
    "loggers": {
        "core.http": {
            "handlers": ["privacy_safe_console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
