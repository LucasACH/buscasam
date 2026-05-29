"""Shared blob-download transport for the API edge.

The single place the dual-mode projection lives: nginx `X-Accel-Redirect` in
prod (empty body), inline `FileResponse` for local dev (`serve_blobs_inline`).
Both `api/docs` and `api/moderation` hand a blob off through here so the
projection cannot drift between routers.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import Response
from fastapi.responses import FileResponse

from buscasam.core import blob_store
from buscasam.settings import settings


def content_disposition(original_filename: str) -> str:
    encoded = quote(original_filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


def download_response(*, sha_hex: str, original_filename: str, mime: str) -> Response:
    # Prod ships an empty body and lets nginx serve the file via
    # X-Accel-Redirect. Local-dev runs uvicorn directly without nginx, so
    # `serve_blobs_inline` flips to streaming the blob from disk instead.
    if settings.serve_blobs_inline:
        return FileResponse(
            blob_store.local_path(sha_hex),
            media_type=mime,
            headers={"Content-Disposition": content_disposition(original_filename)},
        )
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": blob_store.internal_path(sha_hex),
            "Content-Type": mime,
            "Content-Disposition": content_disposition(original_filename),
        },
    )
