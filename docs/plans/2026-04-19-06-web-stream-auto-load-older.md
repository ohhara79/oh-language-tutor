# Web raw-text stream: render tail by default + auto-load older on scroll-up

## Context

The web list view (`#stream-pane` in `tutor/templates/index.html`) renders every
tutor entry via a single Jinja loop over `ctx.tutor_store.load()`. With each
`.raw-toggle` at `font-size: 1.5rem` and no truncation, long histories are
painful to scroll.

We evaluated three approaches (CSS truncation, tail + "Load older" control,
URL-based pagination). The user picked **tail + auto-load on scroll-up**
because it keeps SSE append-at-bottom semantics, avoids per-page URL state,
and requires no manual click — scrolling toward older content automatically
reveals more.

The existing thread-orphan logic (`distributeThreads()` in
`tutor/static/app.js:117`) dumps threads whose anchor line isn't in the DOM
into `#orphan-threads`. With pagination, older-but-unloaded threads would all
show up under "Other threads" — confusing, because nothing tells the reader
*why* those threads are separated. So we also **hide the orphan section
silently** as part of this change. This is safe because
`FollowupThreadPool.delete_tutor_entry` (`tutor/thread_pool.py:185-187`)
cascade-deletes threads when their anchor line is deleted, so no
legitimately-orphaned threads exist in normal operation — every orphan after
this change is a "just not loaded yet" thread that will reappear under its
line once "Load older" reaches far enough.

**Silent-hide tradeoff explicitly accepted.** When the history is long
(thousands of entries) and the user's threads cluster around older material,
*all* thread headings may be hidden on initial render. Example from a real
session: 1,647 entries, 39 threads, 0 thread anchors inside the last-50
window → 0 headings visible on first paint. We considered two alternatives —
(a) auto-expanding the initial tail to cover the oldest thread anchor, and
(b) a pinned no-header thread list at the top of the stream — and rejected
both in favor of the cleaner silent-hide UI. Threads remain reachable via
scroll-up auto-load (which re-attaches them to their anchor lines on each
batch) and via direct `/threads/{id}` URLs; they are never lost.

## Approach

**Default render:** only the newest `N = 50` entries.
**Auto-load via a sentinel** — an invisible `<div id="load-older-sentinel">`
sits at the top of `#stream-pane` with `hx-trigger="intersect once"`. When the
user scrolls up enough for it to enter the viewport, HTMX fires the request.
The response replaces the sentinel (via `hx-swap="outerHTML"`) with
`[fresh sentinel with updated cursor] [older line 1…N]`, so the new sentinel
remains at the top and the older lines appear below it. Combined with the
scroll-anchor described in §4, the new sentinel ends up *out of viewport*
right after the swap (pushed up by the added content), so it doesn't
immediately re-fire; the user has to scroll up again to trigger the next
load. When no older entries remain, the server returns a non-triggering
sentinel (or omits it).

### 1. `tutor/tutor_store.py` — two helpers

Add read-only helpers that reuse the existing memoized `load()`:

```python
def load_tail(self, n: int) -> tuple[list[TutorEntry], bool]:
    """Return (last n entries, has_more)."""
    entries = self.load()
    if n <= 0 or not entries:
        return ([], False)
    tail = entries[-n:]
    return (tail, len(entries) > n)

def load_before(self, anchor_id: str, n: int) -> tuple[list[TutorEntry], bool] | None:
    """Entries immediately older than anchor_id, oldest-first.

    Returns None if anchor_id is not present (caller should 404).
    """
    entries = self.load()
    idx = next((i for i, e in enumerate(entries) if e.id == anchor_id), None)
    if idx is None:
        return None
    start = max(0, idx - n)
    return (entries[start:idx], start > 0)
```

`index_of` already exists at `tutor/tutor_store.py:90` but returns only the
index; inlining the lookup above keeps the new call to one `load()` pass.

### 2. `tutor/web.py` — tail render + new endpoint

At module top add:

```python
_STREAM_PAGE_N = 50
```

**Modify `index()` (`tutor/web.py:97-109`):**

```python
entries, has_more = ctx.tutor_store.load_tail(_STREAM_PAGE_N)
oldest_id = entries[0].id if entries else None
# ...render index.html with entries, has_more, oldest_id, N=_STREAM_PAGE_N
```

**Add new route (near the other `/partials/...` handlers):**

```python
@app.get('/partials/older', response_class=HTMLResponse)
async def older(before: str, n: int = _STREAM_PAGE_N) -> HTMLResponse:
    result = ctx.tutor_store.load_before(before, n)
    if result is None:
        raise HTTPException(status_code=404, detail='cursor not found')
    older_entries, has_more = result
    new_oldest_id = older_entries[0].id if older_entries else before
    html_body = ctx.env.get_template('partials/older_lines.html').render(
        entries=older_entries,
        has_more=has_more,
        oldest_id=new_oldest_id,
        page_n=n,
    )
    return HTMLResponse(content=html_body)
```

### 3. Templates

