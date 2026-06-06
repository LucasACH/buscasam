"""document_versions failure kind + failed-at for author-initiated retry

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-06

"""

from alembic import op


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Classifies a terminal indexing failure so the editar UI can offer retry:
    # 'file' (corrupted/unreadable upload — needs a new file) vs 'system'
    # (worker/infra fault — retriable). index_failed_at anchors the retry
    # cooldown server-side. Both set by mark_failed, cleared on retry; NULL
    # outside of 'failed'. index_retry_count counts author-initiated retries
    # on this version (capped by versions.MAX_INDEX_RETRIES) and survives the
    # retry reset.
    op.execute(
        "ALTER TABLE document_versions "
        "ADD COLUMN index_error_kind text "
        "  CHECK (index_error_kind IN ('file', 'system')), "
        "ADD COLUMN index_failed_at timestamptz, "
        "ADD COLUMN index_retry_count integer NOT NULL DEFAULT 0"
    )
    # Backfill rows that failed before this column existed, deriving the kind
    # from the structured index_error prefixes mark_failed has always written.
    op.execute(
        "UPDATE document_versions SET "
        "  index_error_kind = CASE "
        "    WHEN index_error LIKE 'corrupted:%' "
        "      OR index_error LIKE 'ocr_failed:%' THEN 'file' "
        "    ELSE 'system' END, "
        "  index_failed_at = now() "
        "WHERE index_status = 'failed'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE document_versions "
        "DROP COLUMN index_error_kind, DROP COLUMN index_failed_at, "
        "DROP COLUMN index_retry_count"
    )
