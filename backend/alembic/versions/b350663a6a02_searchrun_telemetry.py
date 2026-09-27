"""searchrun_telemetry

Revision ID: b350663a6a02
Revises: 14d808ce98a3
Create Date: 2026-09-27 01:39:09.098249

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b350663a6a02'
down_revision: Union[str, None] = '14d808ce98a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE search_runs ADD COLUMN IF NOT EXISTS lock_skipped INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE search_runs ADD COLUMN IF NOT EXISTS provider_zero_results JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE search_runs ADD COLUMN IF NOT EXISTS provider_failures JSONB NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE search_runs DROP COLUMN IF EXISTS provider_failures")
    op.execute("ALTER TABLE search_runs DROP COLUMN IF EXISTS provider_zero_results")
    op.execute("ALTER TABLE search_runs DROP COLUMN IF EXISTS lock_skipped")
