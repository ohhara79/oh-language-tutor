# Improve TUI responsiveness

## Context

The Textual TUI feels sluggish to mouse and keyboard input. The user
reports that **ASK**, **DEL**, and **OPEN** all take roughly a second to
respond — and the lag is present even when **idle** (no streaming, no
new explanations arriving). DEL's handler does almost nothing (label
swap + timer + enqueue), so the bottleneck is not the handler body — it
is elsewhere on the event loop / in Textual itself.

### Likely root cause: widget count

The user's live `state/bladerunner/tutor.json` contains **752 tutor
entries**. Each entry becomes, in the left pane:

- 1 `LineBlock` (a `Horizontal` container) →
  - 1 `Label` (raw line)
  - 1 `Button` (ASK)
  - 1 `Button` (DEL)
- 1 `ExplanationBlock` (a `Static`)

That is **5 widgets per entry × 752 entries ≈ 3,760 widgets** in a
single scroll container, on top of everything on the right. Textual's
per-event work (hit-testing, CSS matching, DOM walks from
`query_one`/`query`, layout invalidation, repaint) scales with widget
count, so every click and keypress pays the price.

### Secondary blocking work on the UI loop

- `tutor_store.load()` reparses the ~600 KB `tutor.json` on each ASK
  click (`tutor/gui.py:589`) and again inside
  `pool.open_thread` (`tutor/thread_pool.py:88`). That's two 30–80 ms
  parses per ASK.
- `tutor_store.append()` reloads then rewrites the whole JSON on every
  new explanation (`tutor/tutor_store.py:29-33`) — an idle-ish UI still
  takes a hit every time a new line is explained.
- `_reopen_thread` mounts per-message widgets in a loop
  (`tutor/gui.py:641-645`).
- `_restore_tutor_entries` at startup mounts 752 × 2 widgets one-by-one
  (`tutor/gui.py:367-370`) — slow startup and, more importantly, each
  `mount()` triggers a layout pass.
- Every click handler does several `query_one`/`query` calls that walk
  a ~3.7 k-node DOM.

The intended outcome: clicks feel instant, including at idle.

## Approach

Two tiers. Ship tier 1 first (small, clearly correct); measure; do
tier 2 if sluggish remains.

### Tier 1 — quick wins

#### 1a. Cache `tutor.json` in `TutorStore`

Add an mtime+size-keyed in-memory cache to `TutorStore.load()` and
invalidate it in `_write()`. Eliminates the repeat 600 KB parses.

- `tutor/tutor_store.py`
  - Store `_cached_entries: list[TutorEntry] | None`, `_cached_key:
    tuple[float, int] | None`.
  - `load()`: `os.stat` the file, reuse cache if key matches, else
    parse and cache.
  - `_write()`: clear cache; next `load()` re-stats and re-caches.

#### 1b. Pass `anchor_raw` through from `LineBlock` to skip one reparse

`_open_new_thread` currently scans `tutor_store.load()` just to grab
`entry.raw` for the placeholder. `LineBlock` already holds it (`_raw`).

- `tutor/gui.py`
  - `LineBlock`: add a public `raw` property mirroring `tutor_id`.
  - `on_button_pressed` for `ask-*`: resolve the `LineBlock` via
    `event.button.parent` and pass its `raw` into `_open_new_thread`.
  - `_open_new_thread`: accept and use `anchor_raw`; drop the
    `tutor_store.load()` scan.

#### 1c. Batch mounts

Replace per-item `mount()` loops with one `mount_all([...])` call. One
layout pass instead of N.

- `tutor/gui.py`
  - `_restore_tutor_entries` (~357-370)
  - `_reopen_thread` (~641-645)
  - `_refresh_thread_list` (~696-698)

#### 1d. Cache hot DOM nodes on the app

Resolve `#stream-pane`, `#thread-pane`, `#thread-list-container`,
`#thread-messages`, `#thread-input`, `#status-bar` once in `on_mount`
and store them as instance attributes. Handlers then use
`self._stream_pane` instead of `self.query_one('#stream-pane', ...)`,
avoiding DOM walks on every click.

