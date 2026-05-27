"""procrastinate schema (ADR-0008 async job queue)

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-27

"""
from alembic import op
from procrastinate.schema import SchemaManager


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(SchemaManager.get_schema())


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS "
        "procrastinate_events, "
        "procrastinate_jobs, "
        "procrastinate_periodic_defers, "
        "procrastinate_workers "
        "CASCADE"
    )
    op.execute("DROP TYPE IF EXISTS procrastinate_job_status CASCADE")
    op.execute("DROP TYPE IF EXISTS procrastinate_job_event_type CASCADE")
