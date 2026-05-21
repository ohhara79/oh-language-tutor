# Show language-mismatch error inline on the rejected line

## Context

The previous change rejects an Explain request when the target text's
script disagrees with the configured Learning Language and surfaces the
reason via the global toast at `#toast-container`
(`tutor/templates/partials/toast.html`). The user reports the toast is
hard to read — long mismatch messages have no width cap, so the toast
stretches across the bottom of the viewport and visually blends into
the sentence list rows behind it.

Move the error from a fixed-position bottom-right toast to **inline on
the line that triggered it**, where it's anchored next to the action
that caused the failure and the surrounding list doesn't shift. The
line stays in its unexplained state so the user can click Explain again
after fixing the Learning Language in the menu.

## Approach

The existing Explain form already targets `#line-{{ entry.id }}` with
`hx-swap="outerHTML"`, so we just need the mismatch response to return
the same line re-rendered with an inline error region, instead of
raising HTTPException(400) and broadcasting a toast.

### Change set

1. **`tutor/web_sink.py:WebSink.render_line`** — add a keyword-only
   `error_message: str | None = None` parameter and pass it into the
   template render context.

2. **`tutor/templates/partials/line.html`** — when `error_message` is
   set, render an inline error block inside `.line-detail`, above the
   existing Explain button. The unexplained branch (the `{% else %}`
   today) keeps its Explain form, so the user can retry without
   reloading. The error block carries an `aria-live="polite"` attribute
   so screen readers announce it on swap.

   ```html
   {% if error_message %}
     <div class="line-error" role="alert" aria-live="polite">
       {{ error_message | e }}
     </div>
   {% endif %}
   ```

3. **`tutor/static/app.css`** — add a `.line-error` rule scoped under
   `.line-detail` so it sits in the explanation column, with a distinct
   contained look: dark-red text on a light-red background (matching
   the toast's red), padding, rounded corners, normal text wrapping,
   and a left border accent. The rule also belongs in the existing
   `@media (prefers-color-scheme: dark)` block.

4. **`tutor/web.py:explain()`** — replace the mismatch branch:

   ```python
   mismatch_msg = detect_language_mismatch(source_language, target.raw)
   if mismatch_msg is not None:
       return HTMLResponse(
           content=session.sink.render_line(target, active=True, error_message=mismatch_msg),
           status_code=400,
       )
   ```

   Keep the 400 status so the HTTP semantics still say "request
   rejected," but return the swap body so HTMX replaces the line. (HTMX
   swaps on 4xx by default only when configured; we'll explicitly
   include the response in the swap by setting an `HX-Reswap` /
   `HX-Retarget` header if needed — see the **HTMX 4xx swap** note
   below.) Drop the `session.sink.on_error(mismatch_msg)` call so no
   toast fires for this case (other on_error callers — explain stream
   failures, oversized extras — keep the toast as their channel).

### HTMX 4xx swap

By default HTMX will not swap on a non-2xx response. Two options:

- **Preferred:** return `status_code=200` for the mismatch (with the
  re-rendered line as the body). The user sees the inline error; the
  HTTP layer treats the swap as "successful render of a rejected
  state." This is the simplest and matches how the `already-explained`
  branch in the same route returns 200 with a re-rendered line.
- Alternative: keep 400 and add an `htmx:responseError` handler in
  `tutor/static/app.js` to perform the swap manually. Heavier, no
  win.

Go with the 200 approach. The state on disk (line stays unexplained)
already encodes the rejection.

### What is *not* changing

- `tutor/languages.py:detect_language_mismatch` — unchanged.
- `tutor/templates/partials/toast.html` and the `#toast-container`
  styling — unchanged; the toast remains the channel for transient
  stream failures and other system errors.
- The Explain form, button, and `htmx:configRequest` audience
  injection — unchanged. Same form re-renders, ready for retry.

## Files to touch

- `tutor/web_sink.py` — extend `render_line` with `error_message`.
- `tutor/templates/partials/line.html` — render the inline error block
  on the unexplained branch.
- `tutor/static/app.css` — add `.line-error` styles (light + dark
  modes).
- `tutor/web.py` — replace the `on_error` + 400 mismatch path with an
  `HTMLResponse(render_line(..., error_message=msg))` returning 200.

## Tests

- `tests/test_web.py::test_post_explain_rejects_language_mismatch` —
  update to expect 200, the entry still unexplained, the response body
  containing both `'Korean'` and `'English'` from the error message,
  the `line-error` class, and `id="line-u-mm"` (proving the section is
  re-rendered for HTMX `outerHTML` swap to consume). Also assert
  `fake_client_factory.constructed == []` to confirm no Claude session
  ran.
- `tests/test_web_sink.py` — add a small `render_line` test that
  asserts `error_message='oops'` puts the message into the rendered
  HTML and that the Explain form is still present (so the user can
  retry).

## Verification

1. `uv run --frozen pytest tests/test_web.py tests/test_web_sink.py
   tests/test_languages.py`
2. `make lint`
3. Manual smoke: start the web app, set Learning Language to
   `English`, click Explain on a Korean line. Expect the line to
   re-render in place with a red inline error box reading
   "Text appears to be Korean, but Learning Language is set to
   'English'. …", the Explain button still present, and the sentence
   list around it unchanged (no toast). Fix the Learning Language to
   `Korean`, click Explain again — expect the normal streamed
   explanation, with the previous error block gone.
4. Confirm a streaming-time failure still uses the toast: temporarily
   force `_stream_explain` to raise (or pick an entry whose extras
   blow the prompt budget) — the toast at bottom-right still appears.
