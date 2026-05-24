"""Sole owner of "what counts as a readable document" — ADR-0010 §6."""


def invitado_fragment() -> tuple[str, dict]:
    """Predicate restricting reads to the invitado branch.

    See module map § `core/document_access` and ADR-0010 §6.
    """
    sql = (
        "visibility = 'publico' "
        "AND publication_status = 'published' "
        "AND soft_deleted_at IS NULL "
        "AND moderation_hidden_at IS NULL"
    )
    return sql, {}
