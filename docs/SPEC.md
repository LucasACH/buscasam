# BUSCASAM — Sistema de Búsqueda Académica

## Descripción general
BUSCASAM es un sistema de búsqueda de proyectos de investigación, trabajos prácticos y contenido académico relevante para la comunidad universitaria de UNSAM. Inspirado en Google Scholar Labs, permite ingresar consultas y obtener resultados pertinentes mediante búsqueda semántica.

## Objetivos
- Facilitar el acceso a producción académica de la facultad
- Superar la búsqueda trivial por palabras clave mediante comprensión semántica
- Centralizar publicaciones de estudiantes y docentes en una plataforma única

## Plataforma
Aplicación web accesible para estudiantes, docentes e invitados externos.

---

## Motor de búsqueda

### Input
- Caja de texto libre única (lenguaje natural)
- Filtros opcionales aplicados aparte. Cuando se aplican, son exclusivos (excluyen todo lo que cae fuera)
- Filtros disponibles: fecha, área de estudio, tipo de documento

### Output
- Lista paginada: 10 resultados por página, navegación con números de página al pie
- URL de búsqueda estable y reproducible (`/buscar?q=...&area=...&tipo=...&desde=...&pagina=...`)
- Cada resultado expone: título, autores, fecha, área, tipo de documento, abstract truncado (~2-3 líneas) y snippet del contenido donde matchea la consulta

### Ranking
- Híbrido: similitud semántica (embeddings) + match léxico (BM25)
- Sin boost por popularidad/recencia en el ranking principal
- Ordenamiento alternativo disponible: "más recientes" (ignora relevancia, ordena por fecha desc)

### Idioma
- Motor en español: modelo y pipeline optimizados para español
- Documentos en otros idiomas se aceptan e indexan con el mismo modelo. La calidad de búsqueda sobre ese contenido puede ser degradada — limitación explícita y documentada
- Los metadatos en español (título, abstract cargados por el autor) cubren el match principal en estos casos

### Búsqueda sin resultados
- Mensaje claro + sugerencias estáticas (probar otros términos, ajustar filtros)
- Si hay filtros aplicados: ofrecer "ver N resultados sin filtros"
- Mostrar documentos cercanos por debajo del threshold como "resultados relacionados"
- No hacer query expansion automática (preserva intención del usuario)

### Autocompletado
Mientras el usuario escribe en la caja de búsqueda, un dropdown muestra:
- Sugerencias de queries (historial del usuario + queries populares globales)
- Hits directos de documentos cuando el match es muy fuerte ("¿estás buscando *este trabajo*?")

---

## Corpus y documentos

### Origen
Solo contenido subido por usuarios de la plataforma (estudiantes y docentes). Sin importación de repositorios externos ni scraping.

### Modelo de documento
Cada documento combina:
- Metadatos estructurados: título, autores, abstract, área, tipo, fecha, palabras clave
- Texto completo extraído del archivo (vía OCR/parser) para indexación

### Formatos aceptados
- **Indexados**: PDF, DOCX, ODT
- **Adjuntos complementarios** (almacenados pero no indexados): CSV, código, imágenes

### Tipos de documento (enum cerrado)
Tesis, paper, trabajo práctico, proyecto de investigación, monografía, ponencia/poster, apunte/resumen, informe de cátedra.

### Áreas de estudio (jerarquía)
Estructura jerárquica institucional: Escuela → Carrera → Materia/Disciplina. El filtro permite seleccionar a cualquier nivel.

### Palabras clave
- Extraídas automáticamente del texto del documento
- Visibles en la página de detalle como tags clickeables (cada click ejecuta una búsqueda con esa keyword)
- No hay filtro dedicado a keywords (evita ruido por variantes léxicas)

---

## Publicación

### Flujo
- Formulario guiado para el estudiante/docente
- Carga del archivo principal y, opcionalmente, adjuntos complementarios
- Metadatos manuales mínimos: título, autores, área, tipo de documento
- Metadatos auto-extraídos: abstract, palabras clave, fecha

### Disponibilidad
- Publicación inmediata: tras procesar (OCR + indexar) el trabajo aparece en búsqueda sin revisión humana previa
- Moderación post-hoc reactiva (ver sección Moderación)

### Autores
- Pueden ser usuarios registrados (sugeridos desde la base) o externos (texto libre)
- Caso TP/trabajo grupal: el primer uploader crea la entrada y agrega a los co-autores, que reciben notificación y confirman. Evita duplicados.

