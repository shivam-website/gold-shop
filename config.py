import os

# Absolute path of the folder containing config.py
BASEDIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Secret key for sessions and CSRF
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    
    # Database URI: PostgreSQL on Render or fallback to SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASEDIR, 'instance', 'goldshop.db')}"
    )
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Optional: set pool size / timeout for PostgreSQL
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 5)),
        "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", 30)),
    }

    # Absolute path to uploads folder
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASEDIR, "uploads"))
    
    # Upload constraints
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Optional: log SQL queries (useful for debugging)
    SQLALCHEMY_ECHO = True
