"""document_versions immutable generated-metadata snapshot (issue #94)

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-29

"""
from alembic import op


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Immutable per-version snapshot of the extractor's generated metadata,
    # written once at index completion alongside staged_* and never overwritten
    # by author edits, so any field can be reverted to what the extractor
    # produced. Mirrors the staged_* column types.
    op.execute("ALTER TABLE document_versions ADD COLUMN generated_abstract text")
    op.execute("ALTER TABLE document_versions ADD COLUMN generated_keywords text[]")
    op.execute("ALTER TABLE document_versions ADD COLUMN generated_fecha date")


def downgrade() -> None:
    op.execute("ALTER TABLE document_versions DROP COLUMN generated_fecha")
    op.execute("ALTER TABLE document_versions DROP COLUMN generated_keywords")
    op.execute("ALTER TABLE document_versions DROP COLUMN generated_abstract")
