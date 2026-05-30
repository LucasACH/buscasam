# BUSCASAM — Claude Design Handoff

Handoff package for redesigning the BUSCASAM frontend in **Claude Design**.

**Locked decisions**
- Theme: **light only** (do not design dark mode; leave dark CSS tokens untouched).
- Color: neutral base + **single deep-blue accent**.
- Search: **hero landing** when no query → **compact slim search bar** once results show.
- Layout: **single top-bar, centered single column** everywhere (no sidebar).
- Aesthetic: **modern minimal** (Linear / Vercel restraint). No AI-slop: no gradients-on-everything, no glassmorphism, no purple-blob illustrations, no oversized rounded cards, no emoji.
- Device: **desktop-first, mobile solid**.
- Logo: design a **simple typographic wordmark** for BUSCASAM.
- Empty states: **lucide icon + short text + CTA** (shadcn `empty`). No spot illustrations.
- Motion: **subtle & purposeful** — skeletons, fade/slide-in, press feedback, popover/progress transitions. Nothing decorative.

**Hard constraints (must survive the redesign)**
- Stack is **Next.js 16 + React 19 + Tailwind v4 + shadcn (`radix-nova` style) + Geist font**. Keep shadcn component bones; restyle, don't replace the architecture.
- All **UI copy stays in Spanish** exactly as written in the current app. Redesign visuals, not strings (unless a string is explicitly flagged below).
- Preserve every **functional state** the code already handles — listed per screen. Don't drop states for prettiness.
- Accessibility: keep `aria-*`, `role`, focus-visible rings, `sr-only` labels. Minimum 4.5:1 text contrast.

---

## How to use this package

1. Paste the **§B Foundations** prompt first. Let Design establish the design system.
2. Then paste **one §C screen prompt at a time**. Iterate before moving on.
3. Keep the foundations output pinned — every screen references it.

> **No current-state screenshots.** The existing UI is a bare wireframe; feeding it to Claude Design would anchor it to that and produce a reskin instead of a redesign. Every screen's layout, states, and exact Spanish copy is written into the prompts below — that's the ground truth Design needs.

---

## §A. Reference images (optional, aspirational only)

Do **not** upload screenshots of the current app. If you attach any images, make them **aspirational** — products whose visual language you want Design to echo:
- **Linear**, **Vercel dashboard** — the modern-minimal restraint we're targeting.
- **Google Scholar Labs** — the academic-search framing.

If you attach one, label it: *"aspirational reference — match this language, not literal layout."* Otherwise the prompts stand alone.

---

## §B. Foundations prompt (paste first)

