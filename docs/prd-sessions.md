# PRD Sessions

One `/to-prd` invocation per slice, in order. Each session must restrict scope to its slice — call out explicit out-of-scope to prevent bleed.

Reference: `docs/SPEC.md`, `docs/adr/`.

---

## 1. Search (público + invitado)

```
/to-prd Search engine MVP, scoped to público-visibility documents and invitado users only.

In scope (per docs/SPEC.md §Búsqueda):
- Single text box + optional filters: fecha, área, tipo
- Reproducible URL /buscar?q=...&area=...&tipo=...&desde=...&pagina=...
- 10 results/page, relevance capped at 20 pages
- Result item: título, autores, fecha, área, tipo, abstract truncado, snippet
- "Más recientes" alternative order, uncapped
- Hybrid ranking: multilingual embeddings + PostgreSQL FTS español, fused via RRF
- Match floor: léxico match OR semantic threshold (calibrated pre-launch)
- Empty-state with query/filter suggestions when nothing clears the floor
- Filter-active queries can request unfiltered count under same visibility
- Lexical-only fallback when semantic service is down
- Pipeline en español; otros idiomas aceptados con calidad menor

Out of scope (defer to other PRDs):
- interno/privado visibility (needs auth — PRD #2)
- How documents enter the index (publication — PRD #3)
- "Trabajos relacionados" (detail page — PRD #4)
- Auth-gated UX

Assume seeded fixture documents already indexed. Relevant ADRs: 0001 (database), 0002 (embeddings), 0003 (backend), 0004 (frontend).
```

---

## 2. Auth & Sessions

```
/to-prd Authentication and session management.

In scope (per docs/SPEC.md §Usuarios Y Autenticación):
- Google UNSAM login only; rejected for non-UNSAM hd
- Roles by hd: Estudiante (estudiantes.unsam.edu.ar), Docente (unsam.edu.ar), Invitado (no session)
- Session expiry: 30 días sin actividad OR 90 días desde login (first to trigger)
- In-app bandeja for coauthorship invitations + processing/moderation notices, mark-as-read
- Search visibility extension: authenticated users see público + interno; coauthors see relevant privado

Out of scope:
- Coauthor invitation flow itself (PRD #5)
- Moderation actions (PRD #8)
- Email notifications beyond coautor invitation

Relevant ADRs: 0005 (authentication), 0003 (backend), 0004 (frontend).
```

---

## 3. Publication Flow

```
/to-prd Document publication flow: draft → upload → extract → review → publish.

In scope (per docs/SPEC.md §Documentos, §Publicación):
- Authenticated user creates draft: título, autores, área, tipo, visibilidad
- Upload archivo principal (PDF/DOCX/ODT), API returns 202, async processing
- Text extraction; system suggests abstract, palabras clave, fecha
- Author reviews/edits suggestions; título/abstract changes regenerate heading index before publish enabled
- Publish action — document becomes visible per visibilidad rules
- Hasta 5 adjuntos no indexados (CSV, código, imágenes, formatos permitidos)
- Tipos cerrados: tesis, paper, TP, proyecto investigación, monografía, ponencia/poster, apunte/resumen, informe cátedra
- Áreas jerárquicas: Escuela → Carrera → Materia/Disciplina
- Estados doc: draft → published; versión candidate: processing | processing_failed | ready_to_publish

Out of scope:
- Coautoría invitations/acceptance (PRD #5)
- Versioning replacement flow (PRD #6)
- Deletion (PRD #7)
- Search ranking changes

Relevant ADRs: 0006 (blob storage), 0007 (text extraction), 0008 (async jobs), 0002 (embeddings), 0001 (database).
```

---

## 4. Document Detail + Related Works

```
/to-prd Document detail page and "trabajos relacionados".

In scope (per docs/SPEC.md §Detalle Y Relacionados):
- URL permanente /docs/{id}, version-independent
- Shows metadatos, abstract, palabras clave, descarga del archivo actual + adjuntos
- "Trabajos relacionados" via heading-index comparison, same access policy as detail
- No response, sitemap, or count reveals unauthorized documents
- Apply visibility: público/interno/privado + coauthor rules + hidden/deleted states

Out of scope:
- Search results page (PRD #1)
- Publication (PRD #3)
- Versioning UI (PRD #6)

Relevant ADRs: 0006 (blob storage), 0002 (embeddings), 0001 (database).
```

---

## 5. Coauthorship

```
/to-prd Coauthor invitation, acceptance, and notifications.

In scope (per docs/SPEC.md §Autores):
- Uploader is propietario
- Invitar coautor registrado UNSAM: in-app + email notification, pendiente hasta aceptar
- Coautor pendiente: no acceso privado, no edición
- Coautor aceptado: access + edit per role
- Autor externo: text attribution only, no permissions/access
- In-app bandeja entries for invitations

Out of scope:
- Publication flow itself (PRD #3)
- General session/auth (PRD #2)
- Moderation notifications

Relevant ADRs: 0005 (authentication), 0001 (database), 0003 (backend).
```

---

## 6. Versioning & Replacement

```
/to-prd Document versioning: file replacement and candidate versions.

In scope (per docs/SPEC.md §Versiones, §Estados):
- Replacing archivo creates a new candidate version
- Previous published version remains available while candidate processes/reviews
- Only one processed + author-confirmed version becomes the public current
- Version history downloadable only by aceptados/propietario
- Candidate states: processing | processing_failed | ready_to_publish
- Failed candidate must not hide previous published version
- Publish/replace must never expose an unindexed version

Out of scope:
- Initial publication (PRD #3)
- Deletion (PRD #7)

Relevant ADRs: 0006 (blob storage), 0007 (text extraction), 0008 (async jobs), 0001 (database).
```

---

## 7. Deletion & Restoration

```
/to-prd Logical deletion, restoration, and purge.

In scope (per docs/SPEC.md §Eliminación):
- Author can logically delete a document; immediately inaccessible
- Restore window: 180 días
- After window, purge (files + index entries)
- Deleted documents excluded from búsqueda, detalle, relacionados, descarga, conteos, sitemap
- Moderation hiding is a separate state and does NOT start purge timer

Out of scope:
- Moderation hide/show (PRD #8)
- Publication (PRD #3)

Relevant ADRs: 0006 (blob storage), 0001 (database), 0008 (async jobs).
```

---

## 8. Moderation

```
/to-prd Report and moderation flow.

In scope (per docs/SPEC.md §Moderación MVP):
- Authenticated user reports a published document they can read: spam, contenido inadecuado, plagio, error
- Any Docente reviews reports, hides or re-shows document
- Each action records docente, razón, fecha
- Author receives in-app notification
- Docente inspects non-visible content only via moderation endpoints tied to the report
- Hide state separate from deletion; no purge timer

Out of scope:
- Appeal flow (explicitly out of MVP per SPEC)
- Deletion (PRD #7)
- General auth (PRD #2)

Relevant ADRs: 0005 (authentication), 0001 (database), 0003 (backend).
```

---

## Workflow per session

1. New Claude Code session (fresh context).
2. Paste the prompt block verbatim.
3. Answer skill's interview questions; reference `docs/SPEC.md` + listed ADRs when asked for context.
4. Skill submits PRD as GitHub issue. Capture issue # before closing session.
5. Move to next PRD only after current is submitted and reviewed.