**New `tutor/templates/partials/older_lines.html`** — response body for the
endpoint. The fresh sentinel comes **first**, then the older lines in
chronological order, so that the `outerHTML` swap lands the new sentinel at
the top of the stream and the lines right below it:

```html
{% if has_more %}
<div id="load-older-sentinel"
     hx-get="/partials/older?before={{ oldest_id }}&n={{ page_n }}"
     hx-trigger="intersect once"
     hx-swap="outerHTML"
     hx-indicator="#load-older-indicator"
     aria-hidden="true"></div>
{% endif %}
{% for entry in entries %}
  {% set raw_escaped = entry.raw | e %}
  {% set explanation_html = render_markdown(entry.explanation) %}
  {% include 'partials/line.html' %}
{% endfor %}
```

When `has_more` is false, the response contains only the older lines (no new
sentinel). The `outerHTML` swap replaces the old sentinel with these lines;
no sentinel remains in the DOM, so no further auto-load can fire. No OOB
needed.

**Modify `tutor/templates/index.html`** (line 22-28). Add the sentinel and a
loading indicator at the top of `#stream-pane`, rendered only when
`has_more`:

```html
<main id="stream-pane" sse-swap="explanation" hx-swap="beforeend">
  <div id="load-older-indicator" class="htmx-indicator" aria-live="polite">Loading older…</div>
  {% if has_more %}
  <div id="load-older-sentinel"
       hx-get="/partials/older?before={{ oldest_id }}&n=50"
       hx-trigger="intersect once"
       hx-swap="outerHTML"
       hx-indicator="#load-older-indicator"
       aria-hidden="true"></div>
  {% endif %}
  {% for entry in entries %}
    {% set raw_escaped = entry.raw | e %}
    {% set explanation_html = render_markdown(entry.explanation) %}
    {% include 'partials/line.html' %}
  {% endfor %}
</main>
```

The indicator stays in the DOM across loads; its `htmx-indicator` class
makes it visible only while an HTMX request is in flight. The sentinel is
re-rendered (with an updated cursor) on each successful load and disappears
when exhausted.

### 4. `tutor/static/app.js` — scroll anchoring

When older lines are prepended, preserve the reader's content position.
Without this, the viewport shifts up to show newly-loaded older content
mid-read — and, critically, leaves the newly inserted sentinel still
intersecting the viewport, which would auto-fire the next load immediately
and cascade. Add near the other `htmx:` listeners:

```js
let _loadOlderBefore = null;
document.body.addEventListener('htmx:beforeRequest', (evt) => {
    const t = evt.target;
    if (!t || !t.id || t.id !== 'load-older-sentinel') return;
    _loadOlderBefore = {
        scrollY: window.scrollY,
        height: document.documentElement.scrollHeight,
    };
});
document.body.addEventListener('htmx:afterSettle', () => {
    if (_loadOlderBefore === null) return;
    const delta = document.documentElement.scrollHeight - _loadOlderBefore.height;
    window.scrollTo(0, _loadOlderBefore.scrollY + delta);
    _loadOlderBefore = null;
});
```

The delta (added height) is strictly positive when the response contained
older lines, so the new sentinel ends up `delta` pixels above the viewport
top — safely out of intersection range until the user scrolls up again.

`distributeThreads()` must run after each auto-load so threads matching the
newly-revealed lines migrate to their `.line-threads` container. Extend the
`htmx:afterSwap` handler (`tutor/static/app.js:84-89`) to trigger not only
on `stream-pane` targets (SSE appends) but also on `load-older-sentinel`
targets — the sentinel's `outerHTML` swap replaces the sentinel itself, so
`evt.target.id` is `load-older-sentinel`, not `stream-pane`. Without this,
threads anchored to freshly-loaded older lines stay unlinked.

**Drop the orphan-rendering branch.** In `distributeThreads()`, remove the
block that writes `#orphan-threads` (`app.js:153-163`). The function still
clears `.line-threads` containers and distributes matched threads to loaded
lines; unmatched threads are simply discarded from the DOM output. The Map /
orphans classification can be simplified to a single loop that skips
unmatched items.

The existing MutationObserver for sticky-bottom (`app.js:184`) is
self-guarded by `wasAtBottom`; loading older always happens while scrolled up,
so it won't fight the prepend.

### 5. `tutor/static/app.css` — indicator styling + orphan section removal

Add below the `.raw-toggle` rules:

```css
#load-older-indicator {
    padding: 0.5rem;
    text-align: center;
    color: #888;
    font-size: 0.9rem;
    display: none;
}
#load-older-indicator.htmx-request {
    display: block;
}
```

HTMX toggles the `htmx-request` class on the element referenced by
`hx-indicator` while the request is in flight. We override the default
`htmx-indicator` visibility-fade approach with an explicit
`display: none / block` swap so there's no flicker at rest.

Delete the now-unused orphan rules:
`#orphan-threads-section`, `#orphan-threads-section h2`,
`#orphan-threads-section:has(#orphan-threads:empty)` (light mode lines
97-103), and `#orphan-threads-section h2 { color: #aaa; }` in the dark-mode
block.

### 6. `tutor/templates/index.html` — drop the orphan section

