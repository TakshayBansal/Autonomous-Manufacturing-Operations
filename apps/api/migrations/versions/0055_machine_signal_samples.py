"""Raw machine signal samples.

Revision ID: 0055_machine_signal_samples
Revises: 0054_northstar_manufacturing_master
"""
from alembic import op
from app.db.models import MachineSignalSample

revision="0055_machine_signal_samples"
down_revision="0054_northstar_manufacturing_master"
branch_labels=None
depends_on=None

def upgrade(): MachineSignalSample.__table__.create(bind=op.get_bind(),checkfirst=True)
def downgrade(): MachineSignalSample.__table__.drop(bind=op.get_bind(),checkfirst=True)