```
You are redesigning BUSCASAM — an academic search portal for the UNSAM university community in Argentina (Spanish UI). Think Google Scholar Labs, rebuilt with the restraint of Linear and Vercel. Audience: students and faculty searching, publishing, and moderating academic work (theses, papers, trabajos prácticos).

Establish a design system. Aesthetic target: MODERN MINIMAL — confident, quiet, editorial-grade. Explicitly avoid generic "AI dashboard" look: no heavy gradients, no glassmorphism, no neon, no purple blobs, no oversized rounded cards, no decorative illustrations, no emoji. Every visual choice earns its place.

THEME: light mode only.

STACK (keep these bones): Next.js + React + Tailwind v4 + shadcn/ui (radix-nova style) + Geist Sans (Geist Mono for IDs/code). Use shadcn components as the structural base and restyle them; do not invent a parallel component system.

COLOR — neutral base + a single deep-blue accent:
- Background pure white; cards white; surfaces use very light neutral grays (current OKLCH neutral ramp).
- Borders hairline, low-contrast (~#E5E7EB equivalent).
- Primary / accent = deep blue. Use ~#1D4ED8 (hover #1E40AF, OKLCH ≈ oklch(0.49 0.20 264)). Apply to: primary buttons, links, active filter/segment, focus ring, progress fill, selected states, notification badge.
- Text: near-black (#171717) primary, mid-gray (#6B7280) secondary.
- Destructive stays red (delete/hide/error).
- Status accents, used sparingly as soft tinted badges: amber for "processing/pending", green for "published/accepted/ready", red for "hidden/failed", neutral for "draft". Tinted bg + readable text, never saturated fills.
- Search keyword highlight (<mark>): soft amber bg (#FEF3C7), dark text — keep readable, don't use the blue accent here.

TYPOGRAPHY:
- Geist Sans throughout. Tight tracking on headings.
- Scale: hero/display 40–48px; page H1 26–30px; section H2 18–20px; body 14–15px; meta/caption 12–13px. Comfortable line-height for abstracts (reading).
- One weight step between hierarchy levels; avoid more than 3 weights on a screen.

SPACING / SHAPE:
- 8px grid. Generous whitespace; let content breathe.
- Radius ~10px base (cards/inputs), full-round for pills/badges/avatars.
- Shadows: almost none. Rely on hairline borders + spacing. At most a faint shadow on popovers/dialogs.
- Content column centered, max-width ~768px for reading screens (search results, doc detail, forms), wider only where noted.

WORDMARK: design a clean typographic wordmark "BUSCASAM" (consider a small geometric mark — a minimal magnifier/document glyph in the deep blue). Works at 24–28px in the header. Deliver the lockup.

MOTION (subtle, purposeful — Linear-like):
- Skeleton loaders for every async list/detail (shadcn skeleton).
- Lists/cards fade-and-rise in (~150–220ms, small stagger, ease-out).
- Buttons: gentle press scale (~0.98) + state-color transition.
- Popovers/dialogs: fade + 4px scale-in.
- Progress bars animate width smoothly.
- Respect prefers-reduced-motion.

STATES — design every component for: default, hover, focus-visible (blue ring), active/selected, disabled, loading (skeleton), empty, error. Never ship a list without its empty + loading + error variant.

EMPTY STATES: shadcn `empty` pattern — one muted lucide line-icon, a short Spanish message, and a primary CTA when an action exists. Calm, not cute.

COMPONENT KIT to lean on (shadcn): button, button-group, input, input-group, textarea, field, label, select/native-select, radio-group, checkbox, badge, card, item, popover, command (for searchable pickers), dialog, alert-dialog, dropdown-menu, tabs, toggle-group (segmented control), skeleton, spinner, progress, sonner (toasts), avatar, breadcrumb, pagination, separator, scroll-area, tooltip, empty.

DELIVERABLE: a foundations sheet — color tokens (with hex + OKLCH), type scale, spacing, radii, the wordmark lockup, button variants (primary/secondary/outline/ghost/destructive + sizes), input/field, badge variants (the status set above), card, list-row (item), pill/segmented control, popover, skeleton, and the empty-state template. Keep Spanish sample copy.

All subsequent prompts build on this system. Keep all UI copy in Spanish.
```

---

## §C. Per-screen prompts

Paste one at a time. Each assumes the §B foundations are in effect. (The bracketed numbers in headings are legacy references — ignore them.)

### C1 — Header & navigation (global) · `21`,`22`,`23`
```
Redesign the global top header (applies to every page). Single slim bar, white, hairline bottom border, sticky.

Layout: left = BUSCASAM wordmark (links to /buscar). Right = primary nav + user cluster.
- Guest (logged out): a single "Iniciar sesión con UNSAM" link/button on the right.
- Authenticated: nav links "Mis trabajos" and (docente only) "Moderación"; then the notification bell; then a user menu.
- User cluster: avatar (image or initial fallback), name, a small role label ("Estudiante"/"Docente"). Move "Cerrar sesión" into a dropdown-menu opened from the avatar/name (cleaner than an inline link). Keep it reachable in ≤1 click.
- Active nav item gets a subtle indicator (weight + blue underline/accent).

Notification bell: lucide bell, with a small deep-blue count badge (min-width pill, "9+" overflow). Opening marks all read (existing behavior). Mobile: collapse nav into a menu (sheet or dropdown); keep bell + avatar visible.

Keep Spanish copy. Deliver desktop + mobile header, guest + auth states, and the avatar dropdown.
```

### C2 — Notifications panel (Bandeja) · `23`
```
Redesign the notification popover (opened from the header bell). Width ~360px, max-height with internal scroll-area, hairline divided rows.

Each row = one notification. Unread rows have a subtle blue-tinted left accent or dot; read rows are plain. Four kinds (keep exact Spanish copy + actions):
1) coauthor_invite — "{inviter} te invitó como coautor en «{doc}»" + inline actions Aceptar / Rechazar / Ver (only while unread).
2) document_hidden — "Tu documento «{doc}» fue ocultado. Motivo: …"
3) document_unhidden — "Tu documento «{doc}» fue restaurado. …"
4) processing_failed — "Falló el procesamiento de «{doc}»."
Each unread row also has a small "Marcar como leída". Footer: "Marcar todas como leídas" (only when any unread).
Use a small kind-icon per row (lucide: user-plus, eye-off, rotate-ccw, alert-triangle) in muted tone.

States: empty ("No tenés notificaciones." — centered, muted icon), list, loading skeleton (3 rows). Subtle fade-in on open. Keep it scannable, dense but calm.
```

