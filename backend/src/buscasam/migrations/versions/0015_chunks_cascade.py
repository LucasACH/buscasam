"""chunks FKs cascade on document/version delete (ADR-0006 §12 retention purge)

The §12 retention purge is a single `DELETE FROM documents`; for it to collect
chunks via `ON DELETE CASCADE`, both chunk FKs (to documents and to the
cascaded document_versions) must cascade. They were created without cascade in
0004/0010, so this slice adds it.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-28

"""
from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_doc_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_doc_id_fkey "
        "FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_version_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_version_id_fkey "
        "FOREIGN KEY (version_id) REFERENCES document_versions(id) "
        "ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_doc_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_doc_id_fkey "
        "FOREIGN KEY (doc_id) REFERENCES documents(id)"
    )
    op.execute("ALTER TABLE chunks DROP CONSTRAINT chunks_version_id_fkey")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_version_id_fkey "
        "FOREIGN KEY (version_id) REFERENCES document_versions(id)"
    )
