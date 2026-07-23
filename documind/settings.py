"""
DocuMind AI - Django settings
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------
# Security
# -----------------------------------------------------------------------------

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "change-this-secret-key"
)

DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"

ALLOWED_HOSTS = os.getenv(
    "DJANGO_ALLOWED_HOSTS",
    "127.0.0.1,localhost"
).split(",")

# -----------------------------------------------------------------------------
# Installed Apps
# -----------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.staticfiles",

    "core",
    "accounts",
    "documents",
    "chat",
]

# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.middleware.common.CommonMiddleware",

    "core.middleware.CorsMiddleware",
]

# -----------------------------------------------------------------------------
# URLs
# -----------------------------------------------------------------------------

ROOT_URLCONF = "documind.urls"

# -----------------------------------------------------------------------------
# Templates
# -----------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates"
        ],

        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

# -----------------------------------------------------------------------------
# WSGI
# -----------------------------------------------------------------------------

WSGI_APPLICATION = "documind.wsgi.application"

# -----------------------------------------------------------------------------
# Dummy SQL DB (Required by Django)
# -----------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "unused_django_core.sqlite3",
    }
}

# -----------------------------------------------------------------------------
# Internationalization
# -----------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------------------------------------------
# Static Files
# -----------------------------------------------------------------------------

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static"
]

STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }
}

# -----------------------------------------------------------------------------
# Media Files
# -----------------------------------------------------------------------------

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

os.makedirs(MEDIA_ROOT, exist_ok=True)

# -----------------------------------------------------------------------------
# MongoDB
# -----------------------------------------------------------------------------

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017"
)

MONGO_DB_NAME = os.getenv(
    "MONGO_DB_NAME",
    "documind_ai"
)

MONGO_USE_MOCK = os.getenv(
    "MONGO_USE_MOCK",
    "False"
) == "True"

# -----------------------------------------------------------------------------
# Groq
# -----------------------------------------------------------------------------

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    ""
)

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)

# -----------------------------------------------------------------------------
# Embeddings
# -----------------------------------------------------------------------------

EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME",
    "intfloat/e5-base-v2"
)

EMBEDDING_DIM = int(
    os.getenv("EMBEDDING_DIM", "768")
)

# -----------------------------------------------------------------------------
# RAG
# -----------------------------------------------------------------------------

RAG_CHUNK_SIZE_TOKENS = int(
    os.getenv("RAG_CHUNK_SIZE_TOKENS", "500")
)

RAG_CHUNK_OVERLAP_TOKENS = int(
    os.getenv("RAG_CHUNK_OVERLAP_TOKENS", "50")
)

RAG_TOP_K = int(
    os.getenv("RAG_TOP_K", "8")
)

RAG_MMR_LAMBDA = float(
    os.getenv("RAG_MMR_LAMBDA", "0.5")
)

RAG_MIN_SIMILARITY = float(
    os.getenv("RAG_MIN_SIMILARITY", "0.30")
)

# -----------------------------------------------------------------------------
# Upload
# -----------------------------------------------------------------------------

MAX_UPLOAD_SIZE_MB = int(
    os.getenv("MAX_UPLOAD_SIZE_MB", "100")
)

# -----------------------------------------------------------------------------
# CORS
# -----------------------------------------------------------------------------

CORS_ALLOWED_ORIGIN = os.getenv(
    "CORS_ALLOWED_ORIGIN",
    "*"
)

# -----------------------------------------------------------------------------
# Production Security
# -----------------------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https"
)

SESSION_COOKIE_SECURE = not DEBUG

CSRF_COOKIE_SECURE = not DEBUG