# settings_bootstrap.py
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "quotation_models"
MIGR_DIR = APP_DIR / "migrations"

def ensure_local_app():
    APP_DIR.mkdir(exist_ok=True)
    MIGR_DIR.mkdir(exist_ok=True)
    (APP_DIR / "__init__.py").write_text("", encoding="utf-8") if not (APP_DIR / "__init__.py").exists() else None
    if not (APP_DIR / "apps.py").exists():
        (APP_DIR / "apps.py").write_text(
            "from django.apps import AppConfig\n"
            "class QuotationModelsConfig(AppConfig):\n"
            "    default_auto_field = 'django.db.models.AutoField'\n"
            "    name = 'quotation_models'\n", encoding="utf-8"
        )
    (MIGR_DIR / "__init__.py").write_text("", encoding="utf-8") if not (MIGR_DIR / "__init__.py").exists() else None

def configure_django():
    from django.conf import settings
    ensure_local_app()
    DB_PATH = BASE_DIR / "quotation_app.sqlite3"
    MEDIA_ROOT = BASE_DIR / "media"
    MEDIA_ROOT.mkdir(exist_ok=True)

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            SECRET_KEY="quotation-app-secret-key",
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "quotation_models",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": str(DB_PATH),
                }
            },
            DEFAULT_AUTO_FIELD="django.db.models.AutoField",
            TIME_ZONE="Asia/Kolkata",
            USE_TZ=False,
            MEDIA_ROOT=str(MEDIA_ROOT),
            MEDIA_URL="/media/",
        )
