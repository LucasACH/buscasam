# Text extraction pipeline: composed per-format, gated OCR, single chokepoint

## Status

Accepted

## Decision

Indexable text extracted from PDF/DOCX/ODT via per-format pure-Python libraries (`pdfminer.six`, `python-docx`, `odfpy`), with `ocrmypdf` (Tesseract on `spa+eng`) as a gated fallback when PDF text is near-zero. All behind `core/extract.py`. The module exposes an `ExtractedDoc` (text + paragraph + page offsets + raw metadata) plus `derive_metadata()` for abstract / keywords / fecha. Extraction runs inside one `index_document(version_id)` job. Encrypted PDFs rejected synchronously at upload; corrupted files fail async with `index_status='failed'`. Compound `extract_pipeline_version` on `document_versions`.

## Locked

1. Composed per-format, one chokepoint. All text extraction and metadata derivation lives in `core/extract.py`. CI grep bans imports of `pdfminer`, `pypdf`, `ocrmypdf`, `python_docx`, `docx`, `odfpy`, `pytesseract`, and `yake` outside `core/extract.py` (excluding tests).

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

   The chunker consumes `ExtractedDoc` and prefers paragraph boundaries when the token budget allows, falling back to mid-paragraph splits only when a single paragraph exceeds the 510-token budget. `page_breaks` is empty for DOCX/ODT.

3. PDF library: `pdfminer.six`. Pure Python, MIT, layout-aware reading order via `LAParams`. Paragraph reconstruction is a heuristic inside the chokepoint: group character blocks by vertical gap > median line-height, mark resulting boundaries in `paragraph_breaks`.

4. OCR: gate-then-`ocrmypdf`. For each PDF, run `pdfminer.six` first. If the extracted text has fewer than 100 characters per page averaged (configurable), invoke `ocrmypdf --skip-text --language spa+eng` to add a Tesseract text layer, then re-run `pdfminer.six` on the OCR'd output. Threshold tunable in `core/extract.py`. Metric `ocr_invocation_rate` logged. Tessdata for `spa` and `eng` (~25 MB) included in indexer container image.

5. DOCX: `python-docx`. ODT: `odfpy`. Both populate `paragraph_breaks` natively. Embedded scanned images inside DOCX/ODT are **not** OCR'd at MVP. Logged via `empty_extraction_rate`.

6. Abstract: layered heuristic, capped 300 words:
   1. Regex `^(Resumen|Abstract|Summary|Sinopsis)\b` (case-insensitive) within the first two pages; if matched, take subsequent text until next heading-like line or word cap.
   2. Else first 1–3 paragraphs of body text, truncated to word cap.
   3. If body is near-empty, `abstract = ""`.

   Pre-filled in publication form, author-editable.

7. Keywords: YAKE. `lang='es'`, `n=8`, max n-gram 3, dedup ~0.7, with project-maintained blocklist filtering common academic-template noise (`"trabajo práctico"`, `"presente informe"`, `"este trabajo"`, …). Language is `'es'` always.

8. Fecha: best-effort heuristic, author-authoritative:
   1. Scan first two pages for `\b(19|20)\d{2}\b` near cover-page tokens (`tesis|trabajo|presentado|defendido|publicado|tesina`); pick most-recent plausible match in `[1970, current_year + 1]`.
   2. Fallback: PDF `/CreationDate` if plausible.
   3. Else `None` (caller writes upload date from `document_versions.uploaded_at`).

   Pre-filled in publication form, author-editable.

9. Failure policy and schema.

   - Encrypted PDFs rejected synchronously at upload via one-byte `pdfminer` probe. On `PDFEncryptionError` → 415 "este PDF está protegido por contraseña — quitá la protección y reintentá". No `document_versions` row.
   - Corrupted files fail async. Indexer catches `PDFSyntaxError`, `zipfile.BadZipFile`, etc.; version marked `index_status='failed'` with short `index_error`. Author receives in-app notification (not email — email reserved for "eventos críticos").
   - Empty extraction is NOT a failure. Cleanly-processed-but-empty → `index_status='indexed'` with no chunks. `empty_extraction_rate` metric.

   Schema extension to `document_versions`:

   ```sql
   ALTER TABLE document_versions ADD COLUMN
     index_status text NOT NULL DEFAULT 'pending',    -- 'pending' | 'indexed' | 'failed'
     index_error  text,
     indexed_at   timestamptz,
     extract_pipeline_version text NOT NULL DEFAULT 'unknown';
   ```

   Search chokepoint is **not** modified: a `pending` or `failed` version has no rows in `chunks`, so the existing chunk join already excludes it.

10. Single-job pipeline. Extraction runs inside one `index_document(version_id)` worker job: read blob → try `pdfminer` → if low-yield, run `ocrmypdf` → re-extract → derive metadata → chunk → embed → write chunks transactionally. No intermediate cached OCR blob.

11. Inputs to ADR-0008 (async job runner). Per-job duration may reach ~30 minutes for scanned-thesis OCR on CPU. Runner must either tolerate jobs of that length without timing out, or provide priority/separate queue capability so OCR-heavy jobs do not head-of-line-block fast born-digital jobs.

12. Provenance: `extract_pipeline_version`. Single compound version string sourced from `EXTRACT_PIPELINE_VERSION` (in `pyproject.toml` / env), stored per `document_versions` row. Bump is a deliberate operator action paired with a reindex window.

13. SPEC clarifications:
    - **§Publicación / Metadatos auto-extraídos.** Abstract, palabras clave, and fecha are "pre-llenados automáticamente, editables por el autor."
    - **§Publicación / fecha.** "Fecha estimada del trabajo (no de la subida), pre-llenada automáticamente y editable por el autor."
