"""document_versions index_stage progress checkpoint

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-30

"""
from alembic import op


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sub-stage of the 'processing' index_status, written by the worker as it
    # crosses each pipeline boundary (reading/ocr/summarizing/analyzing/indexing)
    # so the editar UI can show real progress checkpoints instead of one spinner.
    # NULL outside of processing; never a publish gate — purely informational.
    op.execute("ALTER TABLE document_versions ADD COLUMN index_stage text")


def downgrade() -> None:
    op.execute("ALTER TABLE document_versions DROP COLUMN index_stage")
