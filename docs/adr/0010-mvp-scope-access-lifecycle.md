# MVP scope, document access, and publication lifecycle

## Status

Accepted

## Decision

MVP ships a narrow, end-to-end academic document repository: authentication, upload and staged publication, co-author acceptance, hybrid search/filtering, detail/download, related documents, and document moderation. One access-policy module protects every document-derived read. Publication and moderation have explicit states; unfinished features in the broader product vision are deferred.

## Locked

1. MVP feature set:
   - Guest: search/filter, view and download `publico` documents.
   - Authenticated UNSAM user: guest capabilities plus create a draft, upload/replace a main file, add up to five attachments, edit extracted metadata, publish, accept/decline co-authorship, report a published document, and read/acknowledge their invitation/moderation notifications.
   - Docente: authenticated capabilities plus review document reports, hide/unhide documents, and view hidden material only inside moderation endpoints.
   - All readers: document detail and visibility-filtered "Trabajos relacionados".

2. Deferred beyond MVP: personalized home recommendations, interests, query history UI/storage, autocomplete/popular queries, favourites, comments, comment notifications, author/type/area browse landing pages beyond search filters, moderation appeals, and email preferences. They must not appear in MVP API schemas, queues, or frontend navigation.

3. Lifecycle model:

   ```
   documents.publication_status: draft -> published
   candidate document_versions.index_status: pending -> processing -> indexed | failed
   ```

   `processing`, `processing_failed`, and `ready_to_publish` are UI states derived from the candidate version status and headline fingerprint, not document publication states. Only documents with `publication_status='published'` are reader-visible or searchable. A replacement never changes that document status while it processes; the previously published current version remains searchable until the author publishes a successful replacement.

4. Publication flow:
   - Create draft with manually entered `title`, `area_path`, `document_type`, `visibility`, and author list.
   - Upload main file returns `202`, creates a pending `document_versions` row, and enqueues extraction/indexing.
   - Worker writes candidate-version staged `abstract`, `keywords`, and `fecha`, body chunks, and an initial staged headline chunk from the document title plus staged abstract; it never modifies published metadata or publishes automatically.
   - Author reviews/edits staged metadata. An edit that changes indexed headline text invalidates its fingerprint and enqueues fast headline reindex. `ready_to_publish` means candidate body indexing succeeded and its headline fingerprint matches staged final metadata.
   - Publish transaction copies staged metadata to `documents` and flips already indexed matching chunks/version to current; it never calls TEI.
   - Metadata edits after publication persist immediately and enqueue headline reindex; a title change also invalidates any staged candidate headline fingerprint. Search headline/snippet may be briefly eventually consistent while the detail view shows persisted metadata.

5. Co-authorship:

   ```
   document_authors (
     id           bigserial primary key,
     doc_id       bigint not null references documents(id),
     user_id      bigint references users(id),
     display_name text not null,
     status       text not null -- 'owner' | 'pending' | 'accepted' | 'declined' | 'external'
   )
   CREATE UNIQUE INDEX ON document_authors (doc_id, user_id) WHERE user_id IS NOT NULL;
   CREATE UNIQUE INDEX ON document_authors (doc_id) WHERE status = 'owner';
   ```

   A check constraint requires `user_id IS NULL` exactly for `status='external'`. The uploader is `owner`. A registered co-author obtains private read/edit permission only after `accepted`. External authors are attribution only and cannot authenticate as an author; distinct external people may share a display name.

6. Access chokepoint: `core/document_access.py` owns reusable SQL fragments and query functions. All endpoints returning a document, metadata derived from a document, blob, related item, sitemap row, or search count use it. Related lookup accepts `doc_id` and `UserCtx`, obtains the source headline only after readable access succeeds, and filters candidates with the same policy. The sole pre-acceptance disclosure exception is a recipient-scoped co-author invitation containing document title and inviter identity, authorized by its pending `document_authors.user_id`. No frontend process queries Postgres.

7. Normal readable predicate:

   ```sql
   documents.publication_status = 'published'
   AND documents.soft_deleted_at IS NULL
   AND documents.moderation_hidden_at IS NULL
   AND (
     documents.visibility = 'publico'
     OR (documents.visibility = 'interno' AND :is_unsam)
     OR EXISTS (
       SELECT 1 FROM document_authors da
       WHERE da.doc_id = documents.id
         AND da.user_id = :user_id
         AND da.status IN ('owner', 'accepted')
     )
   )
   ```

   Denied reads return `404`. Search, recent sort, related documents, detail, current-version download, attachments, and sitemap all apply this policy; sitemap additionally requires `visibility = 'publico'`.

8. Management predicates:
   - `owner` and `accepted` authors may view draft/candidate state, edit metadata, replace files, manage attachments, and download historical versions.
   - Only `owner` may manage co-authors, change visibility, publish a candidate, soft-delete, or restore a document.
   - A pending invited user may read their minimal invitation and accept/decline only that invitation.
   - A docente does not gain access to private documents outside a moderation case.

9. Moderation:
   - Authenticated users may report only readable, published documents.
   - Docentes operate through moderation endpoints with an explicit moderation-access query, not the normal reader predicate.
   - Hide sets `moderation_hidden_at`; unhide clears it. Author deletion sets `soft_deleted_at`. These are separate states.
   - `moderation_actions` append-only rows contain report id, docente id, action, reason, and timestamp. In-app author notification is created on hide/unhide.
   - Appeals are deferred; authors can contact administration out of band at MVP.

   ```
   document_reports(id, doc_id, reporter_user_id, reason, status, created_at)
   moderation_actions(id, report_id, docente_user_id, action, reason, created_at)
   notifications(id, user_id, event_key, kind, payload_json, read_at, created_at)
   CREATE UNIQUE INDEX ON notifications (user_id, event_key);
   ```

   Report `status` is `open|resolved`; action is `hide|unhide|dismiss`. Notification `kind` at MVP is `coauthor_invite|document_hidden|document_unhidden|processing_failed`.

10. Deletion/retention: author soft-delete hides the document immediately and permits restore until the 180-day purge. Moderation-hidden documents are retained and are not purged unless separately author-deleted.

11. Search availability: a document enters search only at publish time with an indexed current version and a headline chunk. Failed or pending versions remain visible to their authors in draft management only.

12. MVP acceptance tests: guest cannot observe `interno`, `privado`, hidden, deleted, unpublished draft, or failed-candidate content through any normal endpoint; a failed replacement does not hide its prior published version; accepted author can read/edit private work; pending co-author sees only their invitation until acceptance; docente moderation can inspect a reported hidden/private document only through moderation endpoints; notification retries cannot create duplicates; publication and replacement never expose an unindexed current version.
