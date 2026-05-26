"""document_versions, document_attachments, chunks extension (ADR-0006 §5/§6/§7, ADR-0007 §9)

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-26

"""
from alembic import op


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE document_versions (
          id                       bigserial primary key,
          doc_id                   bigint not null references documents(id) on delete cascade,
          version_no               int not null,
          sha256                   bytea not null,
          original_filename        text not null,
          bytes                    bigint not null,
          mime                     text not null,
          uploaded_at              timestamptz not null default now(),
          uploaded_by              bigint references users(id),
          is_current               boolean not null default false,
          index_status             text not null default 'pending',
          index_error              text,
          indexed_at               timestamptz,
          extract_pipeline_version text not null default 'unknown',
          staged_abstract          text,
          staged_keywords          text[],
          staged_fecha             date,
          headline_fingerprint     text,
          CONSTRAINT document_versions_index_status_check
            CHECK (index_status IN ('pending', 'processing', 'indexed', 'failed'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX document_versions_doc_current "
        "ON document_versions (doc_id) WHERE is_current"
    )
    op.execute(
        "CREATE UNIQUE INDEX document_versions_doc_version_no "
        "ON document_versions (doc_id, version_no)"
    )

    op.execute(
        """
        CREATE TABLE document_attachments (
          id                bigserial primary key,
          doc_id            bigint not null references documents(id) on delete cascade,
          sha256            bytea not null,
          original_filename text not null,
          bytes             bigint not null,
          mime              text,
          uploaded_at       timestamptz not null default now(),
          uploaded_by       bigint references users(id)
        )
        """
    )
    op.execute(
        "CREATE INDEX document_attachments_doc_id "
        "ON document_attachments (doc_id)"
    )

    op.execute("ALTER TABLE chunks ADD COLUMN is_current boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE chunks ADD COLUMN version_id bigint references document_versions(id)")

    # Backfill: one synthetic document_versions row per document that has chunks;
    # then point those chunks at it and mark them is_current=true.
    op.execute(
        """
        INSERT INTO document_versions
            (doc_id, version_no, sha256, original_filename, bytes, mime,
             is_current, index_status, extract_pipeline_version)
        SELECT
            d.id, 1,
            decode(repeat('00', 32), 'hex'),
            'fixture-backfill',
            0,
            'application/pdf',
            true,
            'indexed',
            'fixture-backfill'
        FROM documents d
        WHERE EXISTS (SELECT 1 FROM chunks c WHERE c.doc_id = d.id)
        """
    )
    op.execute(
        """
        UPDATE chunks
        SET version_id = dv.id, is_current = true
        FROM document_versions dv
        WHERE chunks.doc_id = dv.doc_id
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS is_current")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS version_id")
    op.execute("DROP TABLE IF EXISTS document_attachments")
    op.execute("DROP TABLE IF EXISTS document_versions")
