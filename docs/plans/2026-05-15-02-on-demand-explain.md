# On-demand explain via per-line button

## Context

Today every stdin line triggers a Claude call in `stdin_loop` (`tutor/core.py:75-123`). The model decides what's worth explaining via the `<<skip>>` token, but tokens are spent on every line either way. The user wants explanations to be paid for only on lines they pick.

New flow:

- stdin lines land in the UI immediately as **unexplained entries** (raw text only, no Claude call).
- An unexplained line shows an `[Explain]` button (in the existing tap-to-expand `.line-detail` panel, alongside where `[Ask]` lives today — no CSS changes).
- Clicking `[Explain]` sends the target line plus the last 100 raw lines as context to the explain client, stores the result, and replaces the line in-place with the current explained variant (which has `[Ask]` and `[Delete]`). 100 matches the context window the thread (Ask) flow already uses.
- Unexplained lines persist across runs so the user can still click `[Explain]` on old entries.
- The model-side `<<skip>>` rule disappears — the user is the filter now.

Each `[Explain]` click spawns a **fresh, short-lived Claude session** rather than reusing one persistent session. With 100 lines of raw context already shipped per call, the persistent session's marginal value (cross-click memory of sporadically-explained lines) is small and brings real downsides (drift, click-order confusion, growing context). Fresh-per-click is also a meaningful simplification: the cross-run session resume, the tutor-entry preamble replay, and the explain-session id file all go away. Cost: ~1–3s subprocess startup per click; benefit: predictable, parallelizable, simpler code.

## Implementation steps

### 1. Data model — `tutor/types.py`

- `TutorEntry.explanation: str` → `explanation: str | None = None`.
- Replace the sink protocol method `on_explanation(raw, text)` with two methods that carry the entry id:
  - `on_entry_appended(entry: TutorEntry)` — fired by `stdin_loop` per new raw line.
  - `on_entry_explained(entry: TutorEntry)` — fired by the explain handler after a successful Claude response.

`LineRecord.explanation` is already `str | None`; no change there.

### 2. Persistence — `tutor/tutor_store.py`

- `load()`: build entries via `TutorEntry(raw=e['raw'], explanation=e.get('explanation'), id=e['id'])`. JSON `null` round-trips as `None`; existing files (which always carry a string) load unchanged.
- Add `update_explanation_async(entry_id: str, explanation: str) -> bool` — load, mutate in place, atomic write, return False if not found. Used by the explain endpoint.

### 3. stdin pipeline — `tutor/core.py:75-123`

Rewrite `stdin_loop`:

- Drop the `ClaudeSDKClient` parameter and all session-id bookkeeping (session id is now saved in the explain handler).
- Keep the regex filter, blank-line skip, same-as-previous dedup, the `stop_event` guard, and `sink.on_raw_line` for `tutor.log`.
- For each surviving line: build `TutorEntry(raw=raw_line, explanation=None)` and call `sink.on_entry_appended(entry)`.

New signature: `async def stdin_loop(sink, filter_re, stop_event, *, use_thread=False, input_file=None)`.

### 4. Explain client lifecycle — `tutor/web.py`

- Delete `connect_with_fallback` (or strip it to just constructing `ClaudeAgentOptions` from args + system prompt). No long-lived `ctx.client`, no replay, no resume.
- Delete `WebContext.client` and `WebContext.session_path` (the `state/session.id` file is no longer used). Keep `WebContext.explain_options`: a pre-built `ClaudeAgentOptions` factory or the args/system-prompt pair the handler needs to spin up a one-shot client.
- Delete the tutor-entry preamble replay path entirely.
- The `asyncio.create_task(stdin_loop(...))` call drops the client argument; `stdin_loop` no longer needs anything Claude-related.
- Cross-run `state/session.id` file becomes vestigial — remove its read/write (the thread-pool session ids in `state/threads/*.json` are unaffected, since each thread already owns its own session id).

### 5. Prompt — `tutor/prompts.py`

