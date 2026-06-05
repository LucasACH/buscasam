"""documents.metadata_llm — per-document opt-in for LLM metadata enrichment

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-05

"""

from alembic import op


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE documents "
        "ADD COLUMN metadata_llm boolean NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN metadata_llm")
