"""Supply-chain planning and control-tower module."""

# Import ORM declarations whenever the package is loaded so the shared
# SQLAlchemy metadata used by tests and Alembic includes the SCM tables.
from app.scm import models as models  # noqa: F401

