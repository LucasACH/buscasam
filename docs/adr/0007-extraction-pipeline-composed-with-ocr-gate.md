# Text extraction pipeline: composed per-format, gated OCR, single chokepoint

## Status

Accepted

## Decision

BUSCASAM extracts indexable text from uploaded PDF/DOCX/ODT files via a per-format composition of pure-Python libraries (`pdfminer.six` for PDFs, `python-docx` for DOCX, `odfpy` for ODT), with `ocrmypdf` (wrapping Tesseract on `spa+eng`) as a gated fallback when `pdfminer` extracts near-zero text from a PDF. All of this lives behind one `core/extract.py` chokepoint module, enforced by a CI grep — same shape as the chokepoints in ADR-0001 §9, ADR-0002 §3, ADR-0003 §3, ADR-0005 §3, and ADR-0006 §3. The module exposes an `ExtractedDoc` shape (text + paragraph + page offsets + raw metadata) plus a `derive_metadata()` helper that produces the SPEC-required auto-extracted fields (abstract, palabras clave, fecha) via simple heuristics: heading-match-then-leading-paragraphs for abstract, YAKE (`lang='es'`, `n=8`, with a small project blocklist) for keywords, and a year-regex over the cover page falling back to PDF `/CreationDate` and then upload date for fecha. Extraction runs inside a single `index_document(version_id)` worker job (the indexer from ADR-0003 §4), which may take up to ~30 minutes on a scanned thesis; this duration constraint and the resulting need for priority/separation are surfaced as inputs to ADR-0008. Encrypted PDFs are rejected synchronously at upload; corrupted files fail the indexer async and the version is marked `index_status='failed'` with an in-app notification to the author. The pipeline carries a single compound version string (`extract_pipeline_version` on `document_versions`), mirroring ADR-0002 §6's per-row embedding model version, so reindex cutovers are observable and partial-state corpora are explicit rather than silent.

## Context

ADR-0001 §3 commits to chunked indexing — bodies are split into ~512-token chunks, both `tsvector` and embeddings live at the chunk level — which only works if there is a clean text stream to chunk. ADR-0002 §4 sets the effective chunk budget at 510 tokens. ADR-0006 §5 stores uploaded bytes as sha256-addressed immutable blobs; the indexer reads from `blob_store.open_for_send(sha256)`. ADR-0003 §4 places all external-service and slow work behind the queue with one uniform `enqueue(job)` call; FastAPI `BackgroundTasks` is banned. The SPEC pins the input formats (PDF/DOCX/ODT for indexing; CSV/code/images as non-indexed attachments) and the auto-extracted metadata (abstract, palabras clave, fecha). The team is small and Python-only; the production VM is 16 GB RAM with Postgres + a ~2 GB TEI model already resident, leaving the operating budget for extraction tight and clearly bounded against adding a second model or a JVM. Most of the academic corpus is born-digital (LaTeX or Word exports), but scanned PDFs — older theses, photographs of handwritten apuntes, library digitizations — exist and must remain indexable.

## Considered options