- `tutor/gui.py`: add attrs in `__init__`, populate in `on_mount`,
  replace `query_one` call sites across the file (there are ~15).

### Tier 2 — reduce widget count (do if tier 1 isn't enough)

Collapse `LineBlock` from 4 widgets (Horizontal + Label + 2 Buttons) to
**1 widget** using Rich/Textual's clickable-markup actions. Each entry
becomes a single `Static` whose content is something like:

```
<raw line text>    [@click=ask('<id>')][ ASK ][/]  [@click=del('<id>')][ DEL ][/]
```

Textual dispatches the click to `action_ask(id)` / `action_del(id)` on
the widget or app. This drops left-pane widget count from ~3,760 to
~1,500 (one `Static` per LineBlock + one per ExplanationBlock = 2 per
entry). If we also inline the explanation text into the same `Static`
(one widget per entry), total drops to ~750 — a **~5× reduction**.

Tradeoffs:
- CSS styling for the "DEL armed" visual (currently a class swap on the
  Button) must move to a markup-level style change (re-rendering the
  Static with different markup for the armed state). Cheap.
- Button hover / focus styling no longer applies; we'd style the
  clickable regions via theme tags. Acceptable for this UI.
- `ThreadListItem` has the same 3-widget structure and can use the
  same treatment (lower priority — only 15 rows, not 752).

Keep this change behind tier 1 because it is the larger refactor; only
do it if tier 1 doesn't restore snappy input.

### Explicitly NOT doing

- **Streaming render is left as-is.** Per user direction. Per-chunk
  Rich-Markdown re-render stays.
- **No mtime cache on `ThreadStore.list_threads`** yet — only 15 files,
  not the bottleneck.
- **No background-thread disk I/O plumbing** — tier 1 caching removes
  the repeated reads; the first read is fine on the loop.

## Files to modify

- `tutor/tutor_store.py` — mtime/size cache in `load`, invalidate in
  `_write`.
- `tutor/gui.py`
  - `LineBlock`: expose `raw` property.
  - `on_button_pressed` (`ask-*` branch): pull `raw` from the
    `LineBlock`, pass into `_open_new_thread`.
  - `_open_new_thread`: accept `anchor_raw`, drop `tutor_store.load()`.
  - `_restore_tutor_entries`, `_reopen_thread`,
    `_refresh_thread_list`: use `mount_all`.
  - `__init__` / `on_mount`: cache hot widget references; replace
    `query_one` hits with cached attrs across the file.
- (tier 2 only) `LineBlock`, `ExplanationBlock`, `ThreadListItem`:
  rewrite to use Rich clickable markup instead of nested
  `Horizontal`+`Button`s.

## Reused existing pieces

- `Widget.mount_all` (Textual 8.2.3 — no new dependency).
- `LineBlock._raw` already exists; just needs a getter.
- `TutorStore._write` is the single mutation point; clean cache
  invalidation surface.
- (tier 2) Textual's `@click=` action markup (built into Rich/Textual,
  used for any interactive inline link).

## Verification

1. **Manual smoke, live workload**: with the user's existing `state/`
   directory (752 tutor entries, 15 threads), launch the TUI and:
   - Click DEL on an entry in the left pane → label flips to `CFM?`
     with no perceptible delay.
   - Click ASK on an entry → right pane switches to conversation view
     instantly.
   - Click OPEN on a saved thread → messages appear instantly.
   - Scroll the left pane while idle; mouse-wheel should feel fluid.
2. **Fresh start**: restart the TUI and confirm no regressions in the
   initial left-pane restore (all 752 entries still visible, in order).
3. **Streaming still works**: send a thread message; confirm streamed
   output still renders with markdown on completion.
4. **Lint/type**: `uv run --frozen ruff check` and `uv run --frozen
   basedpyright`.
5. **Targeted tests**: if there are tests for `TutorStore` (round-trip
   append/load/delete), run them to confirm the cache doesn't break
   invalidation. If there aren't, add one small test: append an entry,
   mutate the file on disk externally, confirm next `load()` picks up
   the external change (stat-based invalidation).

If tier 1 alone is not enough, tier 2 will be the decisive fix since it
directly targets the 3,760-widget count that is the most likely cause
of idle lag.
