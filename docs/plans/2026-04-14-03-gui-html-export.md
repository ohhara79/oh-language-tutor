# Add HTML export (Ctrl+E) to the GUI

## Context

The user wants to browse their oh-language-tutor session in an external web browser
(for reading on another device, sharing, printing, archival). The state directory
already holds everything needed: `tutor.json` (explained lines) and `threads/*.json`
(followup conversations). Today there is no way to view these outside the TUI.

This plan adds a Ctrl+E keybinding that exports the current session's state to a
single self-contained `tutor.html` inside the state directory. No external assets —
all CSS is inlined so the file works offline, on any device, with a double-click.

### Design decisions (agreed with user)

- **Layout:** single scrolling document — explained lines flow vertically.
  Best for browser Ctrl+F search, mobile reading, and print/save-as-PDF.
- **Thread placement:** each line that has a followup thread gets an inline
  `<details>` block directly below its explanation, **collapsed by default**.
  Click to expand in place. No jumping, no duplication.
- **Explanation collapse:** each line's explanation is also wrapped in a
  `<details>` block, **collapsed by default**, with the raw line text serving
  as the `<summary>`. Click the raw line to reveal its explanation.
- **Shortcut:** `Ctrl+E` bound at App level. Collision with Textual Input's
  built-in "move cursor to end" is accepted — export works everywhere except
  while typing in the thread input, which is the expected natural behavior.

## Approach

Add a new module `tutor/html_export.py` that reads state files via the existing
`TutorStore` and `ThreadStore`, then renders a single HTML string. The GUI gets a
new `action_export_html` method wired to `Ctrl+E` that calls the exporter and shows
a success/error message in the existing status bar.

The export runs **synchronously in the action handler** (not through the async
command queue). Reasons: no Claude API calls are involved, the work is just a few
JSON reads + string building, and the stores already tolerate corrupt files. This
keeps the feature simple and fast.

### Matching threads to lines

`TutorEntry.raw` (line text) is the only stable identifier. `ThreadMeta.anchor_raw`
records the raw of the line a thread was anchored to. The exporter groups threads
by `anchor_raw` and attaches them to the matching line entry. If the same raw
appears on multiple lines (rare but possible), the thread attaches to **all**
matching entries — consistent, safe, no data loss.

### Markdown rendering

Reuse the existing CJK-aware emphasis preprocessor `_emphasis_to_html` from
`tutor/gui.py:79-82` to handle `**bold**` in Korean/CJK text (the fix from
commit 57fc391). Feed the preprocessed text to `markdown.markdown()` from the
already-installed `markdown==3.10.2` dep. Extract the helper into a shared module
so it is callable from both the TUI and the exporter.

### HTML structure (minimal, self-contained)

```html
<!doctype html>
<html><head>
  <meta charset="utf-8">
  <title>oh-language-tutor export</title>
  <style>/* inlined CSS */</style>
</head><body>
  <header><h1>oh-language-tutor</h1><p class="meta">Exported 2026-04-14 ...</p></header>
  <main>
    <section class="line">
      <details class="explain">
        <summary class="raw">&gt; BRLOGO_E: "Blade Runner™"</summary>
        <div class="explanation-body"><!-- rendered markdown --></div>
      </details>
      <details class="thread">
        <summary>Thread (3 msgs, 2026-04-13)</summary>
        <div class="msg user">You: ...</div>
        <div class="msg assistant"><!-- rendered markdown --></div>
        ...
      </details>
    </section>
    ...
  </main>
</body></html>
```

CSS: readable max-width (~800px), monospace for `.raw`, serif or system-ui for
body, subtle dividers between lines, distinct background shade for `<details>`.
All user-supplied text passes through `html.escape` before being inserted
anywhere that isn't the markdown-rendered explanation/message body (which is
already HTML from the markdown library).

Include entries with `explanation == "SKIP"` as-is. The TUI also renders SKIP
entries (see `tutor/core.py:141-143` — SKIP responses still call
`sink.on_explanation`, which mounts an `ExplanationBlock` and appends to
`tutor.json`). The export should match the TUI for fidelity.

## Changes

### New: `tutor/html_export.py`

Single public entry point:

```python
def export_to_html(
    tutor_store: TutorStore,
    thread_store: ThreadStore,
    out_path: Path,
) -> None
```

Responsibilities:
- Load entries via `tutor_store.load()` and threads via `thread_store.list_threads()`.
- Render every entry (including `"SKIP"`) to match TUI fidelity.
- Group threads by `anchor_raw` into `dict[str, list[ThreadMeta]]`.
- Render markdown using `_emphasis_to_html` + `markdown.markdown`.
- Build HTML string; write atomically via tempfile + rename (mirror the pattern
  in `tutor/tutor_store.py:38-47` and `tutor/thread_store.py:48-57`).