- Drop the `skip_token` parameter and the "Decision rule / EXACTLY `SKIP`" block from `build_base_system_prompt` / `build_system_prompt`.
- Replace with one sentence: each user message is a target line preceded by surrounding context; explain the target line.
- Add `build_explain_user_message(target: str, context: list[str]) -> str`, formatting roughly:

  ```
  Recent context (oldest first):
  ---
  > {ctx[0]}
  ...
  ---
  Explain this line:
  {target}
  ```

- Add module constant `EXPLAIN_CONTEXT_K = 100` (matches the thread system-prompt window).
- `tutor/args.py`: remove `DEFAULT_SKIP_TOKEN` and the `--skip-token` argparse flag.

### 6. Explain endpoint — `tutor/web.py`

New route inside `build_app`:

```python
@app.post('/commands/explain', response_class=HTMLResponse)
async def explain(entry_id: Annotated[str, Form()]) -> HTMLResponse:
    entries = ctx.tutor_store.load()
    idx = next((i for i, e in enumerate(entries) if e.id == entry_id), -1)
    if idx < 0:
        raise HTTPException(404, 'entry not found')
    target = entries[idx]
    if target.explanation is not None:
        return HTMLResponse(_render_line(ctx.env, target))  # idempotent re-render
    context_raws = [e.raw for e in entries[max(0, idx - EXPLAIN_CONTEXT_K):idx]]
    user_msg = build_explain_user_message(target.raw, context_raws)
    buf: list[str] = []
    try:
        async with ClaudeSDKClient(options=ctx.explain_options) as client:
            await client.query(user_msg)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    buf.extend(b.text for b in msg.content if isinstance(b, TextBlock))
    except Exception as exc:
        ctx.sink.on_error(f'explain failed: {exc}')
        raise HTTPException(500, str(exc)) from exc
    explanation = ''.join(buf).strip()
    if not explanation:
        ctx.sink.on_error('explain produced empty response')
        raise HTTPException(502, 'empty explanation')
    await ctx.tutor_store.update_explanation_async(entry_id, explanation)
    updated = TutorEntry(raw=target.raw, explanation=explanation, id=target.id)
    ctx.sink.on_entry_explained(updated)
    return HTMLResponse(_render_line(ctx.env, updated))
```

A fresh `ClaudeSDKClient` is built per request from `ctx.explain_options` (a `ClaudeAgentOptions` carrying model id + system prompt, built once at startup). No lock needed — concurrent clicks can run in parallel. The originating tab's `hx-target="#line-{id}" hx-swap="outerHTML"` consumes the direct response; other tabs get the SSE OOB swap. Double-click of the same entry: both requests start a Claude call, both write to the store with `update_explanation_async`; the second arrival overwrites the first's explanation. Acceptable — the result is still a valid explanation. (If we want to suppress the second call entirely, an in-memory `set[entry_id]` of in-flight ids in `WebContext` is a small addition.)

### 7. Template — `tutor/templates/partials/line.html`

Branch on `entry.explanation`:

- **Explained** (current behavior): `.explanation-body` + `[Ask]` + `[Delete]`.
- **Unexplained**: no body; `.line-actions` shows `[Explain]` + `[Delete]`. The `[Explain]` form:

  ```jinja
  <form hx-post="/commands/explain" hx-target="#line-{{ entry.id }}" hx-swap="outerHTML">
    <input type="hidden" name="entry_id" value="{{ entry.id }}">
    <button type="submit" class="btn btn-ask">Explain</button>
  </form>
  ```

Both branches keep the `<section class="line" id="line-{{ entry.id }}" ...>` wrapper so OOB swaps work. No CSS change: `[Explain]` lives inside `.line-detail`, exposed by the existing tap-to-expand pattern.

### 8. Index + older_lines templates — `tutor/templates/index.html:33-35`, `tutor/templates/partials/older_lines.html:9-12`

The loops currently call `render_markdown(entry.explanation)` unconditionally. Guard it:

```jinja
{% set raw_escaped = entry.raw | e %}
{% set explanation_html = render_markdown(entry.explanation) if entry.explanation is not none else '' %}
{% include 'partials/line.html' %}
```

