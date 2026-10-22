# Project instructions

## Frontend direction

- Use white or extremely light gray backgrounds and compact, readable layouts.
- This is a reference database. Prioritize useful information and efficient lookup.
- Do not introduce oversized headings, hero sections or decorative empty space.
- Every new frontend page and control must fit the available screen width.
  Horizontal scrolling is prohibited, including inside tables, tabs, filters,
  navigation, and other nested containers. This supersedes earlier scrollable-table designs.
- Follow the original site's compact information layout: group related fields,
  use proportional table columns, wrap text and controls, and reflow dense content
  on narrow screens. Keep information readable and available; do not conceal
  overflow or remove data merely to make a layout fit. Check narrow phone widths
  (including 320px) as well as wider layouts without invoking Computer Use.
- Sophisticated implementation is welcome: smooth interaction feedback, hover
  previews, subtle shadows, responsive layouts and efficient background work.
- Respect reduced-motion settings and keep keyboard access functional.
- The user authorized moving the original site to `games/mhxx_old/` and placing
  the new frontend at `games/mhxx/`. Keep the archived data intact; only its entry
  redirect is adjusted to stay inside the archive. Do not add navigation to it.
- Treat `games/mhxx_old/` as the extraction source and `games/mhxx/` as generated
  frontend output. Edit `web/` and rebuild; never extract from generated output.
- Local development does not authorize publishing or modifying the upper-level site.
