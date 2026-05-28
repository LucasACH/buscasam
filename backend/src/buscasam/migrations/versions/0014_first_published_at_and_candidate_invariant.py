"""document_versions.first_published_at + at-most-one-candidate partial unique
index + 'discarded' index_status value (ADR-0011 §2/§3, module map §schema).

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-27

"""
from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE document_versions ADD COLUMN first_published_at timestamptz"
    )
    # Backfill: existing is_current=true rows were public at some point. Use
    # uploaded_at as a best-effort proxy on the small corpus (ADR-0011 §3).
    op.execute(
        "UPDATE document_versions SET first_published_at = uploaded_at "
        "WHERE is_current = true"
    )

    # Admit the 'discarded' terminal state in the existing CHECK constraint.
    op.execute(
        "ALTER TABLE document_versions "
        "DROP CONSTRAINT document_versions_index_status_check"
    )
    op.execute(
        "ALTER TABLE document_versions "
        "ADD CONSTRAINT document_versions_index_status_check "
        "CHECK (index_status IN ('pending', 'processing', 'indexed', 'failed', 'discarded'))"
    )

    # ADR-0011 §2: at most one non-current, non-discarded candidate per document.
    # `first_published_at IS NULL` scopes the invariant to never-public rows:
    # without it the predicate also matches previously-published historical
    # versions (is_current=false, index_status='indexed') that publish leaves
    # behind on a replacement, breaking the atomic current-flip.
    op.execute(
        "CREATE UNIQUE INDEX document_versions_one_candidate "
        "ON document_versions (doc_id) "
        "WHERE is_current = false AND index_status <> 'discarded' "
        "      AND first_published_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS document_versions_one_candidate")
    op.execute(
        "ALTER TABLE document_versions "
        "DROP CONSTRAINT document_versions_index_status_check"
    )
    op.execute(
        "ALTER TABLE document_versions "
        "ADD CONSTRAINT document_versions_index_status_check "
        "CHECK (index_status IN ('pending', 'processing', 'indexed', 'failed'))"
    )
    op.execute(
        "ALTER TABLE document_versions DROP COLUMN IF EXISTS first_published_at"
    )
