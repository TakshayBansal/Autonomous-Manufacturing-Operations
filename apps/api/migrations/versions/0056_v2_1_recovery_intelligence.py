"""V2.1 operational recovery intelligence.

Revision ID: 0056_v2_1_recovery_intelligence
Revises: 0055_machine_signal_samples
"""
from alembic import op

from app.db.models import (
    ForecastEvaluation,
    ImprovementInvestigation,
    OperationalStateSnapshot,
    RecoveryCase,
    RecoveryOutcome,
    RecoveryStrategy,
    RecoveryStrategyAction,
)

revision = "0056_v2_1_recovery_intelligence"
down_revision = "0055_machine_signal_samples"
branch_labels = None
depends_on = None


TABLES = (
    OperationalStateSnapshot,
    RecoveryCase,
    RecoveryStrategy,
    RecoveryStrategyAction,
    RecoveryOutcome,
    ImprovementInvestigation,
    ForecastEvaluation,
)


def upgrade():
    bind = op.get_bind()
    for model in TABLES:
        model.__table__.create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for model in reversed(TABLES):
        model.__table__.drop(bind=bind, checkfirst=True)
