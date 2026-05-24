"""enable extensions and complete documents shape (ADR-0001 §7, §8)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-24

"""
from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


DOCUMENT_TYPES = (
    "tesis",
    "paper",
    "trabajo_practico",
    "proyecto_investigacion",
    "monografia",
    "ponencia_poster",
    "apunte_resumen",
    "informe_catedra",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TEXT SEARCH CONFIGURATION es_unaccent (COPY = spanish);
        ALTER TEXT SEARCH CONFIGURATION es_unaccent
          ALTER MAPPING FOR hword, hword_part, word
          WITH unaccent, spanish_stem;
        """
    )

    types_list = ", ".join(f"'{t}'" for t in DOCUMENT_TYPES)
    op.execute(
        f"""
        ALTER TABLE documents
          ADD COLUMN titulo     text       NOT NULL,
          ADD COLUMN fecha      date       NOT NULL,
          ADD COLUMN area_path  ltree      NOT NULL,
          ADD COLUMN tipo       text       NOT NULL,
          ADD COLUMN abstract   text,
          ADD CONSTRAINT documents_tipo_check CHECK (tipo IN ({types_list}))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
          DROP CONSTRAINT documents_tipo_check,
          DROP COLUMN abstract,
          DROP COLUMN tipo,
          DROP COLUMN area_path,
          DROP COLUMN fecha,
          DROP COLUMN titulo
        """
    )
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS es_unaccent")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS ltree")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
