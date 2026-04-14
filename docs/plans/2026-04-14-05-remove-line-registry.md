# Remove LineRegistry

## Context

`LineRegistry` (`tutor/registry.py`) is an in-memory deque of every stdin line plus an optional explanation. It predates `TutorStore`, which now persists every explained line to disk as the single source of truth. Investigation shows LineRegistry has exactly **one real consumer** (`FollowupThreadPool.open_thread` calling `recent(100)` for thread context) and one incidental use (`line_idx` as a widget dict key). `TutorStore` can supply the context directly, so LineRegistry is dead weight — it duplicates state, adds a constructor parameter to `FollowupThreadPool` and `TutorTUI`, and requires a manual replay step on GUI resume (`gui.py:342-344`).

**Behavior change the user approved:** thread context will be drawn from `TutorStore`, which contains only lines that produced a response. Filtered/blank/duplicate stdin lines (previously included by `recent(100)`) will no longer appear in the "Recent dialog" block of `build_thread_system_prompt`. Skip-token lines remain (they already land in TutorStore with "SKIP" as explanation).

## Approach

### 1. Source thread context from TutorStore

`tutor/thread_pool.py:83-97` already loads `entries = self._tutor_store.load()`. Reuse the slice directly:

```python
context_entries = entries[max(0, anchor_idx - 100):anchor_idx]
context_lines = [
    LineRecord(idx=-1, raw=e.raw, explanation=e.explanation)
    for e in context_entries
]
```

This also fixes a subtle issue: today's `recent(100)` returns the *globally* most-recent lines, which can include lines added *after* the anchor if the user delays opening a thread. Slicing up to `anchor_idx` scopes context to what preceded the anchor — a small improvement.

`build_thread_system_prompt` keeps its existing signature (takes `list[LineRecord]`), so prompt-rendering code is untouched.

### 2. Replace `line_idx` with `tutor_pos`

`line_idx` flows: `registry.add_line()` → `sink.on_explanation(line_idx, …)` → `gui.on_explanation` stores `_line_widgets[line_idx] = block` and builds button id `ask-{line_idx}`. On click, the handler at `gui.py:416-421` extracts the id, looks up the block, and uses `block.tutor_pos` as the anchor — so `line_idx` is only an opaque widget key.

Simplification: drop `line_idx` from the `OutputSink.on_explanation` signature entirely and key the button id by `tutor_pos` instead. `tutor_pos` is already monotonic and unique per TutorStore entry, and it's what the click handler ultimately needs. Since the handler can parse `tutor_pos` directly from the button id, `_line_widgets` can be deleted outright — nothing else uses it.

Files affected:
- `tutor/types.py` — update `OutputSink.on_explanation` protocol signature.
- `tutor/sink.py` — `TerminalSink.on_explanation` drops the `line_idx` arg.
- `tutor/core.py:111, 142, 145-146` — remove `line_idx = registry.add_line(...)`, remove `registry.set_explanation(...)`, drop the arg from the two `sink.on_explanation` calls.
- `tutor/gui.py:293, 345-348, 360-371, 415-421` — `LineBlock` takes only `(raw, tutor_pos)`; button id becomes `ask-{tutor_pos}`; `on_button_pressed` parses `tutor_pos` directly and passes it to `_open_new_thread`; `_line_widgets` deleted.

### 3. Delete LineRegistry and its wiring

- Delete `tutor/registry.py`.
- `tutor/core.py` — remove `from tutor.registry import LineRegistry`, drop the `registry` parameter from `_stdin_loop`, drop `registry = LineRegistry()` and the arg passed into `_stdin_loop` in `run_terminal` (lines 217, 220).
- `tutor/gui.py` — remove `LineRegistry` import, the `line_registry` constructor parameter, `self._line_registry`, and the `add_line`/`set_explanation` calls in `_restore_tutor_entries` (lines 342-344). The method can just iterate entries and mount widgets directly.
- `tutor/gui.py:584, 594, 604` — the `run_gui` entry point drops `line_registry=…` and no longer constructs a `LineRegistry`.
- `tutor/thread_pool.py` — remove the `registry` parameter, `self._registry`, the `LineRegistry` TYPE_CHECKING import. Update the `FollowupThreadPool(...)` callsite in `gui.py` to stop passing `registry=`.

### 4. Critical files

- `tutor/registry.py` — delete
- `tutor/thread_pool.py` — update `__init__` and `open_thread`
- `tutor/core.py` — update `_stdin_loop`, `run_terminal`
- `tutor/gui.py` — update `TutorTUI.__init__`, `_restore_tutor_entries`, `on_explanation`, `on_button_pressed`, `LineBlock`, and the `run_gui`/instantiation block
- `tutor/sink.py` — update `TerminalSink.on_explanation`
- `tutor/types.py` — update `OutputSink` protocol

## Verification

1. `uv run --frozen ruff check` and `uv run --frozen pyright` pass.
2. **Terminal mode:** pipe a sample transcript with a mix of filtered/blank/duplicate/normal/skip-token lines into `uv run --frozen oh-language-tutor …`. Confirm explanations print and `state/tutor.json` is written correctly.
3. **GUI mode:** launch with `--gui`, feed lines, click "Ask" on a mid-stream line, confirm the followup thread opens with a sensible "Recent dialog" context block. Verify:
   - Filtered/blank/duplicate lines are absent from the context block (expected behavior change).
   - The anchor line itself is excluded from the context slice (the `entries[:anchor_idx]` upper bound).
   - Clicking "Ask" on different lines produces distinct anchors.
4. **Resume:** exit, relaunch with `--gui`, verify left pane rehydrates from `tutor.json` and clicking "Ask" on a restored entry still works (proves the `tutor_pos`-keyed path survives a reload without the registry replay).
5. **Delete / hide thread** still function (no signature change expected, but confirm callsites line up).
