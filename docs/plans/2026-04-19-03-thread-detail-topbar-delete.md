# Thread detail: move Delete button to the top-right row next to Back

## Context

In the web thread detail view, the Delete button lives inside `.thread-header`, floated right of the anchor raw text (`tutor/templates/partials/thread_conversation.html:3-9`, `tutor/static/app.css:141-161`). Even with the recent float change (plan `2026-04-18-19`), the anchor text and Delete still share the same horizontal row, so longer raw text cannot claim the full width.

The Back button already sits at the top of `<body>` in thread view (`tutor/templates/index.html:17`), one row above the conversation. The natural home for Delete is the same row — top-right, mirroring Back — which frees the whole anchor-raw row for text.

## Approach

Wrap the Back button and a new empty slot in a `#thread-topbar` flex row. The conversation partial renders the Delete form as an htmx out-of-band (OOB) swap targeting that slot, so the form still renders server-side per thread (with the correct `thread_id`) while visually living next to Back — even though Back is outside the conversation partial.

Back's JS handler is attached once on page load (`tutor/static/app.js:53-55`); wrapping it in a `<div>` does not break event binding.

### Template: `tutor/templates/index.html`

Replace the bare Back button with a flex row:

```html
<div id="thread-topbar">
  <button type="button" id="back-btn" class="btn">&larr; Back</button>
  <div id="thread-topbar-actions"></div>
</div>
```

### Partial: `tutor/templates/partials/thread_conversation.html`

Move the Delete form out of `.thread-header` into an OOB block at the top of the partial, targeting `#thread-topbar-actions`:

```html
<div id="thread-topbar-actions" hx-swap-oob="innerHTML">
  <form hx-post="/commands/delete_thread"
        hx-confirm="Delete this thread permanently?"
        hx-target="#thread-conversation"
        hx-swap="innerHTML">
    <input type="hidden" name="thread_id" value="{{ meta.thread_id }}">
    <button type="submit" class="btn btn-del">Delete</button>
  </form>
</div>
<div class="thread-header">
  <p class="anchor-raw">{{ meta.anchor_raw | e }}</p>
</div>
```

### Endpoint: `tutor/web.py` — clear slot on delete

After a delete, the empty-state response replaces `#thread-conversation` and the afterSwap handler navigates back to list view, hiding `#thread-topbar`. To avoid leaving a stale delete form (pointing at a now-deleted `thread_id`) in the DOM, append an OOB block that empties the slot:

```python
return HTMLResponse(
    content=(
        '<p class="empty">Thread deleted.</p>'
        '<div id="thread-topbar-actions" hx-swap-oob="innerHTML"></div>'
    ),
)
```

### Styles: `tutor/static/app.css`

Remove:
- `#back-btn { display: none; margin: 0 0 0.75rem; }`
- `body.view-thread #back-btn { display: inline-flex; }`
- `.thread-header::after` clearfix
- `.thread-header > form { float: right; ... }`

Add:

```css
#thread-topbar {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin: 0 0 0.75rem;
}
#thread-topbar-actions form { margin: 0; }

body.view-thread #thread-topbar { display: flex; }
```

`.thread-header` keeps its `border-bottom` / `padding-bottom`; it now simply wraps the full-width `.anchor-raw`.

## Why OOB swap (not DOM restructure alternatives)

- **Move Back into the partial**: requires re-binding the click handler on every swap; single-source JS handler is simpler.
- **Move Delete form into `index.html`**: no `thread_id` available there on initial render; would need JS to populate per-thread.
- **CSS-only positioning across DOM branches** (e.g. absolute-positioning the Delete inside the conversation): fragile, needs a known parent box, and breaks the natural flex row with Back.
- **OOB swap**: the partial already loads per thread; adding one sibling OOB block is the minimal change that keeps Back's JS untouched and keeps `thread_id` server-rendered.

## Files

- `tutor/templates/index.html` — add `#thread-topbar` wrapper.
- `tutor/templates/partials/thread_conversation.html` — OOB Delete block, strip form from `.thread-header`.
- `tutor/web.py` — append OOB clear to the `delete_thread` response.
- `tutor/static/app.css` — drop old `#back-btn` + `.thread-header` float rules, add `#thread-topbar` rules, update view-state toggle.

## Verification

1. `make lint` — type-check and style pass.
2. `uv run --frozen pytest tests/test_web.py -q` — existing `/commands/delete_thread` test still passes (asserts 200; extra OOB HTML does not break it).
3. Browser check (start the web app per README):
   - List view: `#thread-topbar` hidden; no Back, no Delete visible.
   - Open a thread: top row is `[← Back] …………… [Delete]`; the next row is the anchor raw text spanning the full width.
   - Long anchor raw text wraps across multiple lines without being crowded by Delete.
   - Click Delete → confirm → conversation becomes empty state → app navigates back to list view → topbar hides.
   - Open a different thread → `#thread-topbar-actions` slot shows the correct thread's Delete form (OOB replaces any prior content).
   - Dark mode: Back and Delete buttons keep existing styling (no changes to `.btn` / `.btn-del` / dark-mode block).
