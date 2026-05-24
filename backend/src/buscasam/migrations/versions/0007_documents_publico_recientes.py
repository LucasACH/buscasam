"""partial btree supporting orden=recientes for invitado branch (ADR-0001 §11)

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-24

"""
from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX documents_publico_recientes
        ON documents (fecha DESC)
        WHERE visibility = 'publico'
          AND publication_status = 'published'
          AND soft_deleted_at IS NULL
          AND moderation_hidden_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_publico_recientes")
