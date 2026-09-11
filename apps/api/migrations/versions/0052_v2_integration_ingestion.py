"""V2 connector ingestion lineage and idempotency receipts.

Revision ID: 0052_v2_integration_ingestion
Revises: 0051_v2_detector_rules
"""
from alembic import op
from app.db.models import IntegrationIngestionRecord

revision = "0052_v2_integration_ingestion"
down_revision = "0051_v2_detector_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    IntegrationIngestionRecord.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    IntegrationIngestionRecord.__table__.drop(bind=op.get_bind(), checkfirst=True)
