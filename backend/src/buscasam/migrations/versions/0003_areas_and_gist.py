"""áreas reference table + GiST on documents.area_path (ADR-0001 §7)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-24

"""
from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE areas (
          area_path     ltree PRIMARY KEY,
          display_name  text  NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX documents_area_path_gist "
        "ON documents USING gist (area_path)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_area_path_gist")
    op.execute("DROP TABLE IF EXISTS areas")