Remove the entire block (lines 34-37 of current `index.html`):

```html
<section id="orphan-threads-section">
  <h2>Other threads</h2>
  <div id="orphan-threads"></div>
</section>
```

## Files to modify

- `tutor/tutor_store.py` — add `load_tail`, `load_before`.
- `tutor/web.py` — tail load in `index()`; new `GET /partials/older` route;
  `_STREAM_PAGE_N = 50` constant.
- `tutor/templates/index.html` — add `#load-older-indicator` and conditional
  `#load-older-sentinel` inside `#stream-pane`; accept `has_more`,
  `oldest_id` template vars; remove the `#orphan-threads-section` block.
- `tutor/templates/partials/older_lines.html` — new file; fresh sentinel (if
  `has_more`) followed by the older line sections.
- `tutor/static/app.js` — scroll-anchor around `#load-older-sentinel`
  requests; strip the orphan-rendering branch from `distributeThreads()`.
- `tutor/static/app.css` — `#load-older-indicator` styles; remove
  `#orphan-threads-section` rules.

No changes to `WebSink`, SSE pipeline, `ThreadStore`, or `FollowupThreadPool`.

## Behavior notes (for implementer and reviewer)

- **Empty state:** when total entries ≤ 50, `has_more=False`, no sentinel is
  rendered. The indicator div is still present but invisible (no HTMX request
  ever runs to toggle its `htmx-request` class). Same on first start.
- **Initial scroll position:** the app loads and the existing sticky-bottom
  logic auto-scrolls to the bottom. The sentinel at the top of
  `#stream-pane` is far from the viewport, so `intersect once` does not fire
  on load. Only when the user scrolls up does auto-load engage.
- **Cursor-not-found (user deleted the currently-oldest rendered line in
  another tab):** endpoint returns 404; HTMX fires `htmx:responseError`, the
  sentinel stays as-is, and its `once` trigger has already consumed — so
  auto-loading silently halts. A refresh recovers. Not worth extra plumbing.
- **New explanations via SSE:** append at bottom (unchanged). Does not affect
  the cursor — cursor tracks oldest loaded, not newest.
- **Deletion via `tutor_entry_removed`:** removes the `.line` by id if it's
  in the DOM; no-op otherwise. If the deleted line happened to be the
  current `oldest_id` on the sentinel, the sentinel's cursor becomes stale —
  next scroll-up auto-fire 404s silently (see above).
- **Thread anchors older than current window:** invisible in the list view
  until auto-load reaches their anchor line (no "Other threads" UI any
  more). Threads are not lost — the server-side `ThreadStore` still holds
  them, direct `/threads/{id}` URLs still resolve, and they reappear under
  their line once it loads.
- **Assumption behind silent hiding:** every orphan is "anchor not yet
  loaded," not "anchor deleted." This holds because
  `FollowupThreadPool.delete_tutor_entry` cascade-deletes threads with the
  matching anchor. If someone hand-edits `state/tutor.json` to remove an
  entry without going through the pool, threads pointing at it would become
  permanently invisible in the UI; direct URL access still works.
- **IntersectionObserver support:** the `hx-trigger="intersect"` modifier
  relies on the browser `IntersectionObserver` API, which is universally
  available in modern browsers. No polyfill needed.

## Verification

1. `make lint` — must pass (basedpyright + whatever else the Makefile wires).
2. Manual browser test with a `state/` that has ≥120 entries (create synthetic
   entries by running the tutor against a long input, or hand-edit
   `state/tutor.json`):
   - Fresh load: exactly 50 lines visible, viewport at bottom, no auto-load
     fires (confirm via network tab — no `/partials/older` request yet).
   - Scroll to top: once the sentinel enters the viewport, a
     `/partials/older` request fires and 50 older lines appear above the
     previous oldest. The content the user was looking at stays fixed in
     place (no perceived jump), and no second auto-load fires immediately.
   - Continue scrolling up: each time you approach the new top, another
     batch auto-loads.
   - Eventually reach the beginning: on the last successful load the
     response contains no sentinel, so further scroll-up triggers nothing.
   - While a batch is in flight, the "Loading older…" indicator is visible;
     it disappears on completion.
   - New SSE explanation while viewing older window: appears at bottom
     (sticky-bottom only activates if user was at bottom); scroll is not
     forced.
   - Delete a line via its Delete button: line disappears; no errors; further
     auto-loads still work (as long as the deleted line wasn't the sentinel's
     current cursor — see Behavior notes).
   - Thread that anchors to an unloaded older line: not visible anywhere in
     the list view. After auto-load reaches its anchor, it appears beneath
     the anchor line. Confirm there is no "Other threads" section in the
     DOM.
3. If a small entry count fixture is used (≤50), verify no sentinel is
   rendered (inspect DOM for absence of `#load-older-sentinel`) and
   scrolling to the top causes no request.

## Out of scope

- CSS truncation of collapsed raw lines (separate win; not requested now).
- "Jump to top/bottom" controls.
- Virtualization or infinite scroll.
- Persisting how many pages the user loaded across reloads.
