"""minimal documents table for invitado access predicate

Revision ID: 0001
Revises:
Create Date: 2026-05-24

"""
from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("visibility", sa.Text, nullable=False),
        sa.Column("publication_status", sa.Text, nullable=False),
        sa.Column("soft_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderation_hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "visibility IN ('publico', 'interno', 'privado')",
            name="documents_visibility_check",
        ),
        sa.CheckConstraint(
            "publication_status IN ('draft', 'published')",
            name="documents_publication_status_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("documents")