### 9. WebSink — `tutor/web_sink.py`

- Add an `_render_line(entry)` helper shared with the explain endpoint.
- Replace `on_explanation` with:
  - `on_entry_appended(entry)` — `append_async` to tutor store, broadcast SSE event `entry_appended` carrying the unexplained partial.
  - `on_entry_explained(entry)` — broadcast SSE event `entry_explained` carrying the explained partial with `hx-swap-oob="outerHTML"` targeting `#line-{id}`. Also write the `--- explanation for: ... ---` block to `tutor.log` (currently done in `on_explanation`).
- `index.html`: rename `sse-swap="explanation"` on `#stream-pane` to `sse-swap="entry_appended"`. Add `entry_explained` to the `#sse-buffer` `sse-swap` list.

### 10. ThreadPool / replay

No changes expected — `LineRecord.explanation` is already optional, and `build_thread_system_prompt` handles a None anchor.explanation. Ask is only offered on explained lines, so anchor.explanation is non-None in practice. Worth a manual smoke-test where a thread's surrounding context includes unexplained entries.

### 11. Tests — `tests/`

- `test_args.py`: drop `DEFAULT_SKIP_TOKEN` import/assertions.
- `test_prompts.py`: drop skip_token cases, drop `skip_token` from `_base_ns`, add cases for `build_explain_user_message` (formatting, ordering, empty-context edge).
- `test_core.py`: rewrite for the new `stdin_loop` (no client, no `save_session_id`, emits `on_entry_appended`). Drop tests covering query failures and session-id save failures — that surface is gone.
- `test_web_sink.py`: replace explanation tests with `on_entry_appended` (event `entry_appended`, fragment contains `Explain` button, store has entry with `explanation is None`) and `on_entry_explained` (event `entry_explained`, fragment contains `hx-swap-oob="outerHTML"`, no extra persistence).
- `test_tutor_store.py`: add `update_explanation_async` happy + missing cases, plus a load-tolerance test for `"explanation": null`.
- `test_web.py`: add `/commands/explain` tests with `ClaudeSDKClient` mocked at the module boundary — happy path, unknown id → 404, already-explained → 200 idempotent (no client constructed), empty response → 502, client raises → 500. Drop any tests that relied on `state/session.id` resume behaviour.

## Critical files

- `tutor/types.py` — `TutorEntry.explanation: str | None`; sink protocol changes.
- `tutor/tutor_store.py` — None-tolerant load + `update_explanation_async`.
- `tutor/core.py` — Claude-free `stdin_loop`.
- `tutor/web.py` — `WebContext.explain_options` (replaces `.client`/`.session_path`), new `/commands/explain` route that spins up a one-shot `ClaudeSDKClient` per call, drop `connect_with_fallback` + resume + tutor-entry preamble, drop client arg from `stdin_loop`.
- `tutor/web_sink.py` — `on_entry_appended` + `on_entry_explained`, shared `_render_line`, log-file write moves.
- `tutor/prompts.py` — drop skip_token, add `build_explain_user_message`, `EXPLAIN_CONTEXT_K`.
- `tutor/args.py` — drop `--skip-token`.
- `tutor/templates/partials/line.html` — branch on `entry.explanation`.
- `tutor/templates/index.html`, `tutor/templates/partials/older_lines.html` — None-safe markdown render; rename SSE event.

## Verification

1. `make lint` and `make test` clean.
2. Pipe a few lines into a running instance; confirm each shows up immediately as unexplained.
3. Tap a line → click `[Explain]` → line is replaced in-place with explanation + `[Ask]` + `[Delete]`. The 100 preceding raw lines are used as context (eyeball it).
4. Open a second browser tab; click `[Explain]` in tab A; tab B updates via SSE OOB.
5. Restart the server with a mixed `state/tutor.json` (some entries explained, some not); confirm the UI renders both correctly and `[Explain]` still works on the old unexplained ones. Confirm `state/session.id` is no longer being read/written.
6. Click `[Ask]` on an explained line; thread flow still works (regression check).
