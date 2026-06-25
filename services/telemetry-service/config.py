import os


class Config:
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_NAME = os.environ.get("DB_NAME", "")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "root")
    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "")
    S3_CONNECTION_RETRIES = int(os.environ.get("S3_CONNECTION_RETRIES", "3"))
    S3_CONNECTION_TIMEOUT_SECONDS = int(
        os.environ.get("S3_CONNECTION_TIMEOUT_SECONDS", "60")
    )
    # Separate read timeout so a stalled MinIO data transfer fails fast
    # rather than pinning a gunicorn worker for up to the request timeout.
    S3_READ_TIMEOUT_SECONDS = int(os.environ.get("S3_READ_TIMEOUT_SECONDS", "120"))

    # SQLAlchemy connection-pool tuning. pool_pre_ping validates connections
    # before use (prevents stale-connection errors after Postgres restarts).
    # Size is intentionally modest — gunicorn uses sync gthread workers so
    # each worker thread gets its own connection from the pool.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", "10")),
        "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", "1800")),
    }
