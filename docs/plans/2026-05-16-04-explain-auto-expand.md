# Auto-expand line after Explain completes

## Context

Clicking the per-line **Explain** button generated the explanation, but the
swapped-in `<section class="line">` had no `.active` class, so CSS kept
`.line-detail` hidden (`tutor/static/app.css:235`). The user had to click the
sentence a second time to see the result they just asked for.

`render_line` is also re-broadcast as an OOB outerHTML swap by
`on_entry_explained` (`tutor/web_sink.py`). That SSE message reaches the
requesting tab too and arrives after the HTTP response, so a fix that only
patched the HTTP response would be immediately collapsed back by the SSE
swap. Both code paths needed to render with `.active`.

## Approach

Add a keyword-only `active` flag to `WebSink.render_line` (default `False`).
The Jinja template conditionally appends `active` to the section's class list.
Both the `/commands/explain` HTTP response and `on_entry_explained` render
with `active=True` so the line is expanded everywhere a freshly-explained
line is delivered. Initial page render and `on_entry_appended` keep the
default (collapsed), so existing explained lines from prior sessions stay
collapsed on reload.

## Files touched

- `tutor/templates/partials/line.html` — `class="line{% if active %} active{% endif %}"` on the section.
- `tutor/web_sink.py` — `render_line(entry, *, active=False)`; `on_entry_explained` renders with `active=True` and the OOB string-replace now matches `class="line active"`.
- `tutor/web.py` — `/commands/explain` returns `render_line(..., active=True)` in both branches.

## Verification

- `make lint` clean.
- Manual: click Explain on an unexplained line → explanation visible without a
  second click. Open a second tab on the same view, click Explain in tab 1 →
  line expands in tab 2 when SSE arrives. Click another line → existing
  one-active-at-a-time toggle (`tutor/static/app.js:72`) still works. Reload →
  prior-session explained lines render collapsed.
