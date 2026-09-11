import os
import tempfile

os.environ.setdefault("APP_ENV", "test")
_test_database_dir = tempfile.TemporaryDirectory(prefix="genuinegigs-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_database_dir.name}/test.db"
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("AGENT_ENABLED", "true")
# Tests use the private local-storage fallback. Developer `.env` credentials
# must never make a unit test depend on a running MinIO/S3 service.
os.environ["OBJECT_STORAGE_ACCESS_KEY"] = ""
os.environ["OBJECT_STORAGE_SECRET_KEY"] = ""
# Unit and service tests must not call a developer's live model account.
# Provider-selection tests monkeypatch the typed provider boundary explicitly;
# live Groq is an environment acceptance gate, not a unit-test dependency.
os.environ["GROQ_API_KEY"] = ""
os.environ["LLAMA_CLOUD_API_KEY"] = ""
os.environ["UPLOAD_DIR"] = "/tmp/genuinegigs-test-uploads"

from app.db.models import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402


@event.listens_for(Engine, "connect")
def configure_ephemeral_test_database(connection, _record):
    # Test databases are disposable. Avoid thousands of fsyncs when the full
    # metadata is created; production database settings are never changed.
    import sqlite3
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA synchronous=OFF")

with engine.begin() as connection:
    if engine.dialect.name == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=OFF"))
    Base.metadata.drop_all(bind=connection)
    Base.metadata.create_all(bind=connection)
    if engine.dialect.name == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=ON"))
