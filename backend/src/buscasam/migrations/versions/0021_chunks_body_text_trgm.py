"""pg_trgm + GIN trigram index on chunks.body_text (fuzzy fallback)

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-31

"""
from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX chunks_body_text_trgm "
        "ON chunks USING gin (body_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_body_text_trgm")
