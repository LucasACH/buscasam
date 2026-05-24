# BUSCASAM

Sistema de búsqueda académica para la comunidad universitaria de UNSAM. Inspirado en Google Scholar Labs, permite encontrar tesis, papers, trabajos prácticos y demás producción académica mediante búsqueda semántica.

---

## Qué hace

- **Búsqueda híbrida** en español: similitud semántica (embeddings) + match léxico (BM25)
- **Corpus propio**: solo contenido subido por estudiantes y docentes de UNSAM
- **Publicación guiada** con co-autoría, versionado y visibilidad configurable (público / interno / privado)
- **Recomendaciones personalizadas** basadas en historial y perfil académico
- **Interacción social acotada**: favoritos y comentarios de un nivel
- **Moderación post-hoc** reactiva por parte del cuerpo docente

Detalle completo de comportamiento en [docs/SPEC.md](docs/SPEC.md).

---

## Estado

En desarrollo inicial. Sin código aún — el repositorio contiene la especificación y el workflow de trabajo.

---

## Documentación

- [docs/SPEC.md](docs/SPEC.md) — especificación funcional (qué hace el sistema)
- [docs/WORKFLOW.md](docs/WORKFLOW.md) — flujo de trabajo y principios de desarrollo
- [CONTRIBUTING.md](CONTRIBUTING.md) — cómo llevar una feature o bug de idea a PR mergeado
- [CLAUDE.md](CLAUDE.md) — instrucciones para agentes que trabajan sobre el código

---

## Contribuir

Leer [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir issues o PRs.
