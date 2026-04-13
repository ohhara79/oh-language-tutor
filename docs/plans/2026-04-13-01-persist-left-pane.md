# Plan: Persist left pane state to `state/tutor.json`

## Context

Currently, `state/threads/*.json` restores the right pane (thread conversations) on restart, but the left pane (stream of raw lines + explanations) starts empty. The user wants a `state/tutor.json` file so the left pane content is restored on restart, while keeping `tutor.log` as-is.

The left pane only displays lines that have explanations (via `on_explanation` in `gui.py:252-264`), so `tutor.json` only needs to store those entries.

Entries accumulate across sessions (never reset automatically).

## Approach

### 1. Define `TutorEntry` dataclass in `tutor/types.py`

```python
@dataclass(slots=True)
class TutorEntry:
    """One explained line persisted for left-pane restoration."""
    line_idx: int
    raw: str
    explanation: str
```

### 2. Create `tutor/tutor_store.py` — single-file JSON persistence

Follow the same atomic-write pattern as `ThreadStore`:

- `TutorStore.__init__(path: Path)` — path to `state/tutor.json`
- `TutorStore.load() -> list[TutorEntry]` — read and deserialize, return `[]` on missing/corrupt
- `TutorStore.append(entry: TutorEntry)` — load current list, append, write back atomically
- Atomic write via `tempfile` + `rename` (same pattern as `thread_store.py:48-57`)

JSON format:
```json
[
  {"line_idx": 0, "raw": "INTRO_E: ...", "explanation": "🎯 Translation: ..."},
  ...
]
```

### 3. Wire `TutorStore` into the GUI launch path (`gui.py:launch()`)

- Create `TutorStore` instance pointing to `state/tutor.json` (same parent as `log_path`)
- Pass it to `OhLanguageTutorApp` constructor (new `tutor_store` parameter)

### 4. Save entries on each explanation (`gui.py:on_explanation`)

After the existing log writes and widget mounts, call `self._tutor_store.append(TutorEntry(...))`.

### 5. Restore left pane on startup (`gui.py:on_mount`)

- Call `self._tutor_store.load()` to get saved entries
- For each entry, mount `LineBlock` + `ExplanationBlock` (same as `on_explanation` does)
- Remove the "Waiting for input..." placeholder if entries exist
- Populate `self._line_widgets` so [Ask] buttons work on restored lines
- Register restored lines in `self._line_registry` with their explanations so thread context works

## Files to modify

| File | Change |
|------|--------|
| `tutor/types.py` | Add `TutorEntry` dataclass |
| `tutor/tutor_store.py` | **New file** — `TutorStore` class |
| `tutor/gui.py` | Accept `TutorStore`, save on explanation, restore on mount |

## Verification

1. Run the app with `--gui`, let a few explanations appear in the left pane
2. Quit and check that `state/tutor.json` exists with the entries
3. Restart the app — left pane should show the previously saved entries
4. New explanations should append to the existing entries
5. [Ask] buttons on restored entries should still open threads correctly
