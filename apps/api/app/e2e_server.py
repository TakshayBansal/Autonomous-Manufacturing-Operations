import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./genuinegigs_e2e.db")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("AGENT_ENABLED", "true")
os.environ.setdefault("V2_SIMULATION_PASSWORD", "Northstar@2026")
os.environ.setdefault("FACTORY_SIMULATOR_URL", "http://127.0.0.1:8090")

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.db.seed import reset_workspace_database
from app.db.seed_v2_simulation import seed_northstar
from app.db.session import engine


def main() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    with Session(engine) as db:
        reset_workspace_database(db)
        seed_northstar(db, reset=True)
        db.commit()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
