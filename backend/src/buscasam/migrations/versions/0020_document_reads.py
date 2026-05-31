"""document_reads (read tracking for más leídos, module map discovery-most-read.md)

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-31

"""
from alembic import op


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row = one deduped lectura: (doc_id, reader_key, read_day). The PK *is*
    # the once-per-reader-per-doc-per-day invariant; the sole writer
    # (core/discovery.record_read) relies on INSERT ... ON CONFLICT DO NOTHING.
    # reader_key is u:{user_id} for an authed reader, a:{anon_id} for an Invitado.
    # ON DELETE CASCADE: a hard-deleted/purged document drops its reads.
    op.execute(
        """
        CREATE TABLE document_reads (
          doc_id     bigint not null references documents(id) on delete cascade,
          reader_key text not null,
          read_day   date not null,
          primary key (doc_id, reader_key, read_day)
        )
        """
    )
    # Serves the rolling-window aggregation in core/discovery.most_read.
    op.execute(
        "CREATE INDEX document_reads_day_doc ON document_reads (read_day, doc_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_reads")
