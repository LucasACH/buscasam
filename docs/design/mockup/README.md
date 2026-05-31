# BUSCASAM — design mockup

Static, interactive prototype of the BUSCASAM design system, authored by Claude
Design. This is the visual source of truth that the Next.js frontend
(`frontend/`) implements. See [`../claude-design-handoff.md`](../claude-design-handoff.md)
for the accompanying handoff notes.

## View it

Open the HTML files directly in a browser (no build step):

- `Foundations.html` — tokens, type scale, color, and component kit.
- `BUSCASAM.html` — full prototype of every screen (React via in-browser Babel).

## Layout

- `css/tokens.css` — design tokens (mapped onto the shadcn theme in
  `frontend/src/app/globals.css`).
- `css/components.css`, `css/app.css` — component + screen styles.
- `js/*.jsx` — per-screen prototype components (rendered with the UMD React +
  Babel standalone scripts loaded by `BUSCASAM.html`).