### C3 — Login · `01`,`02`
```
Redesign the login page. Centered, generous vertical breathing room, max-width ~400px card or borderless centered block (your call — minimal).

Content: BUSCASAM wordmark, a one-line value prop ("Búsqueda de trabajos académicos de la UNSAM."), and a single primary button "Iniciar sesión con UNSAM" (add the Google "G" mark to the button — it's Google OAuth). 
Error variant (?error=not_unsam): show a calm inline alert above the button — "Solo cuentas @unsam.edu.ar, @estudiantes.unsam.edu.ar o @unsam-bue.edu.ar pueden ingresar." — and the button label becomes "Probar otra cuenta".

No social-media clutter, no extra fields (OAuth only). Use the shadcn login-block bones but strip to this. Deliver default + error states, desktop + mobile.
```

### C4 — Search landing (no query) · `03`
```
Design the no-query state of /buscar as a focused HERO landing (not a marketing page).

Centered vertically in the viewport: BUSCASAM wordmark/lockup, a short tagline (e.g. "Encontrá tesis, papers y trabajos de la comunidad UNSAM"), and a LARGE primary search input — the hero element. Placeholder: "Buscar por título, tema, autor…". Search icon inside the input; submit on enter.

Below the input, optionally: a slim row of example/quick entry points — a few document-type chips (Tesis, Paper, Trabajo práctico, …) and/or "Explorar por área" — that pre-fill a search. Keep it minimal and obviously optional; don't turn it into a dashboard.

This is the brand moment — make the search bar feel premium and inviting, lots of whitespace, one accent (the focused input ring + search button in deep blue). Deliver desktop + mobile.
```

### C5 — Search results · `04`,`05`,`06`
```
Design the results state of /buscar (after a query, or when "Recientes" order is active). The hero collapses: search input moves to a SLIM sticky bar near the top (full-width-of-column, search icon, current query editable), with the filter row directly under it.

FILTER ROW (keep all controls + behavior):
- Order: segmented control (toggle-group) "Relevancia | Recientes".
- Área: outline button → popover with the cascading Escuela › Carrera › Materia selector; shows selected area label as a breadcrumb; "Quitar área" to clear.
- Tipo: outline button "Tipo (n)" → popover multi-select checklist of the 8 document types.
- Año: outline button → popover with Desde / Hasta numeric range.
- "Limpiar" (ghost, with X) appears only when any filter is active.
Active filters should read clearly — consider the trigger buttons taking a filled/blue-tinted state when set. Keep popovers; make them feel crisp (command-style where it helps).

RESULT COUNT line: "{n} resultados" (or "Buscando…" while loading, error text on failure).

RESULT CARD (list, ~12px gap): title (link, prominent, deep-blue on hover/underline) → authors (muted, comma list) → meta row (year · área path · tipo · optional visibility badge "Interno"/"Privado") → truncated abstract (~280 chars) and/or highlighted snippet (<mark> = soft amber). Card = hairline border, white, hover lifts subtly (border darken / faint shadow). Whole card title clickable to /docs/{id}.

PAGINATION: shadcn pagination — Anterior / "Página X de Y" / Siguiente. Relevance order caps at 20 pages.

STATES:
- Loading: 5–6 result-card skeletons (title bar + 3 meta lines + abstract lines).
- Empty (0 results): shadcn empty pattern — muted search-off icon, "No encontramos resultados", a helpful line suggesting to change the query or filters, and a "Limpiar filtros" action when filters are set.
- Error: calm inline message.
Results fade-and-rise in with a small stagger. Deliver: results desktop, results mobile, both filter popovers (Área cascader + Tipo), empty state.
```

