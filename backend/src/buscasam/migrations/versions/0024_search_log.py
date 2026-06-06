"""search_events + search_clicks: relevance-eval instrumentation

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-06

"""

from alembic import op


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # search_events: one row per relevance query (q non-empty) — "what we
    # showed". doc_ids is the ordered page the user saw; the retrieval-path
    # flags say which branch produced it. This is ground truth the offline
    # eval harness joins against and can never be reconstructed after the fact.
    # No retention policy yet (raw q stored deliberately for relevance eval).
    op.execute(
        "CREATE TABLE search_events ("
        "  search_id text PRIMARY KEY, "
        "  created_at timestamptz NOT NULL DEFAULT now(), "
        "  reader_key text NOT NULL, "
        "  q text NOT NULL, "
        "  q_norm text NOT NULL, "
        "  orden text NOT NULL, "
        "  area_path text, "
        "  tipos text[] NOT NULL DEFAULT '{}', "
        "  desde integer, "
        "  hasta integer, "
        "  pagina integer NOT NULL, "
        "  doc_ids integer[] NOT NULL, "
        "  total integer NOT NULL, "
        "  saturated boolean NOT NULL, "
        "  lexical_fallback boolean NOT NULL, "
        "  fuzzy_fallback boolean NOT NULL, "
        "  semantic_used boolean NOT NULL, "
        "  latency_ms integer NOT NULL"
        ")"
    )
    op.execute("CREATE INDEX search_events_created_at ON search_events (created_at)")
    op.execute("CREATE INDEX search_events_q_norm ON search_events (q_norm)")

    # search_clicks: a result click attributed to its originating search via the
    # ?s=&r= the result link carries. Separate from document_reads so reads stay
    # ranking-free (ADR-0014) — clicks-for-eval are a distinct concern. One click
    # per (search_id, doc_id): rank is fixed within a search, so a re-render or
    # double-navigation is a no-op rather than a duplicate.
    op.execute(
        "CREATE TABLE search_clicks ("
        "  search_id text NOT NULL, "
        "  doc_id integer NOT NULL, "
        "  rank integer NOT NULL, "
        "  reader_key text NOT NULL, "
        "  created_at timestamptz NOT NULL DEFAULT now(), "
        "  PRIMARY KEY (search_id, doc_id)"
        ")"
    )
    op.execute("CREATE INDEX search_clicks_search_id ON search_clicks (search_id)")


def downgrade() -> None:
    op.execute("DROP TABLE search_clicks")
    op.execute("DROP TABLE search_events")
