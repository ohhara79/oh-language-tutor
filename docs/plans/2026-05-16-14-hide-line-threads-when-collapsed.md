# Hide per-line question list inside the expanded explanation panel

## Context

After a user asks a question on an explained line, the question's heading is
shown in the per-line thread list (`.line-threads`). Today that list sits
between the raw-text button and `.line-detail`, so it stays visible in the
collapsed list view — every line with past questions becomes vertically taller
in the raw-text list, even when its explanation is not expanded.

Past questions should be hidden until the user taps the raw text to expand the
line, and shown *under* the explanation body (between the explanation and the
Ask/Delete buttons) when expanded.

## Approach

Move the `.line-threads` container from outside `.line-detail` to inside it, in
the `entry.explanation is not none` branch, placed after `.explanation-body`
and before `.line-actions`. Because `body.view-list .line:not(.active)
.line-detail { display: none; }` already hides the entire detail panel for
collapsed lines (`tutor/static/app.css:287`), threads are automatically hidden
in list view and revealed when the line becomes active — no new CSS rule
needed.

This works cleanly because:

- Threads can only exist for lines that already have an explanation (`Ask`
  requires the explained state). Placing `.line-threads` inside the
  `entry.explanation is not none` branch matches that invariant.
- `distributeThreads()` in `tutor/static/app.js:208-238` selects
  `.line-threads` by `data-anchor-id` regardless of DOM position, so no JS
  changes are needed.
- The streaming and unexplained branches don't render `.line-threads` (correct
  — no threads can exist in those states), so re-distribution lands only where
  it should.

## Changes

### `tutor/templates/partials/line.html`

Remove the top-level `.line-threads` div (previously line 4) and re-insert it
inside the explained branch, between the explanation body and the actions
form. Final structure of the explained branch:

```html
<div class="line-detail">
  {% if entry.explanation is not none %}
  <div class="explanation-body">{{ explanation_html | safe }}</div>
  <div class="line-threads" data-anchor-id="{{ entry.id }}"></div>
  <div class="line-actions">
    ...Ask / Delete forms...
  </div>
  ...
  {% endif %}
</div>
```

The `data-anchor-id` on the outer `<section>` is untouched — only the inner
thread container moves.

## Critical files

- `tutor/templates/partials/line.html` — relocates `.line-threads`.

No other files change:

- `tutor/static/app.js` — `distributeThreads()` already locates the container
  by attribute and works at any depth.
- `tutor/static/app.css` — the existing `.line-detail` hide rule hides the
  moved threads automatically; `.line-threads { margin: ...; }` and
  `.line-threads:empty { display: none; }` still apply unchanged.
- `tutor/web_sink.py` / `tutor/web.py` — the partial is rendered through
  `render_line()` (`tutor/web_sink.py:77`), which already passes `entry` and
  doesn't care about the inner layout.

## Verification

1. `make lint` — no type errors.
2. Run the dev server and open the web UI.
3. Pick a line that already has an explanation and at least one past question.
4. In the collapsed list view, confirm the line shows only the raw text — no
   question headings underneath.
5. Tap the raw-text button to expand the line. Confirm the order is: raw text
   (bold) → explanation body → past questions list → Ask/Delete buttons.
6. Tap another line; the previous line should collapse and again hide its
   questions. Tap the same line again to verify toggle-collapse hides
   questions.
7. Ask a new question on an expanded line. After the thread list SSE swap, the
   new question heading should appear inside the still-expanded panel, below
   the explanation. After collapsing, it disappears from the list view.
