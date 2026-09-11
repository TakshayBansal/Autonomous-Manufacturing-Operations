from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.session import engine
from app.platform.demos import seed_demo_workspaces


REQUIRED_TABLES = {
    "platform_materials",
    "external_entity_references",
    "platform_action_intents",
    "platform_action_outcomes",
}


def ensure_platform_schema() -> None:
    """Bring the database to the code's migration head before adding fixtures.

    Compose one-shot containers can otherwise reuse an old ``migrate`` image
    while building a newer seed image. Alembic upgrades are idempotent, making
    this safe both after the normal migrate service and as a standalone seed.
    """
    api_root = Path(__file__).resolve().parents[2]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "migrations"))
    command.upgrade(config, "head")
    missing = REQUIRED_TABLES - set(inspect(engine).get_table_names())
    if missing:
        raise RuntimeError(f"Platform schema bootstrap incomplete; missing tables: {sorted(missing)}")


def main() -> None:
    ensure_platform_schema()
    with Session(engine) as db:
        result = seed_demo_workspaces(db)
        db.commit()
    print(f"Platform demo workspaces seeded: {result}")


if __name__ == "__main__":
    main()