- **Apache Tika.** Single JVM sidecar handling PDF / DOCX / ODT + many others, with Tesseract integration built in. Rejected: JVM adds ~500 MB–1 GB RAM on a VM where TEI already dominates, and introduces a non-Python ops surface to a Python-only team. The features that would justify it — broad format coverage past PDF/DOCX/ODT, mature metadata extraction across hundreds of MIME types — are not in scope.
- **`unstructured`.** One Python lib advertising "smart" partitioning of PDFs and Office docs with layout, table, and OCR support. Rejected: pulls heavy ML dependencies (detectron2 / PaddleOCR for layout analysis) which directly contradicts ADR-0002 §1's commitment that TEI is the only model on this hardware. Layout quality on academic multi-column PDFs is also uneven in practice.
- **`pypdf` alone (no OCR).** Lightweight, pure Python, the obvious "just extract text" path. Rejected: reading-order quality on multi-column academic papers is poor (column-mixing is common), and zero coverage for scanned PDFs means a whole category of legitimate uploads silently indexes empty.
- **`PyMuPDF` (`fitz`).** Best-in-class quality and speed for PDF extraction. Rejected at this scope: AGPL-3.0 licensing is a meaningful constraint that warrants its own ADR-worthy conversation, separate from the pipeline-shape decision. Keeping `pdfminer.six` (MIT) leaves the door open to a future ADR specifically about adopting PyMuPDF, without coupling that conversation to this one.
- **Always run `ocrmypdf --skip-text`.** Let `ocrmypdf` itself decide per-page whether OCR is needed. Rejected: pays the ocrmypdf startup overhead (~1 s) on every PDF even when no OCR is required, and hides the gate decision inside a third-party tool instead of leaving the threshold as a project-tunable.
- **Tesseract directly via `pytesseract` + `pdf2image`.** Rolls our own scan path. Rejected: loses ocrmypdf's deskew, image cleanup, hyphenation handling, and PDF round-trip — the same Tesseract underneath, more code to own for no quality gain.
- **OCR-embedded-images path for DOCX/ODT.** Walk inline shapes, run Tesseract on each. Rejected at MVP: image-only DOCX/ODT is an uncommon authoring pattern at UNSAM (users with scans naturally upload PDFs), and the path adds image-extraction code per format. Documented as a known limitation; a low-yield metric on DOCX/ODT extraction will surface whether it matters in practice.
- **KeyBERT for palabras clave (re-using TEI/e5).** Extract candidate noun phrases via spaCy, embed each via TEI, pick the most cosine-similar to the doc-level embedding. Rejected at MVP: ~30–100 extra TEI calls per document bumps indexing latency, and the SPEC's "no filtro dedicado a keywords" + the click-to-search UX flowing through the hybrid engine mean YAKE-quality keywords are good enough. KeyBERT remains a one-file upgrade inside the same chokepoint if YAKE keywords prove embarrassingly bad in production.
- **LLM-based abstract / keyword / fecha extraction.** Best quality across all three. Rejected: would introduce a second model on the box, directly violating ADR-0002 §1 RAM posture; defer until UNSAM has GPU or a hosted-model exception is granted.
- **Pre-cache OCR'd PDF as a derived blob.** Avoid re-OCR on reindex by writing the text-layer-added PDF back as a new blob, addressable by its own sha256. Rejected at this scope: adds a "derived blob" concept to ADR-0006, which intentionally models only source uploads; reindex is rare (per ADR-0002 it's planned maintenance) so the OCR savings are not worth the schema/storage complication.
- **Split the indexer into two jobs (`extract_document` → `ocr_then_index`).** Lets the slow OCR sub-path live on a low-priority worker trivially. Rejected: an extra job boundary with partial-state failure semantics, and the fast-path extract work is wasted whenever OCR is needed. Single-job shape leaves the priority question to ADR-0008 cleanly without prejudging it.
- **Empty extraction = `index_status='failed'`.** Rejected: a document that processed cleanly but happened to contain no extractable text (e.g., a poster-style PDF that is mostly a graphic) is not a pipeline failure; it should remain findable by its manual metadata (title, autores, área, tipo). Failure is reserved for cases where the pipeline could not complete.

## Architecture decisions locked by this ADR

1. **Composed per-format, one chokepoint.** All text extraction and metadata derivation lives in `core/extract.py`. CI grep bans imports of `pdfminer`, `pypdf`, `ocrmypdf`, `python_docx`, `docx`, `odfpy`, `pytesseract`, and `yake` outside `core/extract.py` (excluding tests). Same shape as ADR-0001 §9, ADR-0002 §3, ADR-0003 §3, ADR-0005 §3, ADR-0006 §3.

2. **Output contract.**

   ```python
   @dataclass(frozen=True)
   class ExtractedDoc:
       text: str
       paragraph_breaks: list[int]    # byte offsets into text; ascending
       page_breaks: list[int]         # byte offsets; empty for DOCX/ODT
       raw_metadata: dict             # PDF /CreationDate, /Title, /Author, /Keywords, …

   @dataclass(frozen=True)
   class IndexableMetadata:
       abstract: str                  # may be empty when extraction yielded near-zero text
       keywords: list[str]            # 0..n; n ≤ 10
       fecha: date | None             # None → caller falls back to upload date

   async def extract(sha256: str, mime: str) -> ExtractedDoc
   def derive_metadata(doc: ExtractedDoc) -> IndexableMetadata
   ```

   The chunker from ADR-0001 §3 consumes `ExtractedDoc` and is free to prefer paragraph boundaries when the token budget allows, falling back to mid-paragraph splits only when a single paragraph exceeds the ADR-0002 §4 effective budget of 510 tokens. `page_breaks` is empty for DOCX/ODT — those formats have no stable rendered pagination until laid out, and faking it would mislead any downstream consumer.

