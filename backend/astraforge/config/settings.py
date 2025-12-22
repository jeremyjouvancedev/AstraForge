"""Django settings for AstraForge.

Settings are 12-factor compliant and pull configuration from environment variables. Defaults
are suitable for local development and unit tests only.
"""

from __future__ import annotations

import json
import os
from importlib import import_module
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIST = BASE_DIR / "frontend_dist"

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
    AUTH_REQUIRE_APPROVAL=(bool, True),
    AUTH_ALLOW_ALL_USERS=(bool, False),
    EMAIL_BACKEND=(str, "django.core.mail.backends.smtp.EmailBackend"),
    EMAIL_HOST=(str, ""),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_USE_SSL=(bool, False),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    DEFAULT_FROM_EMAIL=(str, "AstraForge <noreply@astraforge.dev>"),
    EARLY_ACCESS_NOTIFICATION_EMAIL=(str, ""),
    SELF_HOSTED=(bool, False),
    WORKSPACE_QUOTAS_ENABLED=(bool, True),
    WORKSPACE_QUOTAS=(str, ""),
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
AUTH_REQUIRE_APPROVAL = env.bool("AUTH_REQUIRE_APPROVAL", default=True)
AUTH_ALLOW_ALL_USERS = env.bool("AUTH_ALLOW_ALL_USERS", default=False)
AUTH_WAITLIST_ENABLED = AUTH_REQUIRE_APPROVAL and not AUTH_ALLOW_ALL_USERS

EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS")
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
EARLY_ACCESS_NOTIFICATION_EMAIL = env("EARLY_ACCESS_NOTIFICATION_EMAIL")
SELF_HOSTED = env.bool("SELF_HOSTED", default=False)
WORKSPACE_QUOTAS_ENABLED = env.bool(
    "WORKSPACE_QUOTAS_ENABLED",
    default=not SELF_HOSTED,
)

_DEFAULT_WORKSPACE_PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "trial": {
        "requests_per_month": 50,
        "sandbox_sessions_per_month": 20,
        "sandbox_concurrent": 1,
    },
    "pro": {
        "requests_per_month": 500,
        "sandbox_sessions_per_month": 200,
        "sandbox_concurrent": 3,
    },
    "enterprise": {
        "requests_per_month": 2000,
        "sandbox_sessions_per_month": 1000,
        "sandbox_concurrent": 10,
    },
    "self_hosted": {
        "requests_per_month": None,
        "sandbox_sessions_per_month": None,
        "sandbox_concurrent": None,
    },
}
_WORKSPACE_PLAN_LIMITS_RAW = env("WORKSPACE_QUOTAS", default="").strip()
if _WORKSPACE_PLAN_LIMITS_RAW:
    try:
        _WORKSPACE_PLAN_LIMITS_OVERRIDE = json.loads(_WORKSPACE_PLAN_LIMITS_RAW)
    except json.JSONDecodeError as exc:  # pragma: no cover - invalid operator input
        raise ImproperlyConfigured("WORKSPACE_QUOTAS must be valid JSON") from exc
else:
    _WORKSPACE_PLAN_LIMITS_OVERRIDE = {}


def _merge_plan_limits(
    defaults: dict[str, dict[str, int | None]],
    overrides: dict[str, dict[str, object]],
) -> dict[str, dict[str, int | None]]:
    merged: dict[str, dict[str, int | None]] = {
        key: dict(value) for key, value in defaults.items()
    }
    for plan, values in overrides.items():
        if not isinstance(values, dict):
            continue
        plan_key = str(plan)
        plan_limits = merged.setdefault(plan_key, {})
        for limit_key, limit_value in values.items():
            plan_limits[limit_key] = limit_value  # type: ignore[assignment]
    return merged


WORKSPACE_PLAN_LIMITS = _merge_plan_limits(
    _DEFAULT_WORKSPACE_PLAN_LIMITS, _WORKSPACE_PLAN_LIMITS_OVERRIDE
)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured(
        "EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled."
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
    "astraforge.quotas",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "astraforge.interfaces.api.middleware.ApiKeyCsrfBypassMiddleware",
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

STATIC_URL = "/assets/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [FRONTEND_DIST / "assets"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
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
SANDBOX_REAP_INTERVAL_SEC = env.int("SANDBOX_REAP_INTERVAL_SEC", default=60)
CELERY_BEAT_SCHEDULE = {
    "reap-sandbox-sessions": {
        "task": "astraforge.sandbox.tasks.reap_sandboxes",
        "schedule": SANDBOX_REAP_INTERVAL_SEC,
    },
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
