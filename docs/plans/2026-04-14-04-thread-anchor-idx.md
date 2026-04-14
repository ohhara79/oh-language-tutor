# Stable thread ↔ tutor entry linkage via `anchor_idx`

## Context

Today, a followup thread json file only records `anchor_raw` — the raw text of
the line it's anchored to. html_export (`tutor/html_export.py:147-160`) maps
threads back to tutor.json entries by matching on that raw string. Two problems:

1. **Ambiguity.** If two lines in tutor.json have identical raw text, all
   threads anchored to that text collapse onto the first match.
2. **No durable link.** tutor.json's existing `line_idx` field is written but
   immediately discarded on load — `gui.py:337` re-generates registry indices
   from scratch via `add_line(entry.raw)`. Nothing persists a stable identity
   for a tutor entry.

The goal is a single durable identity for a tutor entry — its **array position
in tutor.json** — and to have each thread record that position.

## Design

- **tutor.json entry schema:** drop `line_idx`. Entries become `{raw,
  explanation}`. Identity of an entry is its array position (0-indexed). This
  is safe because the store is strictly append-only.
- **thread json schema:** add `anchor_idx: int` — the tutor.json array position
  of the anchored entry. Keep `anchor_raw` unchanged (used for orphan
  rendering).
- **GUI:** every `LineBlock` carries a `tutor_pos` alongside its existing
  registry idx. When the user clicks Ask, `OpenThreadCmd.anchor_idx` is set to
  `tutor_pos`, not the registry idx.
- **Command boundary:** `OpenThreadCmd` carries only `anchor_idx` (tutor
  position). The pool resolves the anchor's `raw` + `explanation` by reading
  the `TutorStore` at that position — no registry-idx plumbing through the
  command channel.

### Why tutor position, not registry idx

The registry (`tutor/registry.py`) tracks *every* stdin line — blank, filtered,
duplicate, and SKIP — so registry idx ≠ tutor.json position. Across restarts
the registry re-indexes from 0, so registry idx is not durable either.
tutor.json's array position *is* durable (append-only) and is the natural
foreign key for threads.

### Why the pool reads from `TutorStore`, not the registry

At `open_thread` time the pool needs the anchor's `raw` and `explanation` for
the system prompt. Both are already persisted in tutor.json at the position
carried by `anchor_idx`, so the pool loads the store and indexes into it. The
registry is still used for `recent(100)` context lines, but no longer for
anchor lookup — which means only *one* identity (tutor position) crosses the
command boundary.

## Back-compat

- **Thread json without `anchor_idx`:** loader defaults to `-1`. html_export
  tries `anchor_idx` first; if `-1`, falls back to the existing `anchor_raw`
  string match. New threads always get a real idx.
- **tutor.json with legacy `line_idx`:** loader reads `{raw, explanation}` and
  silently ignores `line_idx` if present. Next write produces the new shape.

## Files to change

| File | Change |
|---|---|
| `tutor/types.py:25-30` | Remove `line_idx` from `TutorEntry`. |
| `tutor/types.py:46-54` | Add `anchor_idx: int = -1` to `ThreadMeta`. |
| `tutor/tutor_store.py:23` | Read only `raw` + `explanation`; tolerate extra keys. |
| `tutor/tutor_store.py:37` | Write only `raw` + `explanation`. |
| `tutor/thread_store.py:40-46` | Serialize `anchor_idx`. |
| `tutor/thread_store.py:67-77` | Deserialize `anchor_idx`, default to `-1` when absent. |
| `tutor/thread_pool.py:69-95` | Inject `TutorStore`; look up anchor by `anchor_idx`; store `anchor_idx` in `ThreadMeta`. |
| `tutor/types.py` | `OpenThreadCmd` carries only `anchor_idx` (no `registry_idx`). |
| `tutor/core.py` | Dispatch passes only `anchor_idx` to `pool.open_thread`. |
| `tutor/gui.py:144-154` | `LineBlock` gains `tutor_pos`; Ask button emits it. |
| `tutor/gui.py:325-342` | `_restore_tutor_entries`: assign `tutor_pos = enumerate index`. |
| `tutor/gui.py:353-367` | `on_explanation`: compute `tutor_pos` as current tutor_store length before append, pass to `LineBlock`. |
| `tutor/gui.py:431-441` | Ask handler passes `LineBlock.tutor_pos` as `OpenThreadCmd.anchor_idx`. |
| `tutor/gui.py` (pool construction) | Pass `tutor_store=` into `FollowupThreadPool`. |
| `tutor/html_export.py:146-161` | For each tutor entry at position `i`, collect threads with `anchor_idx == i`; for threads with `anchor_idx == -1`, fall back to raw-text matching; remaining threads are orphans. |

No changes needed in `tutor/core.py` — core still works in registry-idx terms,
and the GUI translates at the boundary.

## Verification

1. **Fresh run.** Delete state dir, run through a few lines, open a thread,
   send a message, restart, reopen the thread. Confirm thread json has
   `anchor_idx` matching the line's position in tutor.json.
2. **Duplicate raw text.** Feed the same raw line twice. Open a thread on the
   second occurrence. Restart and export HTML. Confirm the thread appears
   under the second line, not the first.
3. **Legacy thread file.** Craft a thread json with `anchor_raw` but no
   `anchor_idx`. Confirm it loads (anchor_idx = -1) and still renders under
   the matching tutor entry in the HTML export.
4. **Legacy tutor.json.** Start with a tutor.json that still has `line_idx`
   fields. Confirm it loads, the restored left pane looks right, and the next
   append rewrites the file without `line_idx`.
5. **Orphan thread.** Open a thread, then hand-edit tutor.json to remove its
   entry. Confirm the HTML export lists it under "Orphan threads".
6. Run `uv run --frozen pytest` if a suite exists; otherwise exercise the
   scenarios above in the TUI.
