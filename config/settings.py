from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if SECRET_KEY == "replace-with-a-random-secret-key":
    raise ImproperlyConfigured("Generer DJANGO_SECRET_KEY dans .env avant le lancement.")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "web"])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.semantic",
    "apps.backoffice",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
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
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": env("POSTGRES_DB"),
    "USER": env("POSTGRES_USER"),
    "PASSWORD": env("POSTGRES_PASSWORD"),
    "HOST": env("POSTGRES_HOST", default="db"),
    "PORT": 5432,
    "CONN_MAX_AGE": 60,
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {"connect_timeout": 5},
}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE", default="fr")
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Africa/Tunis")
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(env("DJANGO_STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("DJANGO_MEDIA_ROOT", default=str(BASE_DIR / "media")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

FUSEKI_BASE_URL = env("FUSEKI_BASE_URL", default="http://fuseki:3030").rstrip("/")
FUSEKI_DATASET = env("FUSEKI_DATASET", default="education")
FUSEKI_DATASET_URL = f"{FUSEKI_BASE_URL}/{FUSEKI_DATASET}"
FUSEKI_TIMEOUT_SECONDS = env.float("FUSEKI_TIMEOUT_SECONDS", default=5)
SEMANTIC_NAMESPACE = env("SEMANTIC_NAMESPACE", default="https://example.org/education#")

GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL", default="gemini-3.8-flash")
GEMINI_TIMEOUT_SECONDS = env.float("GEMINI_TIMEOUT_SECONDS", default=30)

LOGIN_URL = "backoffice:login"
LOGIN_REDIRECT_URL = "backoffice:dashboard"
LOGOUT_REDIRECT_URL = "backoffice:login"
PDF_UPLOAD_MAX_MB = env.int("PDF_UPLOAD_MAX_MB", default=20)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