### Visibilidad por trabajo
El autor elige al publicar:
- **Público**: visible para todos (incluidos invitados)
- **Interno UNSAM**: solo usuarios autenticados de la institución
- **Privado**: solo el autor y co-autores (drafts, material confidencial)

### Licencia
Implícita: "consulta y descarga para uso académico". No hay selector de licencia formal por trabajo.

### Edición
- Metadatos editables en cualquier momento por el autor
- Reemplazo de archivo crea una nueva versión (versionado informativo, historial visible)
- La búsqueda siempre usa la última versión

### Eliminación
- Soft delete: el trabajo deja de aparecer en búsqueda y de ser accesible públicamente
- Datos persisten en BD por un período (auditoría / recuperación)
- Comentarios y favoritos quedan asociados pero no visibles

---

## Usuarios

### Tipos
- **Estudiantes**: publican, buscan, comentan, marcan favoritos
- **Docentes**: mismas capacidades + moderación post-publicación (ver Moderación)
- **Invitados (externos a UNSAM)**: buscan, leen, descargan archivos públicos. No comentan, no favean, no publican

### Autenticación
- SSO institucional UNSAM para estudiantes y docentes
- El rol se deriva del directorio institucional (no es auto-declarado)
- Invitados navegan sin login

### Perfil
- Datos del SSO: rol, Escuela, carrera (si aplica)
- Cursos cursados/dictados: importados del sistema académico si está disponible
- Intereses declarados: el usuario marca áreas/temas opcionalmente

### Primer ingreso
- Sin onboarding: entrada directa a la home
- Recomendaciones funcionan desde el primer día con datos del SSO; mejoran cuando el usuario enriquece su perfil

### Historial de búsquedas
- El sistema lo guarda para alimentar recomendaciones
- El usuario tiene una vista de "mis búsquedas" con borrado individual y "borrar todo"
- Pausable

---

## Recomendaciones

### Home — "Recomendados para vos"
- Lista basada en historial de búsquedas + perfil académico (Escuela, carrera, intereses declarados)
- Actualización periódica

### Página de detalle — "Trabajos relacionados"
- Documentos similares al que se está viendo
- Calculado por similitud entre embeddings de documentos

### No personalización del ranking de búsqueda
Las recomendaciones nunca reordenan los resultados de búsqueda. La búsqueda es reproducible entre usuarios (modulo documentos nuevos indexados).

---

## Interacción social

### Favoritos
- Contador agregado público en cada documento ("guardado por N usuarios")
- Lista de favoritos privada (solo el dueño la ve)

### Comentarios
- Solo usuarios registrados (estudiantes y docentes)
- Threading de un nivel: comentarios pueden tener respuestas, pero sin anidamiento adicional
- Sin reacciones ni marcas especiales

### Notificaciones
- **In-app** (campanita) para todos los eventos relevantes
- **Email** para eventos críticos (invitación de co-autor) y opcional para comentarios, configurable por usuario

---

## Navegación y URLs

### URLs estables
- Búsquedas: URL reproducible incluyendo query, filtros y página
- Trabajos: URL permanente por ID, independiente de versiones

### Click en un resultado
Lleva a una página de detalle interna que muestra:
- Metadatos completos
- Abstract
- Comentarios y favoritos
- Botón para descargar/visualizar el archivo

### Browse sin búsqueda
Páginas navegables paginadas:
- Por Escuela/carrera (jerarquía de áreas)
- Por tipo de documento
- Por autor

### Click en un autor
- Autor registrado: lleva a una página "trabajos de este autor" — listado simple, sin bio ni perfil social
- Autor externo (texto libre): lleva a una búsqueda por ese nombre como string

---

## Moderación

### Reportes
- Cualquier usuario registrado puede reportar un trabajo o comentario
- Razones predefinidas: spam, contenido inadecuado, plagio, error

### Resolución
- Cualquier docente accede a la cola de reportes y decide ocultar o dejar
- Sin descentralización por Escuela (cualquier docente puede actuar sobre cualquier reporte)

### Auditoría y transparencia
- Cada acción de moderación queda registrada
- El autor del contenido afectado es notificado con la razón ("ocultado por [docente] — razón: ...")
- Posibilidad de apelar la decisión

---

## Resumen
BUSCASAM combina búsqueda semántica híbrida (embeddings + BM25), filtros estructurados, recomendaciones personalizadas, publicación guiada con co-autoría, e interacción social acotada (comentarios y favoritos) para que la comunidad de UNSAM encuentre y comparta producción académica de manera eficiente.