3. **PDF library: `pdfminer.six`.** Pure Python, MIT-licensed, layout-aware reading order via `LAParams`. Multi-column academic papers extract in the correct reading order, which is the dominant correctness concern for the corpus. Paragraph reconstruction is a small heuristic inside the chokepoint: group character blocks by vertical gap > median line-height, mark the resulting boundaries in `paragraph_breaks`. Per-page CPU is in the seconds, comfortably within the async indexer budget.

4. **OCR: gate-then-`ocrmypdf`.** For each PDF, run `pdfminer.six` first. If the extracted text has fewer than 100 characters per page averaged over the document (configurable), invoke `ocrmypdf --skip-text --language spa+eng` to add a Tesseract text layer to the PDF, then re-run `pdfminer.six` on the OCR'd output. The threshold is a tunable inside `core/extract.py`, and a metric `ocr_invocation_rate` is logged so the threshold's calibration is observable. `ocrmypdf` is preferred over a direct Tesseract call because it owns deskew, image cleanup, hyphenation, and the PDF round-trip; no quality is lost relative to calling Tesseract directly. Tessdata for `spa` and `eng` (~25 MB combined) is included in the indexer container image.

5. **DOCX: `python-docx`. ODT: `odfpy`.** Both expose paragraph iteration natively, so the `paragraph_breaks` channel is trivially populated. Embedded scanned images inside DOCX/ODT are **not** OCR'd at MVP — these documents are dominated by typed text in the actual UNSAM corpus, and the rare image-only DOCX/ODT case is logged as low-yield via the same `empty_extraction_rate` metric used for failed-OCR PDFs. Adding embedded-image OCR is a one-function change inside the chokepoint if the metric ever shows the case is real.

6. **Abstract: layered heuristic, capped 300 words.** In order:
   1. Regex `^(Resumen|Abstract|Summary|Sinopsis)\b` (case-insensitive) within the first two pages; if matched, take subsequent text until the next heading-like line or the word cap.
   2. Otherwise, take the first 1–3 paragraphs of body text, truncated to the word cap.
   3. If body text is near-empty, `abstract = ""`.

   The 300-word cap keeps the abstract within a single e5 passage (~510 tokens), which keeps the headline chunk (`title + abstract` per ADR-0001 §3) uniformly shaped. The publication form pre-fills this field from the auto-extraction and lets the author edit before publishing — see §13 below for the SPEC clarification this implies.

7. **Keywords: YAKE.** `lang='es'`, `n=8`, max n-gram size 3, dedup threshold ~0.7, with a small project-maintained blocklist filtering common academic-template noise (`"trabajo práctico"`, `"presente informe"`, `"este trabajo"`, …). Language is `'es'` always — no per-doc language detection at MVP, matching the SPEC's "degraded quality for other languages" posture. The output is purely for UI display (SPEC §Palabras clave: clickable tags whose clicks run a hybrid search), so imperfect-but-recognizable phrases are acceptable; the hybrid search itself laundes keyword quality on click.

8. **Fecha: best-effort heuristic, author-authoritative.** In order:
   1. Scan the first two pages of body text for `\b(19|20)\d{2}\b` near cover-page tokens (`tesis|trabajo|presentado|defendido|publicado|tesina`); pick the most-recent plausible match (within `[1970, current_year + 1]`).
   2. Fallback: PDF `/CreationDate` if it parses to a plausible date in the same range.
   3. Fallback: `None` (caller writes upload date from `document_versions.uploaded_at`).

   The publication form pre-fills the date and lets the author edit. The ADR records the SPEC clarification this requires — see §13.

