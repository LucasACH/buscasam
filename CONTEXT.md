# BUSCASAM

Academic search portal for the UNSAM community. Sole context — single backend, single corpus, single user base.

## Language

**Invitado** (guest):
A visitor without an UNSAM Google account. Browses and downloads `público` documents; cannot publish or report.
_Avoid_: external user, anonymous (use *invitado* even in code paths).

**Estudiante**:
An UNSAM Google account with `hd = estudiantes.unsam.edu.ar`. Can publish, accept co-authorship, search, and report readable documents.

**Docente**:
An UNSAM Google account with `hd = unsam.edu.ar`. Same capabilities as **Estudiante** plus document moderation (resolve reports, hide/unhide documents). Treated as "trusted UNSAM staff", not strictly "teaching faculty" - admin and library staff also receive this domain and get the same powers by design.
_Avoid_: profesor, moderator (use *docente*; the moderator-vs-docente distinction is intentionally collapsed).

**hd claim**:
The Google OIDC `hd` (hosted domain) field. The only trustworthy signal that an email is managed by a specific Google Workspace tenant. Email-suffix matching is unsafe; `hd` is mandatory.

**Visibilidad**:
A per-document setting controlling who sees it. Three values: `público` (everyone including **Invitados**), `interno` (any signed-in UNSAM user - **Estudiante** or **Docente**), `privado` (owner and accepted co-authors only). Enforced by the access chokepoint (ADR-0010).

## Relationships

- An **Estudiante** and a **Docente** are both authenticated users; they differ only in moderation rights.
- An **Invitado** is never a row in the `users` table.
- A published document's **Visibilidad**, lifecycle/moderation state, accepted authorship, and requester's role decide access; the predicate lives in one access module.

## Example dialogue

> **Dev:** "If a librarian with `@unsam.edu.ar` reviews a document report, can they resolve it?"
> **Domain expert:** "They can resolve it themselves — they're a **Docente** for our purposes. We're collapsing 'UNSAM staff' into the docente role on purpose; the SPEC's docente-moderator wording is what we're honouring, even if the literal job title isn't teaching."

## Flagged ambiguities

- "docente" in the SPEC sounded teaching-specific. Resolved: in BUSCASAM, **Docente** = any holder of `@unsam.edu.ar`, which is the moderation surface by design.