### Modify: `tutor/gui.py`

1. Add import: `from tutor.html_export import export_to_html`.
2. Add constructor arg `thread_store: ThreadStore | None` (so the exporter can
   read thread files directly rather than reaching through `self._pool`).
   Store as `self._thread_store`.
3. Add binding at line 271-274:
   ```python
   ('ctrl+e', 'export_html', 'Export HTML'),
   ```
4. Add action method:
   ```python
   def action_export_html(self) -> None:
       if self._tutor_store is None or self._thread_store is None:
           return
       out = self._state_dir / 'tutor.html'
       try:
           export_to_html(self._tutor_store, self._thread_store, out)
       except OSError as exc:
           self.query_one('#status-bar', Label).update(f'Export failed: {exc}')
           return
       self.query_one('#status-bar', Label).update(f'Exported to {out}')
   ```
   Thread a `state_dir: Path` through `__init__` rather than reaching into the
   private `_path` on `TutorStore`.
5. In `OhLanguageTutorApp.launch` (line 567-569), pass the already-constructed
   `ThreadStore` instance (line 563) and `state_dir` to the app.

### Refactor: extract CJK emphasis helper

The `_emphasis_to_html` function and `_RE_STRONG`/`_RE_EMPH` regexes in
`tutor/gui.py:75-82` are needed by both the TUI (already) and the exporter (new).
Move them to a small new module `tutor/markdown_util.py` and import from both
`gui.py` and `html_export.py`. Keeps the GUI module focused on TUI concerns and
avoids GUI-framework imports leaking into the exporter.

## Critical files

- `tutor/gui.py:271-274` — add Ctrl+E binding
- `tutor/gui.py:279-296` — constructor, add `thread_store` + `state_dir` params
- `tutor/gui.py:567-569` — pass `store` (ThreadStore) and state_dir into app
- `tutor/gui.py:75-82` — extract `_emphasis_to_html` / regex helpers
- `tutor/tutor_store.py:19-27` — `TutorStore.load()` (reused, no changes)
- `tutor/thread_store.py:22-31` — `ThreadStore.list_threads()` (reused, no changes)
- `tutor/types.py:24-54` — `TutorEntry`, `ThreadMeta`, `ThreadMessage` (data model, no changes)
- `tutor/html_export.py` — NEW, exporter module
- `tutor/markdown_util.py` — NEW, shared emphasis preprocessor

## Verification

1. **Lint & typecheck:** `uv run --frozen ruff check`, `uv run --frozen ruff format --check`, `uv run --frozen basedpyright`.
2. **Run the TUI** via `scripts/bladerunner.sh` (or the usual launcher) against a
   state dir that already has `tutor.json` + several threads.
3. **Press Ctrl+E** from the main list view (thread input not focused).
   - Expected: status bar shows `Exported to <state>/tutor.html`.
   - Expected: `tutor.html` appears in the state dir.
4. **Open `tutor.html` in Firefox/Chrome.** Check:
   - Every explained line from the TUI appears in the same order.
   - Each line is a collapsed `▶ <raw text>` row; clicking it expands the
     explanation in place.
   - Markdown formatting is rendered (bold, italics, code blocks, lists).
   - CJK `**볼드**` renders as bold (the commit 57fc391 regression test).
   - Lines with threads have an additional collapsed `▶ Thread (N msgs,
     YYYY-MM-DD)` toggle nested directly below the explanation.
   - Clicking the thread toggle expands the full conversation inline.
   - User messages visually distinct from assistant messages.
   - Ctrl+F in the browser finds text in expanded AND collapsed details (modern
     browsers auto-expand `<details>` on find).
5. **Edge cases:**
   - Empty state dir (no `tutor.json`, no threads): export should produce a valid
     HTML page with "no content" placeholder rather than crash.
   - A thread whose `anchor_raw` doesn't match any line entry (thread orphaned
     because the line is not in `tutor.json`): render it at the bottom under a
     "Orphan threads" section, don't drop it. Keep this small — one `<details>`
     each.
   - SKIP explanations: rendered the same way the TUI renders them (just the
     literal text "SKIP" in the explanation block). No filtering.
   - Re-export overwrites existing `tutor.html` atomically (tempfile + rename).
6. **Press Ctrl+E while typing in the thread input:** confirm the keystroke moves
   the cursor and does **not** trigger export (documented behavior).
7. **Run at least once against a real session** (the `state/` directory under the
   repo appears to contain real data — do not modify it, just read).
