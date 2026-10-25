"""
Settings for the Nexora School Office system.

It runs only on this computer (http://127.0.0.1:8000) and keeps every record
in one file: db.sqlite3 in this folder. Photos and the logo go in "media".
"""
from pathlib import Path

import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Where the records live. Desktop: this folder (db.sqlite3 + media). The online demo sets
# SCHOOL_DATA_DIR so its fictional data is kept apart from the program files.
DATA_DIR = Path(os.environ["SCHOOL_DATA_DIR"]) if os.environ.get("SCHOOL_DATA_DIR") else BASE_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Admission numbers look like NMS-2026-0001.
ADMISSION_PREFIX = os.environ.get("SCHOOL_ADMISSION_PREFIX", "NMS").upper()

# Public online demo (portfolio): OFF unless SCHOOL_DEMO=1. Fictional data only, one-click
# sign-in, rebuilt automatically every DEMO_RESET_HOURS. Never used on the office computer.
DEMO_MODE = os.environ.get("SCHOOL_DEMO") == "1"
DEMO_RESET_HOURS = float(os.environ.get("SCHOOL_DEMO_RESET_HOURS", "24"))

# A secret used to sign the login cookie. Created on first run and kept in secret_key.txt.
_key_file = DATA_DIR / "secret_key.txt"
if not _key_file.exists():
    import secrets

    _key_file.write_text(secrets.token_urlsafe(50), encoding="utf-8")
SECRET_KEY = _key_file.read_text(encoding="utf-8").strip()

# Office use on one computer only. DEBUG stays off so mistakes show a friendly page.
DEBUG = (BASE_DIR / "debug.on").exists()
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
_extra_hosts = [h.strip() for h in os.environ.get("SCHOOL_ALLOWED_HOSTS", "").split(",") if h.strip()]
ALLOWED_HOSTS += _extra_hosts
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in _extra_hosts]
if os.environ.get("SCHOOL_HTTPS") == "1":  # online demo behind HTTPS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "office",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "office.demo.DemoMiddleware",
    "office.middleware.AdminOnlyMiddleware",
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
                "office.context_processors.school",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
]

LOGIN_URL = "office:login"

# Closing the window logs you out; also log out after 4 hours idle.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 4
SESSION_SAVE_EVERY_REQUEST = True

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = False
USE_TZ = True
USE_THOUSAND_SEPARATOR = False

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = DATA_DIR / "media"
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000  # big mark sheets

MESSAGE_TAGS = {40: "danger"}
