"""Membership operational scopes.

Revision ID: 0053_v2_operational_scope
Revises: 0052_v2_integration_ingestion
"""
from alembic import op
from app.db.models import OperationalScope

revision = "0053_v2_operational_scope"
down_revision = "0052_v2_integration_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    OperationalScope.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    OperationalScope.__table__.drop(bind=op.get_bind(), checkfirst=True)
