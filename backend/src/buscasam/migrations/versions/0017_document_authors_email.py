"""document_authors.email for external authors (ADR-0010 §5)

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-29

"""
from alembic import op


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_authors ADD COLUMN email text")


def downgrade() -> None:
    op.execute("ALTER TABLE document_authors DROP COLUMN email")
