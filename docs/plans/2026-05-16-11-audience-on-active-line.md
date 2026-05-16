# Move audience controls onto the active line; freeze audience on the entry

## Context

After moving audience settings to a header strip in the previous change, the controls become unreachable in normal use: the `intersect once` load-older trigger (`tutor/templates/index.html:25-30` + `tutor/static/app.js:206-220`) keeps prepending older content above the user's scroll position, so the un-pinned header drifts further off-screen with every auto-load. The user can never reach the top to change settings.

Fix it by moving the three controls out of the header and into the `.line-detail` panel of unexplained lines, directly above the Explain button. Because `body.view-list .line:not(.active) .line-detail { display: none; }` (`tutor/static/app.css:260`), only the currently tapped line shows its detail panel — so exactly one set of controls is visible at any time, with no clutter.

Second decision: the audience the user chose at Explain time should be **frozen on the entry**. When Ask is later clicked on an already-explained line, the thread is opened with the line's stored audience, not the live localStorage value. This keeps follow-up threads consistent with how the line was originally explained, even if the user is now reading a different SRT file with different settings.

## Approach

**UI — per-line controls**

- `tutor/templates/index.html`: remove `#cfg-strip` from `<header>`. Header reverts to title-only.
- `tutor/templates/partials/line.html`: in the `{% else %}` branch (unexplained line, lines 37–59), add a controls row above `.line-actions`:
  - `<input type="text" class="cfg-source-language">`
  - `<input type="text" class="cfg-target-language">`
  - `<select class="cfg-level">` with beginner/intermediate/advanced
  Use class selectors (not ids) since the row is repeated per line.
- The explained and streaming branches stay as they are — no controls there.

**JS — hydrate per active line**

`tutor/static/app.js`:
- Drop the one-time `cfgHydrate()` call.
- Extend the existing `raw-toggle` click handler (lines 71–86) so that whenever a line becomes active, the handler walks the controls inside its `.line-detail` and writes the current localStorage values into them.
- Persist on each control's `change` / `input` event (delegate at `#stream-pane`, identify by class).
- Narrow the `htmx:configRequest` injection: only inject `source_language` / `target_language` / `level` for `/commands/explain`. Drop `/commands/open_thread` from the inject set — open_thread no longer accepts these fields.
- When injecting, prefer the controls inside the line whose Explain form is being submitted (read from `evt.detail.elt.closest('.line')`); fall back to localStorage if no line context.

**CSS**

`tutor/static/app.css`: drop the header `.cfg-strip` block and add a compact `.line-cfg` row style (label + small input/select group, sized to sit comfortably above the action buttons on mobile).

**Persist audience on the entry**

`tutor/types.py` — `TutorEntry`:
- Add `source_language: str | None = None`, `target_language: str | None = None`, `level: str | None = None`. All optional so unexplained entries and legacy explained entries (written before this change) deserialize cleanly.

`tutor/tutor_store.py`:
- `load()` (line 49): read the three new fields with `e.get(...)`.
- `_write()` (line 131): include the three fields in each serialized dict.
- `update_explanation_async` (line 90): widen signature to also take `source_language`, `target_language`, `level` and persist them alongside the explanation in the same atomic write.

**Server**

`tutor/web.py`:
- `/commands/explain` (lines 283–318): no signature change; after the explain stream completes, `_stream_explain` (lines 113–149) calls `update_explanation_async(..., source_language, target_language, level)` so the audience is frozen onto the entry at the same moment as the explanation. Pass those three through `_stream_explain` as additional parameters.
- `/commands/open_thread` (lines 236–263): drop the three `Form()` parameters. Inside the handler, look up the entry via the existing `ctx.tutor_store.load()` path (already imported transitively), read `entry.source_language` / `entry.target_language` / `entry.level`, and fall back to `'English'` / `'Korean'` / `'intermediate'` if any are `None` (legacy entry). Call `_validate_audience` on the resulting triple, then pass into `pool.open_thread(...)`. If the entry is missing entirely, 404 — the pool already emits that error today via `_sink.on_error`, but a handler-level 404 is cleaner; check existing behavior before adding a new path.

**Reused existing code**

- `_validate_audience` (`tutor/web.py:72-80`) — unchanged, called from both endpoints (explain: request values; open_thread: stored-or-default values).
- `raw-toggle` click handler (`tutor/static/app.js:71-86`) — extended to also hydrate the newly-active line's controls.
- `htmx:configRequest` listener already added in the previous change — narrow its path set.
- `FollowupThreadPool.open_thread(... source_language, target_language, level)` — signature unchanged from the previous change; this plan does not touch the pool.
- Static-asset cache-buster (`tutor/web.py` `version`) — already wired through `index.html` and will invalidate the JS/CSS automatically on next run.

**Tests**

`tests/test_tutor_store.py`:
- Round-trip a `TutorEntry` whose three audience fields are populated.
- Write a legacy JSON file by hand (no audience keys), load it, assert the three fields read back as `None`.
- Update `update_explanation_async` tests for the wider signature.

`tests/test_web.py`:
- Adjust the explain happy-path test: after stream completion, assert the persisted entry carries the audience values from the request.
- Drop `test_post_open_thread_rejects_invalid_level` (open_thread no longer takes form audience; validation runs against the stored value, which was validated at explain time).
- Replace `test_post_open_thread_creates_and_broadcasts` audience-form-field assertion with: stored audience on the entry propagates to `pool.open_thread`; legacy entry (no stored audience) falls back to defaults.
- `_FakePool.open_thread` keeps the kwargs.

`tests/test_thread_pool.py`: no changes — pool surface is unchanged.

## Files to modify

- `tutor/types.py`
- `tutor/tutor_store.py`
- `tutor/web.py`
- `tutor/templates/index.html`
- `tutor/templates/partials/line.html`
- `tutor/static/app.js`
- `tutor/static/app.css`
- `tests/test_tutor_store.py`
- `tests/test_web.py`

## Verification

1. `make lint` clean; `uv run --frozen pytest` passes.
2. Open the UI. Tap an unexplained line — three controls appear above the Explain button. Change them, tap a different unexplained line — the new line's controls show the same values (localStorage shared).
3. Set level=`advanced`, click Explain. After streaming, inspect `state/tutor.json` — the entry has `source_language`, `target_language`, `level=advanced` populated.
4. Tap that now-explained line — no controls visible, just Ask + Delete.
5. Change the controls on a different unexplained line to level=`beginner`. Go back, click Ask on the previously-explained line. Inspect `state/tutor.log` — the thread's system prompt uses `advanced` (frozen on the entry), not `beginner`.
6. Scroll up far enough to trigger several rounds of auto-load — the missing-header problem is gone; settings remain reachable on any unexplained line you tap.
7. Stop the server, hand-edit `state/tutor.json` to remove the audience keys from one entry (simulating a legacy entry), restart, click Ask on that entry — opens cleanly using the hardcoded defaults; no crash, no 400.
