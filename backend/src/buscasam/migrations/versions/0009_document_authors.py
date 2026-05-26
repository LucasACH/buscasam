"""document_authors (ADR-0010 §5)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-26

"""
from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE document_authors (
          id           bigserial primary key,
          doc_id       bigint not null references documents(id),
          user_id      bigint references users(id),
          display_name text not null,
          status       text not null,
          CONSTRAINT document_authors_status_check
            CHECK (status IN ('owner', 'pending', 'accepted', 'declined', 'external')),
          CONSTRAINT document_authors_external_user_null_check
            CHECK ((status = 'external') = (user_id IS NULL))
        )
        """
    )
    # ADR-0010 §5: a registered author appears at most once per document.
    op.execute(
        "CREATE UNIQUE INDEX document_authors_doc_user_uniq "
        "ON document_authors (doc_id, user_id) WHERE user_id IS NOT NULL"
    )
    # ADR-0010 §5: exactly one owner per document.
    op.execute(
        "CREATE UNIQUE INDEX document_authors_one_owner "
        "ON document_authors (doc_id) WHERE status = 'owner'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_authors")
