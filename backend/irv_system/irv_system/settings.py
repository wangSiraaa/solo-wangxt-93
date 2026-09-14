"""
Django 设置。数据库默认使用 PostgreSQL（见 README），
可用环境变量 DATABASE_URL / 各 PG* 变量覆盖；未配置时回退 SQLite 以便单测。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("必须设置 DJANGO_SECRET_KEY 后再启动 Django")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "corsheaders",
    "irv",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "irv_system.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "irv_system.wsgi.application"


def _database_config():
    # 显式声明使用 SQLite（仅用于无 PG 的本地快速测试）
    if os.environ.get("USE_SQLITE") == "1":
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "test_db.sqlite3"}

    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        import re
        m = re.match(
            r"postgres(?:ql)?://(?P<user>[^:]+):(?P<pw>[^@]*)@(?P<host>[^:/>]+)"
            r"(?::(?P<port>\d+))?/(?P<name>[^?]+)", db_url)
        if not m:
            raise ValueError(f"无法解析 DATABASE_URL: {db_url}")
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": m.group("name"),
            "USER": m.group("user"),
            "PASSWORD": m.group("pw"),
            "HOST": m.group("host"),
            "PORT": m.group("port") or "5432",
        }

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PGDATABASE", "irv"),
        "USER": os.environ.get("PGUSER", "postgres"),
        "PASSWORD": os.environ.get("PGPASSWORD", ""),
        "HOST": os.environ.get("PGHOST", "/tmp"),
        "PORT": os.environ.get("PGPORT", "5432"),
    }


DATABASES = {"default": _database_config()}

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}
