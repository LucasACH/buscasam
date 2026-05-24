"""HNSW index on chunks.embedding (ADR-0001 §5)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-24

"""
from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding halfvec_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_hnsw")
