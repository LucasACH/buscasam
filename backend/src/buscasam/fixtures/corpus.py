"""Committed fixture corpus for search MVP slice 1.

Covers every dimension the issue's acceptance criteria call out: three
visibilities, four lifecycle states (published, draft, soft-deleted,
moderation-hidden), area_path across all three levels, all eight document
types, fechas spanning multiple years, and at least one non-Spanish document.

Embeddings for `CHUNKS` live in the sibling `embeddings.npy` file and are
produced by `scripts/regenerate_fixture_embeddings.py` against a TEI
sidecar — tests never reach TEI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

EMBEDDING_MODEL_VERSION = "intfloat/multilingual-e5-large"


@dataclass(frozen=True)
class Document:
    id: int
    visibility: str
    publication_status: str
    titulo: str
    fecha: date
    area_path: str
    tipo: str
    abstract: str | None = None
    soft_deleted: bool = False
    moderation_hidden: bool = False


@dataclass(frozen=True)
class Chunk:
    id: int
    doc_id: int
    chunk_seq: int
    is_headline: bool
    body_text: str


DOCUMENTS: tuple[Document, ...] = (
    Document(
        id=1, visibility="publico", publication_status="published",
        titulo="Búsqueda híbrida en repositorios académicos",
        fecha=date(2024, 3, 15),
        area_path="escuela_ciencia.carrera_informatica.materia_bd",
        tipo="tesis",
        abstract="Estudio sobre fusión léxico-semántica con embeddings multilingües.",
    ),
    Document(
        id=2, visibility="publico", publication_status="published",
        titulo="Recuperación densa con e5 multilingüe",
        fecha=date(2023, 9, 1),
        area_path="escuela_ciencia.carrera_informatica.materia_bd",
        tipo="paper",
        abstract="Evaluación de embeddings densos sobre corpus en español.",
    ),
    Document(
        id=3, visibility="publico", publication_status="published",
        titulo="Trabajo práctico: árboles de decisión",
        fecha=date(2022, 6, 10),
        area_path="escuela_ciencia.carrera_informatica.materia_algoritmos",
        tipo="trabajo_practico",
        abstract="Implementación didáctica de ID3 sobre datasets pequeños.",
    ),
    Document(
        id=4, visibility="publico", publication_status="published",
        titulo="Lógica modal y semántica de mundos posibles",
        fecha=date(2024, 11, 5),
        area_path="escuela_humanidades.carrera_filosofia.materia_logica",
        tipo="proyecto_investigacion",
        abstract="Análisis formal de sistemas modales aplicados a epistemología.",
    ),
    Document(
        id=5, visibility="publico", publication_status="published",
        titulo="A survey of Argentine novel structures",
        fecha=date(2021, 4, 20),
        area_path="escuela_humanidades.carrera_letras.materia_literatura_argentina",
        tipo="monografia",
        abstract="A comparative study of narrative arcs in 20th-century Argentine fiction.",
    ),
    Document(
        id=6, visibility="publico", publication_status="published",
        titulo="Póster: Visualización de embeddings",
        fecha=date(2020, 8, 15),
        area_path="escuela_ciencia.carrera_informatica.materia_bd",
        tipo="ponencia_poster",
        abstract="Proyecciones UMAP de embeddings de documentos académicos.",
    ),
    Document(
        id=7, visibility="publico", publication_status="published",
        titulo="Apunte: complejidad de algoritmos de ordenamiento",
        fecha=date(2025, 1, 10),
        area_path="escuela_ciencia.carrera_informatica.materia_algoritmos",
        tipo="apunte_resumen",
        abstract="Resumen comparativo de quicksort, mergesort y heapsort.",
    ),
    Document(
        id=8, visibility="publico", publication_status="published",
        titulo="Informe de cátedra: rendimiento del curso de Lógica 2024",
        fecha=date(2024, 7, 22),
        area_path="escuela_humanidades.carrera_filosofia.materia_logica",
        tipo="informe_catedra",
        abstract="Análisis cuantitativo de notas y deserción en Lógica I.",
    ),
    Document(
        id=9, visibility="interno", publication_status="published",
        titulo="Memorando interno sobre indexación",
        fecha=date(2024, 5, 1),
        area_path="escuela_ciencia.carrera_informatica.materia_bd",
        tipo="paper",
        abstract="Notas internas sobre la pipeline de indexación.",
    ),
    Document(
        id=10, visibility="privado", publication_status="published",
        titulo="Borrador privado de tesis doctoral",
        fecha=date(2023, 12, 12),
        area_path="escuela_ciencia.carrera_informatica.materia_algoritmos",
        tipo="tesis",
        abstract="Investigación en curso, no compartir.",
    ),
    Document(
        id=11, visibility="publico", publication_status="draft",
        titulo="Borrador público sin publicar",
        fecha=date(2024, 2, 1),
        area_path="escuela_ciencia.carrera_informatica.materia_bd",
        tipo="paper",
        abstract=None,
    ),
    Document(
        id=12, visibility="publico", publication_status="published",
        titulo="Paper eliminado por el autor",
        fecha=date(2024, 4, 4),
        area_path="escuela_ciencia.carrera_informatica.materia_bd",
        tipo="paper",
        abstract="Paper que el autor decidió eliminar lógicamente.",
        soft_deleted=True,
    ),
    Document(
        id=13, visibility="publico", publication_status="published",
        titulo="Paper ocultado por moderación",
        fecha=date(2024, 6, 6),
        area_path="escuela_ciencia.carrera_informatica.materia_algoritmos",
        tipo="paper",
        abstract="Paper ocultado tras un reporte resuelto.",
        moderation_hidden=True,
    ),
    Document(
        id=14, visibility="publico", publication_status="published",
        titulo="Reglamento general de la Escuela de Ciencia y Tecnología",
        fecha=date(2023, 3, 1),
        area_path="escuela_ciencia",
        tipo="informe_catedra",
        abstract="Documento marco a nivel de escuela, sin carrera ni materia asociada.",
    ),
    Document(
        id=15, visibility="publico", publication_status="published",
        titulo="Plan de estudios — Licenciatura en Filosofía",
        fecha=date(2022, 11, 30),
        area_path="escuela_humanidades.carrera_filosofia",
        tipo="informe_catedra",
        abstract="Documento de carrera, sin materia asociada.",
    ),
)


def _doc_chunks(doc: Document, headline_id: int, body_id: int) -> tuple[Chunk, Chunk]:
    headline_text = doc.titulo if doc.abstract is None else f"{doc.titulo}. {doc.abstract}"
    body_text = doc.abstract or f"Contenido principal del documento {doc.id}."
    return (
        Chunk(id=headline_id, doc_id=doc.id, chunk_seq=0,
              is_headline=True, body_text=headline_text),
        Chunk(id=body_id, doc_id=doc.id, chunk_seq=1,
              is_headline=False, body_text=body_text),
    )


def _build_chunks() -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    cid = 1
    for doc in DOCUMENTS:
        h, b = _doc_chunks(doc, cid, cid + 1)
        chunks.append(h)
        chunks.append(b)
        cid += 2
    return tuple(chunks)


CHUNKS: tuple[Chunk, ...] = _build_chunks()
