# Remove completed migration code

## Context

Two one-time migrations were introduced earlier and have now run on every
user's state directory:

- `TutorStore.migrate()` — back-fills `id` UUIDs onto legacy tutor entries
  (plan `docs/plans/2026-04-14-04-thread-anchor-idx.md` and related).
- `ThreadStore.migrate(tutor_entries)` — rewrites legacy `anchor_idx: int`
  fields into stable `anchor_id: str` references
  (plan `docs/plans/2026-04-15-04-delete-line-and-stable-anchor-id.md`).

Both migrations are idempotent and still execute on every GUI/terminal startup
even though no legacy files remain. Their presence also forces defensive
fallbacks elsewhere (synthesising UUIDs in `load()`, `legacy_by_raw` matching
in the HTML export). All migration is complete, so this is dead code.

## Changes

### 1. `tutor/tutor_store.py`
- Delete `migrate()` (lines 65–85).
- Simplify `load()` (lines 21–41): drop the `uuid4().hex` fallback on line 34,
  read `e['id']` directly. Remove the docstring paragraph that references
  `migrate`.
- Remove the now-unused `from uuid import uuid4` import.

### 2. `tutor/thread_store.py`
- Delete `migrate()` (lines 72–97).
- Simplify `_load_file()` (lines 114–128): replace `data.get('anchor_id', '')`
  with `data['anchor_id']`. Orphans still legitimately have `anchor_id=''` in
  the file, but the key must be present post-migration.
- Remove the `TYPE_CHECKING` import of `TutorEntry` (only used by `migrate`).

### 3. `tutor/gui.py`
- At lines 724–725, remove both `tutor_store.migrate()` and
  `store.migrate(tutor_store.load())`.

### 4. `tutor/terminal.py`
- At line 66, remove `tutor_store.migrate()`.

### 5. `tutor/html_export.py`
- In `_build_html()` (lines 147–174), remove the `legacy_by_raw` dict,
  `rendered_legacy_raws` set, and raw-text fallback match. After the change:
  - `threads_by_id` collects every thread keyed by `t.anchor_id`; threads
    with `anchor_id == ''` are skipped.
  - Each entry renders with `threads_by_id.get(entry.id, [])`.
  - Orphans = any thread whose `anchor_id` is empty or not in `live_ids`.
- Keep `_render_orphan_threads` and `anchor_raw` display on orphans — the
  live-UI contract for anchor-less threads, not a migration artefact.

### 6. `tutor/types.py`
- Line 56: update the inline comment on `ThreadMeta.anchor_id`. Currently
  "empty for legacy files that could not be migrated"; change to "empty for
  orphan threads whose anchor entry was deleted".

## Out of scope / intentionally kept

- `ThreadStore.save_thread()` keeps writing `anchor_raw` — used for orphan
  display in the GUI and HTML export, unrelated to migration.
- The mixed thread-id filename formats described in
  `2026-04-14-12-thread-id-format.md` need no code change: both formats are
  matched by `*.json` glob and there is no migration code.
- `anchor_idx` local variables in `tutor/thread_pool.py` (lines 89–96) are
  just list indices, not the removed persisted field.

## Verification

1. `uv run --frozen basedpyright` — no new type errors.
2. `uv run --frozen ruff check` — no unused imports / dead branches.
3. Smoke test GUI mode against existing `state/` dir — left pane loads,
   threads render under their anchor lines, orphans still appear.
4. Smoke test terminal mode — confirm resume/reload still works.
5. Run HTML export and confirm the output contains no double-rendering.

## Critical files

- `tutor/tutor_store.py`
- `tutor/thread_store.py`
- `tutor/gui.py`
- `tutor/terminal.py`
- `tutor/html_export.py`
- `tutor/types.py`
