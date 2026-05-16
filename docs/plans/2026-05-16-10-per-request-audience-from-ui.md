# Move source-language / target-language / level from CLI to web UI

## Context

The audience settings are currently required CLI flags (`--source-language`, `--target-language`, `--level`) parsed in `tutor/args.py:21-36` and baked into the explain system prompt once at server startup (`tutor/web.py:325`, `tutor/web.py:331-336`). They also seed the `FollowupThreadPool` constructor (`tutor/web.py:358-360`) so every ask-thread's system prompt is built from those same launch-time values.

Now that explain is user-initiated (no automatic pipeline) and one server instance can read several different SRT files in a session, baking these values in at launch is awkward — you'd have to restart to change languages. Moving them into the browser, persisted in `localStorage`, lets the user switch freely and have their preferences survive a reload. CLI flags for these three become dead weight.

`--extra-system-prompt` stays CLI-driven (it's source-specific, not audience-specific). `--explain-model`, `--ask-model`, `--state-dir`, etc. also stay on the CLI.

## Approach

**Frontend (UI + persistence)**

Replace the read-only `<p class="meta">…</p>` line in `tutor/templates/index.html:14` with a small settings strip in the header containing:

- `<input type="text" id="cfg-source-language">` (free text — CLI never validated)
- `<input type="text" id="cfg-target-language">`
- `<select id="cfg-level">` with `beginner` / `intermediate` / `advanced`

In `tutor/static/app.js`, on DOM-ready: hydrate the three inputs from `localStorage` keys `tutor.sourceLanguage`, `tutor.targetLanguage`, `tutor.level`, falling back to `'English'` / `'Korean'` / `'intermediate'`. Persist on each `change`/`input` event.

Use HTMX's `htmx:configRequest` event to inject the three current values into every outbound POST whose path is `/commands/explain` or `/commands/open_thread`. (No need to inject into `/commands/send_message` — the system prompt is fixed at thread open and the session keeps it.)

**Server (per-request settings)**

`/commands/explain` (`tutor/web.py:274-289`): add three `Annotated[str, Form()]` parameters. Validate `level ∈ {beginner, intermediate, advanced}`; return HTTP 400 on invalid. Build a fresh `ClaudeAgentOptions` per request — its `system_prompt` is rebuilt from these three values plus the optional extras file. Drop the shared `ctx.explain_options` field.

`/commands/open_thread` (`tutor/web.py:224-235`): accept the same three fields, validate `level`, pass them through to `pool.open_thread(...)`.

`FollowupThreadPool.open_thread` (`tutor/thread_pool.py:79-121`): accept `source_language`, `target_language`, `level` as parameters, use them to call `build_thread_system_prompt` instead of the constructor-stored values. Drop the three from `__init__` — they're no longer launch-time state.

**Prompt construction**

`tutor/prompts.py`: keep `build_base_system_prompt(source, target, level)` as-is. Refactor `build_system_prompt(args)` into something callable per-request, e.g. `build_system_prompt(source_language, target_language, level, extras_text)`. Pre-read the extras file once at startup into the `WebContext` (one place to fail fast on bad path) and pass `extras_text` into the per-request builder. Apply the `MAX_SYSTEM_PROMPT_BYTES` check there — exceeded → return HTTP 400 (don't crash the server on a long extras file at request time; the per-request prompt size is mostly stable so this should only fire on the first request after a misconfigured launch).

**Cleanup**

- Remove `--source-language`, `--target-language`, `--level` from `tutor/args.py:21-36`.
- Remove `source_language` / `target_language` / `level` Jinja variables from the render call in `tutor/web.py:149-151`.
- Remove the `<p class="meta">` line that consumed them in `index.html:14` (replaced by the settings strip).
- Add minimal CSS for the settings strip in `tutor/static/app.css` (label + input row, comfortable on mobile).

**Tests**

- `tests/test_args.py`: drop the three test cases that exercised the removed flags (`test_missing_source_language_exits`, the level-default test, etc.).
- `tests/test_web.py`: update `_build_ctx` helper to no longer pre-set CLI audience values; update each explain test to POST `source_language`, `target_language`, `level` form fields. Add: explain with invalid level returns 400. Add: explain uses the request's source/target/level in the system prompt (assert by inspecting `fake_client_factory.constructed[0]` options).
- `tests/test_thread_pool.py`: update `FollowupThreadPool` construction to drop the three params; pass them into `open_thread` instead.

**Docs**

- `README.md`: remove the three flags from the CLI table, simplify both invocation examples (they currently lead with `--source-language English --target-language Korean --level intermediate`), and add a one-liner explaining that audience settings now live in the browser and persist in `localStorage`.

## Files to modify

- `tutor/args.py`
- `tutor/prompts.py`
- `tutor/web.py`
- `tutor/thread_pool.py`
- `tutor/templates/index.html`
- `tutor/static/app.js`
- `tutor/static/app.css`
- `tests/test_args.py`
- `tests/test_web.py`
- `tests/test_thread_pool.py`
- `README.md`

## Reused existing code

- `build_base_system_prompt(source_language, target_language, level)` (`tutor/prompts.py:23`) — unchanged signature; called per-request.
- `build_thread_system_prompt(source_language, target_language, level, anchor, context_lines)` (`tutor/prompts.py:144`) — unchanged signature; called per `open_thread`.
- `MAX_SYSTEM_PROMPT_BYTES` check (`tutor/prompts.py:75-82`) — moved out of startup into the per-request prompt builder.
- HTMX `htmx:configRequest` — already loaded; the path-aware listener is a small addition to `tutor/static/app.js`.

## Verification

1. `make lint` is clean.
2. `uv run --frozen main.py` (no audience flags) starts successfully; the previous required-flag error from argparse is gone.
3. Open the UI, see three settings controls in the header. Change values, reload the page — values persist. Open a private window — defaults (`English` / `Korean` / `intermediate`) appear.
4. Pipe a few lines in, click Explain. Tail `state/tutor.log` and confirm the constructed system prompt reflects the values shown in the UI.
5. Change the source/target in the UI, explain another line, confirm the new prompt is used (different language wording in the log).
6. Click Ask on an explained line. Inspect `state/threads/*.json` — the metadata is fine; check the log for the thread system prompt and confirm it uses the UI values.
7. POST `/commands/explain` directly with `level=garbage` (e.g. via `curl`) — receive HTTP 400.
8. `uv run --frozen pytest` — all tests pass, including the two new assertions.
