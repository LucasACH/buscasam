"""Sole owner of "what counts as a readable document" — ADR-0010 §6."""


def invitado_where(alias: str) -> str:
    """`WHERE`-clause body restricting reads to the invitado branch.

    `alias` is the SQL name (table name or alias) under which the `documents`
    table is in scope at the call site — passed explicitly so this module owns
    column qualification.

    See module map § `core/document_access` and ADR-0010 §6.
    """
    return (
        f"{alias}.visibility = 'publico' "
        f"AND {alias}.publication_status = 'published' "
        f"AND {alias}.soft_deleted_at IS NULL "
        f"AND {alias}.moderation_hidden_at IS NULL"
    )