9. **Failure policy and schema.**

   - **Encrypted PDFs are rejected synchronously at upload**, before the index job is enqueued. The publication endpoint runs a one-byte probe via `pdfminer`; on `PDFEncryptionError` the upload is rejected with an actionable 415 ("este PDF está protegido por contraseña — quitá la protección y reintentá"). No `document_versions` row is created.
   - **Corrupted files fail async.** The indexer catches `PDFSyntaxError`, `zipfile.BadZipFile`, and similar; the version is marked `index_status='failed'` with a short `index_error`. The author receives an in-app notification via the SPEC §Notificaciones campanita (not email — email is reserved for SPEC's "eventos críticos" tier). Re-uploading creates a new version.
   - **Empty extraction is not a failure.** A version that processed cleanly but yielded near-zero text is `index_status='indexed'` with no chunks; it remains findable by manual metadata. The `empty_extraction_rate` metric makes regressions visible.

   Schema extension to ADR-0006 §5's `document_versions`:

   ```sql
   ALTER TABLE document_versions ADD COLUMN
     index_status text NOT NULL DEFAULT 'pending',    -- 'pending' | 'indexed' | 'failed'
     index_error  text,                                -- short reason when 'failed'
     indexed_at   timestamptz,                         -- timestamp of success
     extract_pipeline_version text NOT NULL DEFAULT 'unknown';
   ```

   The search-query chokepoint from ADR-0001 §9 is **not** modified: a `pending` or `failed` version simply has no rows in `chunks`, so the existing chunk join already excludes it. The status fields exist for author UX (the publication form and "mis trabajos" view), not for search filtering.

10. **Single-job pipeline.** Extraction runs inside one `index_document(version_id)` worker job that does: read blob → try `pdfminer` → if low-yield, run `ocrmypdf` → re-extract → derive metadata → chunk → embed → write chunks transactionally. Atomic from the orchestrator's POV (one job, one success-or-failure boundary). No intermediate cached OCR blob is written; reindex re-runs the OCR (acceptable: reindex is rare per ADR-0002).

11. **Inputs to ADR-0008 (async job runner).** This ADR does not pick the runner. It does impose two constraints:
    - **Per-job duration may reach ~30 minutes** for scanned-thesis OCR on CPU Tesseract. The runner must either tolerate jobs of this length without timing out, or
    - **Provide priority / separate queue capability** so OCR-heavy jobs do not head-of-line-block fast born-digital jobs (5-second extract + embed).

    Either resolution is fine; both belong to ADR-0008.

12. **Provenance: `extract_pipeline_version`.** One compound version string, sourced from a single config constant (e.g., `EXTRACT_PIPELINE_VERSION="v1"` in `pyproject.toml` / env), stored per `document_versions` row. A bump means "this version's `pdfminer.six` + `ocrmypdf` + `python-docx` + `odfpy` combination produces materially different output from the prior one." Bumping is a deliberate operator action paired with a reindex window — same posture as ADR-0002 §5/§6 handles `EMBEDDING_MODEL_REVISION`. Reindex updates the column row by row; mixed values during cutover are explicit, not silent.

13. **SPEC clarifications flagged by this ADR.**
    - **§Publicación / Metadatos auto-extraídos.** The current wording groups abstract, palabras clave, and fecha as "auto-extraídos" without naming the author's role. This ADR commits to a UX where all three are pre-filled from auto-extraction and editable in the publication form. SPEC should be updated to read approximately "pre-llenados automáticamente, editables por el autor."
    - **§Publicación / fecha.** SPEC does not define what `fecha` means semantically. Other SPEC sections (filter by fecha, "más recientes" sort, result-page display) only make sense if it is the *academic* date of the work (publication / defense / submission), not the upload date. This ADR commits to that reading and to a best-effort heuristic extraction with author override. SPEC should be updated to read approximately "fecha estimada del trabajo (no de la subida), pre-llenada automáticamente y editable por el autor."

## Consequences

- **Operational simplicity in dependency footprint.** No JVM, no second model on the box, no heavy CV stack. The indexer image adds `pdfminer.six` + `ocrmypdf` + `python-docx` + `odfpy` + `yake` + Tesseract + tessdata-spa + tessdata-eng — all pure-Python except Tesseract (a single OS package). RAM budget on the 16 GB VM stays dominated by Postgres + TEI, with extraction CPU-bursty but memory-light.
- **OCR is the long tail.** Born-digital PDFs index in seconds; a 500-page scanned thesis can take 10–30 minutes of CPU Tesseract. The gate metric `ocr_invocation_rate` is the operational handle — a sudden spike means corpus composition shifted (a library digitization batch, an old-archive import) and queue sizing may need to respond.
- **`pdfminer.six` reading order is the correctness lever, not raw speed.** A move to `PyMuPDF` later (faster, marginally better) is a future ADR specifically about the AGPL conversation; the chokepoint shape (§1, §2) makes the swap surgical — one file changes.
- **Chunker quality depends on `paragraph_breaks`.** A pdfminer paragraph heuristic that's too aggressive (over-fragments) gives the chunker too many tiny anchors and it falls back to token-only splitting; too conservative (under-detects) means paragraph-respecting chunking is rarely possible. The heuristic is a tuning parameter inside the chokepoint and will need a calibration pass against a representative corpus sample.
- **Abstract quality is uneven by document type.** Papers and theses with explicit `Resumen` headings get clean abstracts; TPs and apuntes get a leading-paragraph fallback that looks rougher in result snippets. SPEC's UI ("abstract truncado ~2-3 líneas") absorbs this, and the author-override path is the safety valve. The headline-chunk embedding (ADR-0001 §3, ADR-0002 §7) consumes whatever abstract we produce; uneven quality propagates into "Trabajos relacionados" quality the same way.
- **YAKE keywords will sometimes be noisy.** Academic boilerplate ("este trabajo presenta…") slips through; the project blocklist is a maintenance artifact that grows over time. Acceptable trade against KeyBERT's per-doc TEI cost. The upgrade path is one function body inside the chokepoint.
- **Fecha extraction is genuinely fallible.** A 2003 scan with `/CreationDate=2024-03-15` and no cover-page year falls through to upload date if the author doesn't correct it. The "más recientes" sort and date filter inherit this fallibility — flagged explicitly so it isn't surprising when a sort-by-date result list contains a clearly-old document at the top.
- **Encrypted-PDF rejection is a synchronous validation, on the upload path.** This is a small but real exception to ADR-0003 §4's "in-request work only for pure DB writes" — the encrypted probe is an external-library call on the upload path. It is bounded (one-byte read), deterministic, and avoids the much worse UX of accepting an unindexable upload and notifying the author later that the version is `index_status='failed'`. The exception is intentional and named.
- **`index_status='failed'` is observable in-app, not over email.** This is consistent with SPEC §Notificaciones reserving email for critical events. A user uploading from outside the app (rare today; nonexistent in the SPEC) would not learn of the failure until they returned. Acceptable given the upload UX is always in-app.
- **`extract_pipeline_version` joins `embedding_model_version` (ADR-0002 §6) as a per-row reindex coordinate.** Two version axes now describe a chunk's provenance — pipeline output + embedding revision. A reindex driven by either bumps that axis only; the other axis stays stable. Mixed-state corpora during cutover are explicit, not silent.
- **Single-job pipeline assumes worker tolerance for long jobs.** If ADR-0008 picks a runner with rigid per-job timeouts (e.g., short-default RQ workers), the resolution is to split fast and slow queues at the runner level, not to refactor this ADR. The contract here is "one job per version, durable, completes or fails as a unit."
- **DOCX/ODT image-only documents will index empty.** The `empty_extraction_rate` metric catches this case; if it ever fires meaningfully, the path of least resistance is to extend the chokepoint with a per-format image-walk + Tesseract loop, not to change the architecture.
- **Five chokepoints, one pattern.** Search (introduced in ADR-0001 §9, formalised as `core/search_query.py` in ADR-0003 §3), embed (ADR-0002 §3), auth (ADR-0005 §3), blob IO (ADR-0006 §3), and now extraction (this ADR §1). The cost is one extra CI rule per chokepoint; the benefit is that "where does extraction happen?" — and equally "where does extraction never happen?" — always has exactly one answer.
