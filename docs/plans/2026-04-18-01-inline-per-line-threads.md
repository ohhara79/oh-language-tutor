# Inline per-line threads in list view

## Context

The previous web-UI rewrite (`2026-04-17-02-web-ui-mobile-views.md`) put the thread list in its own section at the bottom of list view, separate from the stream. The user reports that browsing is easier if each line's threads appear directly below that line — so related threads are visible in context without scrolling to a separate section.

This change moves each thread's UI next to its anchor line, keeping the hidden `#thread-list` as the SSE source of truth and distributing its items into per-line containers on every update.

## Target behavior

- **List view:** raw text lines stacked; each line's threads are shown inline just below the raw text. Tapping a thread item → thread-detail. Tapping the raw text → line-detail.
- **Line-detail view:** active line shows raw text, its inline threads (same as list view), explanation, Ask, Delete.
- **Thread-detail view:** unchanged.
- **Orphan threads** (anchor_id empty or anchor line absent): shown in a separate "Other threads" section at the bottom of list view. Auto-hidden when empty.

## File changes

### `tutor/templates/partials/line.html`
Move `.line-threads` out of `.line-detail` so it's a sibling that stays visible in list view:

```html
<section class="line" id="line-{{ entry.id }}" data-anchor-id="{{ entry.id }}">
  <button type="button" class="raw-toggle">RAW</button>
  <div class="line-threads" data-anchor-id="{{ entry.id }}"></div>
  <div class="line-detail">
    <div class="explanation-body">...</div>
    <div class="line-actions"><!-- Ask / Delete --></div>
  </div>
</section>
```

### `tutor/templates/index.html`
- Keep `#thread-list` as the SSE target but hide it (`style="display:none"`). This preserves `sse-swap="thread_list" hx-swap="innerHTML"` exactly; JS reads from it after each swap.
- Replace the visible "Threads" heading with an `#orphan-threads-section` that shows only unmatched threads.

```html
<div id="thread-list" sse-swap="thread_list" hx-swap="innerHTML" style="display:none">
  {% include 'partials/thread_list.html' %}
</div>

<section id="orphan-threads-section">
  <h2>Other threads</h2>
  <div id="orphan-threads"></div>
</section>
```

### `tutor/static/app.js`
- New `distributeThreads()`: read `<li>` items from hidden `#thread-list`; clone each into its matching line's `.line-threads` (by `data-anchor-id`); push unmatched ones into `#orphan-threads`. Call `htmx.process()` on each populated subtree.
- Call `distributeThreads()` once on DOMContentLoaded and in `htmx:afterSwap` when target is `#thread-list` (SSE update) or `#stream-pane` (new line appeared — its empty `.line-threads` needs filling in case an orphan now matches).
- Remove the old `populateLineThreads()` (superseded).
- Keep the thread-conversation afterSwap branch (tap-to-thread still works via cloned `hx-get`).

### `tutor/static/app.css`
- Show `.line-threads` in list and line-detail views.
- Style as a compact indented list: smaller font, tighter padding than the top-level list.
- `.line-threads:empty { display: none; }` so lines with zero threads don't leave vertical gaps.
- Hide `#orphan-threads-section` in `body.view-line` / `body.view-thread`; hide when `#orphan-threads` is empty.

## SSE behavior

- `thread_list` → innerHTML swap on hidden `#thread-list`. `htmx:afterSwap` triggers `distributeThreads()` which refreshes all per-line containers + orphans.
- `explanation` → appends a new `.line` via beforeend swap on `#stream-pane`. `htmx:afterSwap` on `#stream-pane` triggers `distributeThreads()` to populate the new line's empty `.line-threads` if any existing orphan thread matches it.
- Other SSE events unchanged.

## Verification

1. Smoke run: launch the server; confirm initial load shows existing entries with their threads inline. (`curl /` and render check already green.)
2. In browser: create a thread via "Ask" → returns to line-detail with the new thread appearing inline under the line.
3. Delete the anchor line with `Delete` → the cascaded thread removals update both the line's `.line-threads` (line itself removed) and any orphan display.
4. Manually delete a line with active threads in another client → orphan section populates; threads open correctly from there.
5. Confirm `.line-threads:empty` rule hides containers on lines with no threads.
6. Lint: `uv run --frozen ruff check tutor/` and `uv run --frozen basedpyright tutor/` — should remain green (Python untouched).

## Critical files
- `tutor/templates/partials/line.html`
- `tutor/templates/index.html`
- `tutor/static/app.css`
- `tutor/static/app.js`

## Out of scope
- No backend/SSE schema changes.
- No change to `thread_list.html` (still renders the full `<ul>` used as SSE source).
- No change to `thread_conversation.html` or nav stack.