### C6 — Document detail · `07`,`08`,`09`
```
Redesign /docs/{id} — the permanent document page. Reading-first, two-column on desktop (main content + right aside), single column stacked on mobile.

MAIN (left, ~2/3): title (large H1), authors line, a metadata definition list (Autores, Área [resolved Escuela › Carrera › Materia], Tipo, Fecha, Visibilidad badge when not público). Then "Resumen" section (comfortable reading measure + line-height) and "Palabras clave" as pill badges.

ASIDE (right, ~1/3, sticky on desktop):
- "Archivo principal": a file row (filename, file-type icon, size if available) with a primary "Descargar" action.
- "Adjuntos": list of attachment rows (same treatment), download each.
- "Editar" button (only if manageable).
- "Versiones anteriores" panel (only if manageable): list rows "v{n} · filename · size · date · (actual)", each with Descargar; inline error on a failed download.
- "Reportar" — opens the report popover (see C12).

BOTTOM: "Trabajos relacionados" — heading + a vertical list reusing the search result card.

INVITE VARIANTS (a pending coauthor viewing the doc):
- banner variant: a strip above the metadata — "{inviter} te invitó como coautor en «{título}». ¿Aceptar o rechazar?" with Aceptar (primary) / Rechazar (ghost). The full detail shows below it.
- minimal variant (privado doc the invitee can't read yet): the page body is ONLY that invitation card, centered, max-width ~440px — no metadata, abstract, files, related, or versions. This is a privacy requirement: design the minimal card to stand alone.

STATES: loading skeleton (title + meta + abstract + aside), the two invite variants. File/attachment rows get hover affordance. Deliver: full detail desktop, detail mobile, banner-invite, minimal-invite.
```

### C7 — Mis trabajos (list) · `10`,`11`
```
Redesign /mis-trabajos. Page header: "Mis trabajos" + right-aligned actions: "Papelera" (secondary link) and "Nuevo trabajo" (primary button, plus icon).

Two sections: "Borradores" and "Publicados". Each = a section heading + a list of rows (shadcn item/list). Each row: document title (links to its editar page), and inline meta:
- moderation-hidden docs get a red-tinted badge "Oculto por moderación".
- published docs show "Publicado el {fecha}" (muted).
- consider a small status badge per row (draft=neutral, published=green) consistent with the foundations status set.
Rows: hover background, clear click target, hairline dividers or carded list — keep it minimal and scannable.

STATES:
- Loading: row skeletons under each section.
- Empty (per section): "Aún no subiste ningún trabajo — empezá con Nuevo trabajo" with the empty pattern + the Nuevo trabajo CTA. (Both sections can be empty independently.)
Deliver desktop + mobile, populated + empty.
```

### C8 — Nuevo trabajo (create form) · `12`
```
Redesign /mis-trabajos/nuevo — the create-draft form. Single column, max-width ~640px, clear field rhythm (shadcn field/label). Page H1 "Nuevo trabajo".

Fields in order (keep all + validation):
1. Título (text, required).
2. Área — the cascading Escuela → Carrera → Materia selector (must reach a Materia leaf). Show validation "Elegí una Materia".
3. Tipo — select of 8 document types.
4. Visibilidad — radio-group of 3 options, EACH with a helper line: Público ("Cualquier persona puede encontrarlo y leerlo."), Interno ("Sólo personas con cuenta UNSAM…"), Privado ("Sólo vos y tus coautores aceptados."). Design these as selectable cards/rows with the helper text, not bare radios — make the choice feel considered.
5. Coautores externos — repeatable group of (Nombre, Apellido, Email) rows, each removable (X), plus "Agregar coautor externo". Inline per-field errors.
6. Coautores (registered) — a searchable picker: type a name → results list (name · email) → selected users become removable chips.
7. Archivo principal — a real FILE UPLOAD affordance (drag-and-drop dropzone styled, not a raw <input type=file>): accepts .pdf/.docx/.odt, shows the chosen filename + size + a clear/replace control. This is the most-used action — make it prominent and obviously droppable.

Submit: primary "Subir trabajo" (loading state while uploading). Form-level error message region above the button. 
Deliver desktop + mobile; show the dropzone empty + file-selected states, and the coautor picker with results + chips.
```

