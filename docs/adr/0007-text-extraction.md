# Text extraction pipeline: composed per-format, gated OCR, single chokepoint

## Status

Accepted

## Decision

Indexable text is extracted from PDF/DOCX/ODT via per-format libraries (`pdfminer.six`, `python-docx`, `odfpy`), with `ocrmypdf` (Tesseract on `spa+eng`) as a gated PDF fallback. All extraction and metadata suggestion logic lives behind `core/extract.py`. Initial extraction runs on the default worker; PDFs requiring OCR are handed to the dedicated OCR worker before OCR is invoked. Encrypted PDFs are rejected synchronously at upload; corrupted files fail asynchronously. Suggested metadata feeds ADR-0010 staged publication. The §6–7 abstract/keyword heuristics may be refined by an optional, off-by-default local LLM (ADR-0012); the heuristic remains the always-on fallback.

## Locked

1. Composed per-format, one chokepoint. All text extraction and metadata derivation lives in `core/extract.py`. Architecture tests ensure application indexing code calls this surface; packaging and tests may import dependencies directly.

2. Output contract:

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

   The chunker consumes `ExtractedDoc` and prefers paragraph boundaries when the ADR-0002 measured token budget allows, falling back to mid-paragraph splits only for oversized paragraphs. `page_breaks` is empty for DOCX/ODT.

3. PDF library: `pdfminer.six`. Pure Python, MIT, layout-aware reading order via `LAParams`. Paragraph reconstruction is a heuristic inside the chokepoint: group character blocks by vertical gap > median line-height, mark resulting boundaries in `paragraph_breaks`.

4. OCR: gate-then-`ocrmypdf`. For each PDF, run `pdfminer.six` first. If the extracted text has fewer than 100 characters per page averaged (configurable), invoke `ocrmypdf --skip-text --language spa+eng` to add a Tesseract text layer, then re-run `pdfminer.six` on the OCR'd output. Threshold tunable in `core/extract.py`. Metric `ocr_invocation_rate` logged. Tessdata for `spa` and `eng` (~25 MB) included in indexer container image.

5. DOCX: `python-docx`. ODT: `odfpy`. Both populate `paragraph_breaks` natively. Embedded scanned images inside DOCX/ODT are **not** OCR'd at MVP. Logged via `empty_extraction_rate`.

6. Abstract: layered heuristic, capped 300 words:
   1. Regex `^(Resumen|Abstract|Summary|Sinopsis)\b` (case-insensitive) within the first two pages; if matched, take subsequent text until next heading-like line or word cap.
   2. Else first 1–3 paragraphs of body text, truncated to word cap.
   3. If body is near-empty, `abstract = ""`.

   Stored as a suggestion for the staged publication form; author-editable before publish.

7. Keywords: YAKE. `lang='es'`, `n=8`, max n-gram 3, dedup ~0.7, with project-maintained blocklist filtering common academic-template noise (`"trabajo práctico"`, `"presente informe"`, `"este trabajo"`, …). Language is `'es'` always.

8. Fecha: best-effort heuristic, author-authoritative:
   1. Scan first two pages for `\b(19|20)\d{2}\b` near cover-page tokens (`tesis|trabajo|presentado|defendido|publicado|tesina`); pick most-recent plausible match in `[1970, current_year + 1]`.
   2. Fallback: PDF `/CreationDate` if plausible.
   3. Else `None` (caller writes upload date from `document_versions.uploaded_at`).

   Stored as a suggestion for the staged publication form; author-editable before publish.

9. Failure policy and schema.

   - Encrypted PDFs rejected synchronously at upload via one-byte `pdfminer` probe. On `PDFEncryptionError` → 415 "este PDF está protegido por contraseña — quitá la protección y reintentá". No `document_versions` row.
   - Corrupted newly uploaded candidate files fail async. Indexer catches `PDFSyntaxError`, `zipfile.BadZipFile`, etc.; candidate version is marked `index_status='failed'` with short `index_error`. Author receives in-app notification.
   - Empty body extraction is not a failure. Cleanly processed but empty produces no body chunks; publish still requires/creates the indexed headline chunk from author metadata. `empty_extraction_rate` metric.

   Schema extension to `document_versions`:

   ```sql
   ALTER TABLE document_versions ADD COLUMN
     index_status text NOT NULL DEFAULT 'pending',    -- 'pending' | 'processing' | 'indexed' | 'failed'
     index_error  text,
     indexed_at   timestamptz,
     extract_pipeline_version text NOT NULL DEFAULT 'unknown',
     staged_abstract text,
     staged_keywords text[],
     staged_fecha date,
     headline_fingerprint text;
   ```

   Reader search additionally requires ADR-0010 `publication_status='published'` and current chunks. Pending, failed, or staged candidate versions are owner-visible only in draft management. Reindex failure for an existing published current version leaves its prior indexed chunks/status active and records an operator failure; it does not convert published content into a failed candidate.

10. Pipeline tasks:
    - `index_document(version_id)` on `default`: DOCX/ODT complete there. For PDF, run `pdfminer` gate. If text is sufficient, complete there; if OCR is required, enqueue `ocr_index_document(version_id)` and exit without embedding partial output.
    - `ocr_index_document(version_id)` on `ocr`: run `ocrmypdf`, re-extract, derive metadata, chunk, embed, and write staged chunks transactionally. No intermediate cached OCR blob survives the task.
    - `refresh_headline(version_id)` on `default`: embed final edited headline text and update staged/current headline only if its metadata fingerprint is still current.

11. OCR jobs may reach approximately 30 minutes on CPU. ADR-0008 dedicates a concurrency-one `ocr` worker; default jobs never execute OCR. All indexing tasks are retry-safe and use execution locks.

12. Provenance: `extract_pipeline_version`. Single compound version string sourced from `EXTRACT_PIPELINE_VERSION` (in `pyproject.toml` / env), stored per `document_versions` row. Bump is a deliberate operator action paired with a reindex window.

13. Metadata edits and publish follow ADR-0010: candidate-version staged metadata appears after first/replacement processing, edits can trigger fast headline reindex, and only an indexed candidate with a matching headline fingerprint can become current/public. Operator reindex of an already published current version never overwrites author-approved `documents` metadata; it rebuilds body/headline indexes from the existing persisted values.
