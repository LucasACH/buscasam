"""GIN index on chunks.body_tsv (ADR-0001 §10)

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-24

"""
from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX chunks_body_tsv_gin ON chunks USING gin (body_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_body_tsv_gin")
