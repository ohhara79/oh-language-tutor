# Move Learning / Native / Level controls into the hamburger menu

## Context

In the web sentence-list view (`/tutor`), tapping an unexplained sentence currently expands a `.line-detail` panel that renders three controls — Learning, Native, Level — alongside the **Explain** button (`tutor/templates/partials/line.html:38-55`). These three values are already global: they're persisted to `localStorage` (`tutor.sourceLanguage`, `tutor.targetLanguage`, `tutor.level`) and every newly-activated line hydrates its controls from the same keys (`tutor/static/app.js:21-62`). The per-line UI is therefore misleading — it edits one shared value but looks per-sentence — and it clutters the Explain action.

Relocate the three controls into the existing hamburger menu (`#menu-panel` in `tutor/templates/index.html:19-41`), placed between the Jump-to-Nth slider and the **Switch dataset** link. After the move, the unexplained-sentence detail panel keeps only the Explain button; the menu becomes the single place to view/edit the audience that future Explains will use.

Server contract is unchanged: `htmx:configRequest` still injects `source_language`, `target_language`, and `level` onto `/commands/explain`, now read from one set of controls instead of from the active line.

## Approach

### `tutor/templates/index.html`

Add a `<hr class="menu-sep">` + `<div class="menu-cfg">…</div>` block inside `#menu-panel`, immediately before the `Switch dataset` anchor. The inner markup reuses the existing `.cfg-field`, `.cfg-label`, `.cfg-source-language`, `.cfg-target-language`, `.cfg-level` classes so the `CFG_FIELDS` table in `app.js` keeps matching without modification.

### `tutor/templates/partials/line.html`

Delete the `<div class="line-cfg">…</div>` block (currently `line.html:38-55`) from the unexplained, non-streaming branch. Leave the `<div class="line-actions">` with the Explain form intact.

### `tutor/static/app.js`

- Drop the `cfgHydrateLine` helper and the call to it from the raw-line click handler — there are no per-line controls left to hydrate.
- Add a small `cfgHydrateMenu()` that fills the menu's `.cfg-*` controls from `cfgGet(key)` on init.
- Move the `input`/`change` listeners from `#stream-pane` onto the new `.menu-cfg` container.
- Simplify the `htmx:configRequest` handler to read each form field straight from `cfgGet(key)` instead of querying the active line.

### `tutor/static/app.css`

- Add a `.menu-cfg` block (vertical flex layout, sensible padding) near the existing `.menu-jump` rules.
- Override `.menu-cfg .cfg-field input, .menu-cfg .cfg-field select { width: 100%; }` so the inputs fill the menu width.
- Remove the now-unused `.line-cfg` rule. The shared `.cfg-field` / `.cfg-label` / `.cfg-field input,select` rules stay; they're still consumed by the menu.

## Files to modify

- `tutor/templates/index.html`
- `tutor/templates/partials/line.html`
- `tutor/static/app.js`
- `tutor/static/app.css`

## Verification

1. `make lint` clean.
2. Run web mode, open `/tutor`. Hamburger menu order: *Show only explained* → *Stdin → …* (when applicable) → *Jump to …* → **Learning / Native / Level** → *Switch dataset*.
3. Menu controls are pre-filled from `localStorage` and persist across menu close/open and page reload.
4. Tapping an unexplained sentence shows only the **Explain** button (no inline audience controls). The `POST /commands/explain` payload still carries `source_language` / `target_language` / `level` matching the menu values.
5. Changing a menu value mid-session causes the next Explain to use the new value (no stale per-line copy).
6. Explained-sentence detail and Ask / Delete actions are unchanged.