### C9 — Editar trabajo (workspace) · `13`,`14`,`15`,`16`,`18`
```
Redesign /mis-trabajos/{id}/editar — the draft/published editing workspace. Max-width ~768px. Header: H1 "Editar trabajo" + a status pill on the right (uses the foundations status badges: e.g. Borrador / Procesando / Listo para publicar / Publicado / Falló).

This screen has THREE top-level modes:

A) BLOCKED — first version still indexing OR failed (no form yet):
   - Indexing: centered block with the ProcessingSteps component (see C11) + reassurance copy "Estamos procesando tu archivo. Esto puede tardar unos minutos. Podés cerrar esta página y volver más tarde…". Calm, patient, premium loading moment.
   - Failed: centered destructive message (the gate message) + an "Eliminar" action (owner only).

B) READY — the full editable form:
   - Fields: Título (text), Área (read-only breadcrumb Escuela › Carrera › Materia), Resumen (textarea, reading-sized), Palabras clave (comma input), Fecha (date). 
   - Each of Resumen/Palabras clave/Fecha can show a small "Restaurar" link (top-right of the field) when the value diverges from the extractor's suggestion — design this as a subtle inline affordance, not a button.
   - Visibilidad (select) — owner only.
   - Fields auto-save on blur (toast on failure). Convey "saved" lightly if possible.
   - Then stacked panels (each a bordered section): CandidatePanel (C10), "Versiones anteriores", "Adjuntos" (C11), "Coautores" (C11).
   - Initial publish affordance: a primary "Publicar" button + a muted gate-reason line when publishing is blocked. (Only before the first published version exists.)
   - "Eliminar" (owner only) at the very bottom, separated by a divider, opens the delete alert-dialog: title "¿Eliminar este trabajo?", body about 180-day papelera restore window, Cancelar / Eliminar (destructive).

Keep all Spanish copy. Make a long form feel calm and navigable (clear section separation, consistent panel styling). Deliver: indexing-blocked, failed-blocked, full ready form (desktop + mobile), and the delete dialog.
```

### C10 — Candidate / replace-file panel · `16`
```
Redesign the CandidatePanel (inside editar, for replacing the main file on a PUBLISHED doc). Bordered section, heading "Archivo principal". Helper: "La versión previa permanece pública hasta que publiques la nueva." Four states:

1) No candidate: a "Reemplazar archivo principal" upload control (styled dropzone/button, accepts .pdf/.docx/.odt) + the helper line.
2) Processing: the ProcessingSteps progress (C11) + a "Reemplazar" control + "Descartar" (when allowed).
3) Ready: a status pill, a staged-metadata preview (Resumen / Palabras clave / Fecha the extractor produced for the new version), a primary "Publicar" (enabled when allowed) + "Descartar".
4) Failed: status pill + destructive error text + "Descartar".
Replace errors surface inline ("Este archivo supera los 50 MB", "Formato no soportado o PDF cifrado", etc.).

Make the four states visually distinct but clearly one component. Keep Spanish copy.
```

### C11 — Workspace sub-panels: Processing, Coautores, Adjuntos · `13`,`15`
```
Redesign these shared panels used in the editar workspace. Keep all copy + behavior.

PROCESSING STEPS (progress indicator): a labeled progress bar with a spinner + current step label. Steps map to honest backend checkpoints — "Leyendo el documento", "Reconociendo texto (puede tardar varios minutos)", "Generando resumen y palabras clave", "Analizando contenido", "Preparando la búsqueda"; fallbacks "En cola" / "Procesando…". Bar fills by step/4. Make the fill animate smoothly in deep blue; spinner subtle. Optionally render as discrete step ticks rather than a plain bar — but never advertise a step that may not run (label-driven). 

COAUTORES PANEL (owner only): bordered section "Coautores". List rows: display name (+ email local part), an owner row marked "Vos", and per-row status badge (Pendiente=amber, Aceptado=green, Rechazado=neutral/red). Pending rows have a "Quitar" action. Below the list: the searchable coautor picker (name search → results → invite). 

ADJUNTOS PANEL: bordered section "Adjuntos". List rows: filename · size, each with "Quitar" (when manageable). Empty: "Sin adjuntos". Add control: "Agregar adjunto" (dropzone/button, accepts .csv/.json/.txt/.py/.ipynb/.png/.jpg/.gif/.zip), disabled at the 5-attachment cap with "Llegaste al máximo de 5 adjuntos". Toasts on errors.

Deliver each panel in its key states. Consistent with the other bordered panels on the editar page.
```

