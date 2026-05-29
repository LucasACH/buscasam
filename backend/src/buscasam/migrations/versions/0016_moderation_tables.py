"""document_reports + moderation_actions (ADR-0010 §9, module map report-moderation)

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-29

"""
from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADR-0010 §9. doc_id cascades so the §12 retention purge
    # (DELETE FROM documents) collects reports of a hard-deleted document;
    # user FK follows document_authors (no cascade — users are not deleted).
    op.execute(
        """
        CREATE TABLE document_reports (
          id               bigserial primary key,
          doc_id           bigint not null references documents(id) on delete cascade,
          reporter_user_id bigint not null references users(id),
          reason           text not null,
          status           text not null default 'open',
          created_at       timestamptz not null default now(),
          CONSTRAINT document_reports_reason_check
            CHECK (reason IN ('spam', 'contenido_inadecuado', 'plagio', 'error')),
          CONSTRAINT document_reports_status_check
            CHECK (status IN ('open', 'resolved'))
        )
        """
    )
    # Module map: a second open report by the same reporter on the same doc is a
    # harmless no-op (ON CONFLICT upstream); a resolved report coexists.
    op.execute(
        "CREATE UNIQUE INDEX document_reports_open_uniq "
        "ON document_reports (doc_id, reporter_user_id) WHERE status = 'open'"
    )

    # ADR-0010 §9: append-only audit log; cascades with its report on purge.
    op.execute(
        """
        CREATE TABLE moderation_actions (
          id              bigserial primary key,
          report_id       bigint not null references document_reports(id) on delete cascade,
          docente_user_id bigint not null references users(id),
          action          text not null,
          reason          text,
          created_at      timestamptz not null default now(),
          CONSTRAINT moderation_actions_action_check
            CHECK (action IN ('hide', 'unhide', 'dismiss'))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS moderation_actions")
    op.execute("DROP TABLE IF EXISTS document_reports")
