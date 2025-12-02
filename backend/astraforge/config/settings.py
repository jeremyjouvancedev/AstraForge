"""Django settings for AstraForge.

Settings are 12-factor compliant and pull configuration from environment variables. Defaults
are suitable for local development and unit tests only.
"""

from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "unsafe-secret-key"),
    ALLOWED_HOSTS=(list[str], ["*"]),
    DATABASE_URL=(str, "postgres://postgres:postgres@localhost:5433/astraforge"),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    OTEL_EXPORTER_OTLP_ENDPOINT=(str, ""),
    EXECUTOR=(str, "codex"),
    CONNECTOR=(str, "direct_user"),
    VCS_PROVIDER=(str, "gitlab"),
    PROVISIONER=(str, "docker"),
    RUN_LOG_STREAMER=(str, "memory"),
    LLM_PROXY_URL=(str, "http://llm-proxy:8080"),
    LOG_LEVEL=(str, "INFO"),
    REQUEST_REPOSITORY=(str, "database"),
    CSRF_TRUSTED_ORIGINS=(list[str], ["http://localhost:5174", "http://127.0.0.1:5174"]),
)

environ.Env.read_env(
    env_file=os.environ.get("ASTRAFORGE_ENV_FILE", BASE_DIR / ".env"), recurse=False
)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:5174", "http://127.0.0.1:5174"],
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "astraforge.accounts",
    "astraforge.integrations",
    "astraforge.requests",
    "astraforge.interfaces.rest",
    "astraforge.sandbox",
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
]

ROOT_URLCONF = "astraforge.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "astraforge.config.wsgi.application"
ASGI_APPLICATION = "astraforge.config.asgi.application"

DATABASES = {
    "default": env.db(),
}

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

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "astraforge.interfaces.api.authentication.ApiKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

if env.bool("UNSAFE_DISABLE_AUTH", default=False):
    REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
        "astraforge.interfaces.api.authentication.ApiKeyAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ]
    REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = [
        "rest_framework.permissions.AllowAny",
    ]

SPECTACULAR_SETTINGS = {
    "TITLE": "AstraForge API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOW_ALL_ORIGINS = True

LLM_PROXY_URL = env("LLM_PROXY_URL")
LOG_LEVEL = env("LOG_LEVEL")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}

CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_EAGER_PROPAGATES = env.bool("CELERY_TASK_EAGER_PROPAGATES", default=True)
CELERY_TASK_DEFAULT_QUEUE = "astraforge.default"
CELERY_TASK_ROUTES = {
    "astraforge.application.tasks.*": {"queue": "astraforge.core"},
}

PROVIDER_FACTORIES = {
    "executors": {
        "codex": "astraforge.infrastructure.executors.codex:from_env",
        "claude_code": "astraforge.infrastructure.executors.claude:from_env",
        "open_coder": "astraforge.infrastructure.executors.opencoder:from_env",
    },
    "connectors": {
        "direct_user": "astraforge.infrastructure.connectors.base:from_env",
        "jira": "astraforge.infrastructure.connectors.jira:from_env",
        "email": "astraforge.infrastructure.connectors.email:from_env",
        "teams": "astraforge.infrastructure.connectors.teams:from_env",
        "glitchtip": "astraforge.infrastructure.connectors.glitchtip:from_env",
    },
    "vcs": {
        "gitlab": "astraforge.infrastructure.vcs.gitlab:from_env",
        "github": "astraforge.infrastructure.vcs.github:from_env",
    },
    "provisioners": {
        "k8s": "astraforge.infrastructure.provisioners.k8s:from_env",
    },
}


IMPLEMENTATION_CACHE: dict[tuple[str, str], object] = {}


def load_factory(target: str):
    module_path, attr = target.split(":", 1)
    module = import_module(module_path)
    factory = getattr(module, attr)
    return factory


def resolve_provider(kind: str, key: str, *args, **kwargs):
    cache_key = (kind, key)
    if cache_key in IMPLEMENTATION_CACHE:
        return IMPLEMENTATION_CACHE[cache_key]
    mapping = PROVIDER_FACTORIES[kind]
    factory = load_factory(mapping[key])
    instance = factory(*args, **kwargs)
    IMPLEMENTATION_CACHE[cache_key] = instance
    return instance


def EXECUTOR_FACTORY(key: str):
    return resolve_provider("executors", key)


# Observability defaults; exporters activated when endpoint is configured.
OTEL_EXPORTER_OTLP_ENDPOINT = env("OTEL_EXPORTER_OTLP_ENDPOINT")
EXECUTOR_PROVIDER = env("EXECUTOR")
CONNECTOR_PROVIDER = env("CONNECTOR")
VCS_PROVIDER = env("VCS_PROVIDER")
PROVISIONER = env("PROVISIONER")
PROVISIONER_PROVIDER = PROVISIONER
RUN_LOG_STREAMER = env("RUN_LOG_STREAMER")
