# Compact thread heading: remove msg count + timestamp

## Context

The thread list row currently renders three spans: heading, `N msg`, and the created timestamp. The user wants only the heading for a more compact list.

## Change

### 1. `tutor/templates/partials/thread_list.html`
Keep only the `.anchor` span; drop `.count` and `.created`:

```html
<a href="#" hx-get="/threads/{{ t.thread_id }}" hx-target="#thread-conversation" hx-swap="innerHTML">
  <span class="anchor">{{ thread_heading(t) | e }}</span>
</a>
```

### 2. `tutor/static/app.css`
Remove the now-orphaned rules (no templates reference `.count` or `.created` after this change):

- `.thread-list .count, .thread-list .created { ... }` (in the "Thread list" block).
- `.line-threads .thread-list .count, .line-threads .thread-list .created { ... }` (in the per-line compact variant).

### 3. No change to backend / Jinja globals
`format_created_at_utc` is still used by the TUI (`tutor/gui.py`) and `tutor/html_export.py`, so the function stays. Keeping it registered as a Jinja global is harmless even though no template uses it after this change.

## Verification
1. `uv run --frozen ruff check tutor/ && uv run --frozen basedpyright tutor/` — clean (Python untouched).
2. Render `index.html` with a stub thread and confirm only the heading span appears, no `N msg`, no UTC timestamp.
3. Browser: thread rows display just the first-question heading; inline per-line lists and orphan list both compact.

## Critical files
- `tutor/templates/partials/thread_list.html`
- `tutor/static/app.css`
