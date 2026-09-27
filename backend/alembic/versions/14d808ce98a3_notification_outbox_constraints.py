"""notification_outbox_constraints

Revision ID: 14d808ce98a3
Revises: baeffd94ede2
Create Date: 2026-09-27 01:34:17.394552

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14d808ce98a3'
down_revision: Union[str, None] = 'baeffd94ede2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotente: bancos novos já têm via initial_schema; bancos antigos
    # restaurados via lightweight precisam destes. Usa blocos DO para
    # não falhar se já existirem.
    op.execute("""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_notifications_logical') THEN
            ALTER TABLE notifications ADD CONSTRAINT uq_notifications_logical UNIQUE (user_id, job_id, channel, event_type);
        END IF;
    END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_notif_outbox ON notifications (status, next_attempt_at)")
    # Garante colunas do outbox em bancos antigos (redundante com lightweight, mas seguro)
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS event_type VARCHAR(32) NOT NULL DEFAULT 'new_match'")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute("ALTER TABLE job_matches ADD COLUMN IF NOT EXISTS recency_score INTEGER NOT NULL DEFAULT 0")
    # Limpa índice único legado criado pela revisão anterior (se existir),
    # já que a garantia canônica agora é a CONSTRAINT acima.
    # Não toca se o nome já pertence a uma constraint (caso fresh DB).
    op.execute("""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'uq_notifications_logical' AND relkind = 'i')
           AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_notifications_logical') THEN
            DROP INDEX uq_notifications_logical;
        END IF;
    END $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notif_outbox")
    op.execute("DROP INDEX IF EXISTS uq_notifications_logical")
