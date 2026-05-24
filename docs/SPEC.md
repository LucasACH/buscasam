# BUSCASAM - Sistema de Búsqueda Académica

## Alcance MVP

BUSCASAM permite publicar y encontrar trabajos académicos subidos por la comunidad UNSAM.

Incluye:
- autenticación institucional;
- borradores, procesamiento, publicación y reemplazo versionado;
- coautoría con aceptación y notificaciones de invitación;
- búsqueda híbrida, filtros, detalle, descarga y trabajos relacionados;
- reporte y ocultamiento moderado de documentos.

Queda fuera del MVP:
- recomendaciones personalizadas e intereses;
- historial de búsquedas y autocompletado;
- favoritos y comentarios;
- emails opcionales y preferencias, excepto la invitación de coautor;
- páginas de navegación por autor/área/tipo separadas de la búsqueda;
- apelaciones dentro de la plataforma.

---

## Búsqueda

### Entrada
- Caja de texto libre única.
- Filtros opcionales: fecha, área de estudio y tipo de documento.
- URL reproducible: `/buscar?q=...&area=...&tipo=...&desde=...&pagina=...`.

### Salida
- Lista de 10 resultados por página; relevancia limitada a las primeras 20 páginas.
- Cada resultado: título, autores, fecha, área, tipo, abstract truncado y snippet.
- Orden alternativo "más recientes", sin límite de relevancia.

### Ranking
- Híbrido: embeddings multilingües + ranking full-text de PostgreSQL en español.
- Fusión por Reciprocal Rank Fusion; sin boost por popularidad o recencia.
- Se muestra un resultado si hay match léxico o si supera el piso semántico calibrado antes del lanzamiento.
- Si no hay resultados sobre el piso, se informa claramente y se sugieren cambios de consulta/filtros.
- Con filtros activos, se puede consultar el conteo sin filtros aplicando la misma visibilidad.

### Idioma
- Pipeline de texto en español; documentos en otros idiomas se aceptan con calidad potencialmente menor.
- Título y abstract ingresados/revisados por el autor también se indexan.

---

## Documentos

### Contenido
- Metadatos: título, autores, abstract, área, tipo, fecha y palabras clave.
- Archivo principal indexado: PDF, DOCX u ODT.
- Hasta cinco adjuntos no indexados: CSV, código, imágenes y formatos permitidos.
- Tipos cerrados: tesis, paper, trabajo práctico, proyecto de investigación, monografía, ponencia/poster, apunte/resumen, informe de cátedra.
- Áreas jerárquicas: Escuela -> Carrera -> Materia/Disciplina.

### Visibilidad
- `publico`: visible y descargable por cualquier visitante.
- `interno`: visible y descargable por usuarios UNSAM autenticados.
- `privado`: visible y descargable solo por autor propietario y coautores aceptados.
- Un borrador aún no publicado, un documento eliminado u ocultado y el contenido de una versión candidata fallida no aparecen en lecturas normales.

### Versiones
- Reemplazar archivo crea una versión candidata nueva.
- La versión publicada anterior continúa disponible mientras la nueva se procesa y revisa.
- Solo una versión procesada y confirmada por el autor pasa a ser la versión pública actual.
- El historial de versiones es descargable solo por autores aceptados/propietario.

---

## Publicación

### Flujo
1. Usuario autenticado crea borrador con título, autores, área, tipo y visibilidad.
2. Sube archivo principal; la API responde `202` y procesa fuera del request.
3. El sistema extrae texto y sugiere abstract, palabras clave y fecha del trabajo.
4. El autor revisa o edita sugerencias. Si cambia título/abstract, el índice de encabezado se regenera antes de habilitar publicación.
5. El autor publica; recién entonces el documento aparece en búsqueda, detalle y descarga según visibilidad.

### Estados
- El documento es `draft` hasta su primera publicación y luego permanece `published` mientras exista una versión pública.
- La versión candidata puede estar `processing`, `processing_failed` o `ready_to_publish`.
- Al reemplazar un archivo publicado, la versión pública anterior sigue accesible mientras la candidata se procesa o falla.

### Autores
- El uploader es propietario.
- Un coautor registrado invitado recibe notificación in-app/email y queda pendiente hasta aceptar; antes de aceptar no obtiene acceso privado ni permisos de edición.
- Un autor externo se muestra como atribución de texto y no obtiene permisos.

### Eliminación
- El autor puede eliminar lógicamente un documento; deja de ser accesible inmediatamente.
- Puede restaurarlo durante 180 días; después se purga.
- Ocultamiento por moderación es un estado separado y no inicia purga.

---

## Usuarios Y Autenticación

### Invitado
- Busca, ve y descarga documentos `publico`.
- No publica ni reporta.

### Estudiante
- Cuenta Google Workspace con `hd = estudiantes.unsam.edu.ar`.
- Publica, busca, acepta coautoría y reporta documentos accesibles.

### Docente
- Cuenta Google Workspace con `hd = unsam.edu.ar`.
- Mismas capacidades que Estudiante más moderación.
- Representa personal UNSAM confiable para este producto, no necesariamente cargo docente literal.

### Sesión
- Login solo con Google UNSAM.
- Sesión expira tras 30 días sin actividad o 90 días desde login, lo que ocurra primero.
- La bandeja in-app contiene invitaciones de coautoría y avisos de procesamiento/moderación; el usuario puede marcarlos como leídos.

---

## Detalle Y Relacionados

- URL permanente `/docs/{id}`, independiente de versiones.
- Muestra metadatos, abstract, palabras clave y descarga del archivo actual/adjuntos.
- "Trabajos relacionados" compara encabezados indexados y aplica exactamente la misma política de acceso que el detalle.
- Ninguna respuesta, sitemap o conteo revela documentos no autorizados.

---

## Moderación MVP

- Un usuario autenticado puede reportar un documento publicado que puede leer: spam, contenido inadecuado, plagio o error.
- Cualquier Docente puede revisar reportes y ocultar o volver a mostrar un documento.
- Cada acción registra docente, razón y fecha; el autor recibe notificación in-app.
- Un Docente solo inspecciona contenido no visible mediante endpoints de moderación asociados al reporte.
- La apelación en producto queda fuera del MVP.

---

## Criterios De Aceptación

- Invitado no observa documentos internos, privados, borradores no publicados, ocultos ni eliminados por búsqueda, detalle, relacionados, descarga, conteos o sitemap.
- Una versión candidata fallida no oculta la versión publicada anterior.
- Coautor pendiente no accede a un documento privado; coautor aceptado sí.
- Publicar o reemplazar nunca expone una versión sin indexar.
- Si el servicio semántico no responde, la búsqueda léxico-only sigue disponible.
- Backup restaurable y benchmark de búsqueda/OCR sobre la VM se validan antes del lanzamiento.