### C12 — Report dialog & Coautor invitation card · `08`,`24`
```
Redesign two small but important interactive surfaces. Keep Spanish copy + behavior.

REPORT (Reportar) — a popover on the doc detail aside. Trigger: muted "Reportar" text/button. Content: "¿Por qué reportás este documento?" + a radio-group of reasons (Spam, Contenido inadecuado, Plagio, Error en el contenido) + primary "Enviar" (disabled until a reason is picked). Success state replaces content with "Recibimos tu reporte. Gracias." Error: inline retry message. Keep it compact (~288px).

COAUTOR INVITATION CARD — two variants of one component (see C6): 
- "minimal": standalone centered card (max-width ~440px) — the only thing on a privado doc the invitee can't read yet.
- "banner": a strip above doc metadata.
Both: "{inviter} te invitó como coautor en «{título}». ¿Aceptar o rechazar?" + Aceptar (primary) / Rechazar (ghost). Error region for failed actions. Make "minimal" feel intentional and trustworthy on its own, not like an error page.
```

### C13 — Papelera · `17`
```
Redesign /mis-trabajos/papelera (soft-deleted documents, restorable for 180 days). Header: "Papelera" + a "Volver a Mis trabajos" link.

List rows: document title + a muted "Se elimina en {n} días" countdown, and a "Restaurar" action per row (toast "Trabajo restaurado" on success). Consider a subtle warning tone on rows close to purge.

STATES: loading skeleton, empty ("La papelera está vacía" — empty pattern, muted trash icon). Deliver desktop + mobile, populated + empty.
```

### C14 — Moderación queue · `19`
```
Redesign /moderacion (docente-only report queue). Header: "Moderación".

List of report rows, each links to the inspect page. Row: document title (prominent) + a meta line: reason tags · "{n} reportes" · "Último reporte el {fecha}". Surface the reason categories as small badges (Spam / Contenido inadecuado / Plagio / Error). Make a high report_count visually notable (it's a triage signal).

STATES: loading skeleton, empty ("No hay reportes pendientes" — calm empty pattern, shield/check icon). This is a work queue — prioritize fast scanning. Deliver desktop + mobile, populated + empty.
```

### C15 — Moderación inspect · `20`
```
Redesign /moderacion/{reportId} (docente reviews one reported document and acts). Max-width ~768px.

H1 = document title. Metadata definition list: Tipo, Área, Autores, Palabras clave, Resumen, and "Reportado por" (the reporter-chosen reason labels). A "Descargar archivo" link to inspect the actual file.

Action zone (separated by a divider): a "Motivo" textarea (free-text moderator note) + three actions: "Ocultar" (destructive), "Mostrar" (outline), "Descartar" (ghost). Buttons disable while an action is pending. After acting, the moderator returns to the queue.

Frame this as a focused review surface — give the document content room to be read/judged, keep the action zone clearly separated and deliberate (these actions notify the author). Loading + not-found ("No se pudo cargar el reporte") states. Deliver desktop + mobile.
```

### C16 — Not found / 404
```
Design the "not found" page (shown for a missing/unauthorized document at /docs/{id}, and as the generic app 404). Centered, calm, on-brand with the minimal system.

Content: the empty-state pattern — a muted lucide icon (file-x / search-x), a short Spanish message ("No encontramos esta página." / for documents: "Este trabajo no existe o no está disponible."), and a primary action back to search ("Volver a buscar" → /buscar). Keep it minimal and reassuring — never expose whether a private document exists (a missing doc and an unauthorized doc must look identical). Deliver desktop + mobile.
```

---

## §D. Notes for the implementing dev (post-design)
- Current tokens live in `frontend/src/app/globals.css` (`:root` OKLCH neutral ramp). Apply the deep-blue accent by setting `--primary` / `--ring` (and the status-badge utilities) there; leave the `.dark` block as-is.
- Components to (re)add from shadcn that aren't installed yet: `skeleton`, `empty`, `badge`, `card`, `field`, `input`, `input-group`, `select`/`native-select`, `radio-group`, `tabs`/`toggle-group`, `dropdown-menu`, `avatar`, `breadcrumb`, `pagination`, `progress`, `command`, `separator`, `tooltip`, `dialog`. (Already present: `button`, `popover`, `alert-dialog`, `sonner`.)
- The cascader, coautor picker, processing steps, candidate panel, and notification kinds are bespoke — Design restyles them; keep the existing component boundaries.
