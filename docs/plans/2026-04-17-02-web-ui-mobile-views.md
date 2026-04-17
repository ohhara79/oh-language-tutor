# Unified 3-view UI (mobile + desktop)

## Context

Browsing threads on a phone is painful: on narrow screens the current 2-column grid collapses to a single column with `#stream-pane` above a sticky sidebar — the user must scroll past hundreds of raw lines to reach the thread list, sticky+max-height creates double scroll regions, touch targets are ~24 px tall, and long (Korean) anchor text is truncated with an ellipsis.

This change replaces the current 2-pane desktop layout and 1-column mobile fallback with a **single, unified UI** that has three navigable views: **list**, **line-detail**, **thread-detail**. Desktop and mobile render identically; only sizing changes.

Rationale (per user decisions in planning):
- List view must be compact — only raw text lines + the (always-expanded) thread list.
- Explanation, per-line threads, Ask, Delete all live in **line-detail**, entered by tapping a raw line.
- Tapping a thread (from anywhere) opens **thread-detail**. Back returns to wherever you came from.
- Desktop mirrors mobile so there is only one UX to maintain.

## Target views

### 1. List view (default)
- Compact list of **raw text only**, one line per row, each tappable.
- Below that: a "Threads" heading and the full thread list, always expanded (no collapse toggle).
- No explanation, no per-line Ask/Delete/Threads buttons visible.
- No Back button.

### 2. Line-detail view (entered by tapping a raw line in list view)
- Header: `← Back` button, then the raw text of the tapped line.
- Body: explanation (markdown-rendered).
- Below: `Threads (N)` — inline list of this anchor's threads (empty if N = 0). Each thread item opens thread-detail.
- Actions row: `Ask`, `Delete`.

### 3. Thread-detail view (entered by tapping any thread)
- Header: `← Back` button, then the thread's anchor raw text.
- Body: messages (user + assistant, existing markup).
- Footer: compose form (textarea + Send button), sticky to bottom.
- Delete button in the header row.

### Navigation stack
- `list → line-detail → thread-detail` (Back from thread returns to line-detail).
- `list → thread-detail` (Back from thread returns to list).
- The nav stack is explicit in JS; browser hardware Back is wired through `history.pushState` / `popstate` so it matches.

## File changes

### `tutor/templates/index.html` (rewrite body structure)
Replace the two-column `.layout` with a single column and three top-level sections gated by a body view-state class.

### `tutor/templates/partials/line.html` (separate raw from detail)
Split what's always visible (raw text) from what's hidden until line-detail: raw-toggle button + hidden `.line-detail` (explanation, per-line threads placeholder, Ask/Delete actions).

### `tutor/templates/partials/thread_list.html` (add anchor_id data attribute)
Each `<li>` gets `data-anchor-id="{{ t.anchor_id }}"` so the per-line threads JS can filter client-side.

### `tutor/static/app.css` (rewrite layout + view-state CSS)
- **Remove**: `.layout` grid, `.sidebar` sticky/max-height, `#stream-pane` max-height/overflow, the `@media (max-width: 900px)` rule (no longer needed).
- **Add**: a single column body, view-state visibility rules, touch targets (≥44px), sticky compose bar with safe-area inset.

### `tutor/static/app.js` (nav stack + view transitions)
Replace with a nav controller that:
- Maintains a stack `[list, ...]` and toggles `body.view-list|view-line|view-thread`.
- Pushes on raw-line tap, on `#thread-conversation` afterSwap (if not empty-state).
- Pops on `#back-btn` click and on hardware `popstate`.
- Populates per-line thread sublists by cloning filtered `#thread-list` items.
- Re-populates the active line's sublist when SSE swaps `#thread-list`.

### No backend changes required
- `/threads/{id}`, `/commands/open_thread`, `/commands/send_message`, `/commands/delete_thread`, `/commands/delete_tutor_entry`, `/events` (SSE) — all unchanged.
- `thread-meta` already includes `anchor_id`.

## SSE behavior in each view
- `explanation`/`raw_line` → append to `#stream-pane`. Visible in list view; silently appended in detail views.
- `thread_list` → innerHTML swap on `#thread-list`. Immediate in list view; re-populates active line sublist in line-detail view.
- `thread_chunk`/`thread_done` → OOB swaps target `#thread-messages-{id}` (unchanged).
- `tutor_entry_removed`/`error` → OOB/toast (unchanged).

## Verification

1. Start web server: `uv run --frozen python -m tutor --web --source-language en --target-language ko --level intermediate` (exact flags may differ; check CLAUDE.md).
2. Chrome DevTools: iPhone SE (375×667), Pixel 7 (412×915), and desktop 1280×800.
3. Smoke test:
   1. Load with no threads → stream shows raw lines only; "Threads" heading with empty-state; no horizontal scroll.
   2. Tap a raw line → line-detail with Back, explanation, Threads (0 or N), Ask, Delete.
   3. With a line open, tap `Ask` → thread-detail with compose. Send → streams back. Back → line-detail.
   4. From line-detail with N>0, tap a per-line thread → thread-detail. Back → line-detail. Back → list.
   5. From list, tap any thread in the global list → thread-detail. Back → list.
   6. Delete a thread from thread-detail → returns to previous view.
   7. Long Korean anchor: wraps, no ellipsis.
   8. iOS Safari: textarea focus, no zoom, compose not hidden by keyboard.
   9. Hardware/browser Back matches on-screen Back at each depth.
   10. Dark mode: sticky compose background matches.
4. `uv run --frozen basedpyright tutor/` — green (Python untouched).
5. No regression in CLI/TUI (this change is web-only).

## Critical files
- `tutor/templates/index.html`
- `tutor/templates/partials/line.html`
- `tutor/templates/partials/thread_list.html`
- `tutor/static/app.css`
- `tutor/static/app.js`

## Out of scope
- No backend/SSE schema changes.
- No changes to TUI or CLI modes.
- No persistence of view state across reloads (always lands in list view).
- No swipe gestures.
