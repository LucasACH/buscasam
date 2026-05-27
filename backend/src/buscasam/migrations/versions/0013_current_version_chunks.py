"""current-version searchable chunks and version-scoped sequence identity

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-27

"""
from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Complete the 0010 backfill for any legacy fixture/import chunks written
    # after that migration but before version ownership became mandatory.
    op.execute(
        """
        INSERT INTO document_versions
            (doc_id, version_no, sha256, original_filename, bytes, mime,
             is_current, index_status, extract_pipeline_version)
        SELECT
            d.id, COALESCE(MAX(v.version_no), 0) + 1,
            decode(repeat('00', 32), 'hex'),
            'legacy-current-backfill',
            0,
            'application/pdf',
            true,
            'indexed',
            'legacy-current-backfill'
        FROM documents d
        LEFT JOIN document_versions v ON v.doc_id = d.id
        WHERE EXISTS (
            SELECT 1 FROM chunks c
            WHERE c.doc_id = d.id AND c.version_id IS NULL
        )
          AND NOT EXISTS (
            SELECT 1 FROM document_versions current_v
            WHERE current_v.doc_id = d.id AND current_v.is_current
        )
        GROUP BY d.id
        """
    )
    op.execute(
        """
        UPDATE chunks c
        SET version_id = v.id, is_current = true
        FROM document_versions v
        WHERE c.version_id IS NULL
          AND v.doc_id = c.doc_id
          AND v.is_current
        """
    )

    op.execute("ALTER TABLE chunks ALTER COLUMN version_id SET NOT NULL")
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_doc_id_chunk_seq_key")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_version_id_chunk_seq_key "
        "UNIQUE (version_id, chunk_seq)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_version_id_chunk_seq_key")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_doc_id_chunk_seq_key "
        "UNIQUE (doc_id, chunk_seq)"
    )
    op.execute("ALTER TABLE chunks ALTER COLUMN version_id DROP NOT NULL")
