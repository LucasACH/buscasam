"""chunks table with generated es_unaccent tsvector + halfvec(1024) embedding

ADR-0001 §3, §5, §10; ADR-0002 §6, §7.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-24

"""
from alembic import op


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE chunks (
          id                       bigserial    PRIMARY KEY,
          doc_id                   bigint       NOT NULL REFERENCES documents(id),
          chunk_seq                int          NOT NULL,
          is_headline              boolean      NOT NULL,
          body_text                text         NOT NULL,
          body_tsv                 tsvector     GENERATED ALWAYS AS
                                                  (to_tsvector('es_unaccent', body_text))
                                                  STORED,
          embedding                halfvec(1024),
          similarity_embedding     halfvec(1024),
          embedding_model_version  text         NOT NULL,
          UNIQUE (doc_id, chunk_seq),
          CHECK (NOT is_headline OR chunk_seq = 0)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunks")
