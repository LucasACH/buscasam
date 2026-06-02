# BUSCASAM

Sistema de búsqueda académica para la comunidad universitaria de UNSAM. Inspirado en Google Scholar Labs, permite encontrar tesis, papers, trabajos prácticos y demás producción académica mediante búsqueda semántica.

En producción en [buscasam.org](https://buscasam.org).

---

## Qué hace

- **Búsqueda híbrida** en español: similitud semántica (embeddings) + ranking full-text de PostgreSQL, fusionados con RRF y un piso semántico con anclaje léxico
- **Corpus propio**: solo contenido subido por estudiantes y docentes de UNSAM (acceso restringido por dominio vía Google OAuth)
- **Publicación por etapas** con co-autoría, revisión, versionado y visibilidad configurable
- **Moderación post-hoc** de documentos por parte del cuerpo docente

Detalle completo de comportamiento en [docs/SPEC.md](docs/SPEC.md).

---

## Estado

En producción y en evolución activa. El núcleo (búsqueda, publicación, co-autoría, versionado, moderación) está desplegado; quedan features diferidas (favoritos, comentarios, autocompletado, apelaciones) y mejoras incrementales. Ver [docs/adr/](docs/adr/) para las decisiones tomadas.

---

## Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy async, PostgreSQL + `pgvector`
- **Embeddings**: `intfloat/multilingual-e5-large` servido por TEI (CPU); metadata LLM opcional vía Vertex/Gemini, apagado por defecto
- **Frontend**: Next.js, React, TypeScript
- **Infraestructura**: Terraform sobre GCP, Docker Compose, scripts de despliegue

---

## Estructura

```
backend/    API FastAPI, búsqueda, publicación, moderación, extracción de metadatos
frontend/   App Next.js (buscar, mis-trabajos, moderación)
infra/      Terraform (GCP), Docker Compose y scripts de despliegue
docs/       Especificación, ADRs, module maps y runbooks
```

---

## Desarrollo agéntico

La idea fue construir un codebase completamente agéntico: desarrollado de punta a punta por agentes de IA, bajo guías y workflows estrictos que mantienen la calidad (entendimiento compartido antes de specs, slices verticales, módulos profundos, revisión como compuerta de merge). Inspirado en el workshop de Matt Pocock: [AI-assisted development](https://www.youtube.com/watch?v=-QFHIoCo-Ko). El detalle vive en [docs/WORKFLOW.md](docs/WORKFLOW.md) y [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Documentación

- [docs/SPEC.md](docs/SPEC.md) — especificación funcional (qué hace el sistema)
- [docs/local-dev.md](docs/local-dev.md) — levantar el entorno de desarrollo local
- [docs/WORKFLOW.md](docs/WORKFLOW.md) — flujo de trabajo y principios de desarrollo
- [docs/production-launch.md](docs/production-launch.md) — runbook operativo de producción
- [docs/adr/](docs/adr/) — decisiones de arquitectura (ADRs)
- [docs/module-maps/](docs/module-maps/) — mapas de módulos de cada flujo
- [CONTRIBUTING.md](CONTRIBUTING.md) — cómo llevar una feature o bug de idea a PR mergeado
- [CLAUDE.md](CLAUDE.md) — instrucciones para agentes que trabajan sobre el código

---

## Contribuir

Leer [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir issues o PRs.

---

## Licencia

[MIT](LICENSE) © 2026 Lucas Achaval
