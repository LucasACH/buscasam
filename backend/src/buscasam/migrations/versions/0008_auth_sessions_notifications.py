"""users, sessions, notifications (ADR-0005 §6/§8, ADR-0010 §9)

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-25

"""
from alembic import op


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
          id            bigserial primary key,
          google_sub    text unique not null,
          email         text not null,
          hd            text not null,
          role          text not null,
          name          text not null,
          picture_url   text,
          created_at    timestamptz not null default now(),
          last_login_at timestamptz not null default now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE sessions (
          sid           bytea primary key,
          user_id       bigint not null references users(id) on delete cascade,
          created_at    timestamptz not null default now(),
          last_seen_at  timestamptz not null default now(),
          expires_at    timestamptz not null default now() + interval '90 days',
          user_agent    text,
          ip            inet
        )
        """
    )

    # ADR-0005 §6: `expires_at = created_at + 90 days` is never extended.
    # Enforced at the DB so the invariant survives any future caller that
    # reaches the table outside core/auth.
    op.execute(
        """
        CREATE FUNCTION sessions_expires_at_is_immutable()
        RETURNS trigger AS $$
        BEGIN
          IF NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
            RAISE EXCEPTION
              'sessions.expires_at is immutable (ADR-0005 §6)';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER sessions_expires_at_immutable
        BEFORE UPDATE ON sessions
        FOR EACH ROW EXECUTE FUNCTION sessions_expires_at_is_immutable()
        """
    )

    op.execute(
        """
        CREATE TABLE notifications (
          id           bigserial primary key,
          user_id      bigint not null references users(id) on delete cascade,
          event_key    text not null,
          kind         text not null,
          payload_json jsonb not null,
          read_at      timestamptz,
          created_at   timestamptz not null default now()
        )
        """
    )
    # ADR-0010 §9: producer-side idempotency.
    op.execute(
        "CREATE UNIQUE INDEX notifications_user_event_uniq "
        "ON notifications (user_id, event_key)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP FUNCTION IF EXISTS sessions_expires_at_is_immutable()")
    op.execute("DROP TABLE IF EXISTS users")
