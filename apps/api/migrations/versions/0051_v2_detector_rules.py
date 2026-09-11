"""Add governed plant detector configuration.

Revision ID: 0051_v2_detector_rules
Revises: 0050_v2_action_dependencies
"""
from alembic import op
from app.db.models import Base

revision = "0051_v2_detector_rules"
down_revision = "0050_v2_action_dependencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["operational_detector_rules"].create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.tables["operational_detector_rules"].drop(op.get_bind(), checkfirst=True)
