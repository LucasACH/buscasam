# ADR-0009 §2: backend image. Four containers run from it (api, worker_default,
# worker_ocr, backup); the entrypoint is set per-service in compose.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ARG UID=1000
ARG GID=1000

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

# OS packages: text extraction + OCR (ADR-0007), libmagic sniffing, and the
# backup tooling (postgresql-client + rsync, ADR-0009 §11). ocrmypdf pulls in
# ghostscript + qpdf at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
        libmagic1 poppler-utils ghostscript qpdf \
        postgresql-client rsync curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g "${GID}" buscasam && useradd -u "${UID}" -g "${GID}" -m buscasam

WORKDIR /app

# Cached dependency layer: resolve from the lockfile before copying sources.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra ocr

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra ocr

USER buscasam
EXPOSE 8000
CMD ["uvicorn", "buscasam.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
