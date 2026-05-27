"""documents.keywords + documents.published_at for the publish transaction

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-27

"""
from alembic import op


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # publish copies staged_keywords into documents.keywords and stamps the
    # publish moment so /mis-trabajos can render it (module map §core/documents).
    op.execute("ALTER TABLE documents ADD COLUMN keywords text[]")
    op.execute("ALTER TABLE documents ADD COLUMN published_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS published_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS keywords")
