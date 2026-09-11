"""Structured product and BOM master.

Revision ID: 0054_northstar_manufacturing_master
Revises: 0053_v2_operational_scope
"""
from alembic import op
from app.db.models import ManufacturingBOMLine, ManufacturingProduct

revision="0054_northstar_manufacturing_master"
down_revision="0053_v2_operational_scope"
branch_labels=None
depends_on=None


def upgrade() -> None:
    ManufacturingProduct.__table__.create(bind=op.get_bind(), checkfirst=True)
    ManufacturingBOMLine.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    ManufacturingBOMLine.__table__.drop(bind=op.get_bind(), checkfirst=True)
    ManufacturingProduct.__table__.drop(bind=op.get_bind(), checkfirst=True)
