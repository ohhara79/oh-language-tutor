# Async store writes + plain-text streaming render

## Context

Two remaining responsiveness levers from the TUI assessment:

- **#3 — Write amplification on the UI loop.** Every new explanation
  (`on_explanation`) and every thread message (user or assistant)
  triggers a **full-file JSON rewrite** on the asyncio event loop.
  `tutor.json` is ~600 KB; rewriting it on every explained line stalls
  the UI.
- **#4 — O(N²) streaming re-render.** Every chunk of a streaming
  thread reply calls `_rich_md(self._streaming_text)` on the *entire*
  accumulated text, so render cost grows quadratically with reply
  length. The previous direction to keep per-chunk markdown rendering
  is reversed.

Goal: UI stays snappy while new explanations arrive at idle, and long
thread replies render without compounding latency.

## Current state (reference)

- `TutorStore._write` (`tutor/tutor_store.py:73-93`) — atomic
  tmpfile-then-rename; rebuilds the full JSON body; runs on the caller
  thread.
- `TutorStore.append` / `TutorStore.delete` (`tutor/tutor_store.py:51,
  57`) — sync, call `_write` on the event loop.
- `ThreadStore.save_thread` / `_write` (`tutor/thread_store.py:38,
  72`) — same pattern, per-thread file (smaller, but one rewrite per
  chunked assistant reply and per user message).
- Callers on the event loop:
  - `gui.py:427` — `on_explanation` → `tutor_store.append(entry)`
    (called from the `_stdin_loop` coroutine).
  - `thread_pool.py:193` — `delete_tutor_entry` → `tutor_store.delete`.
  - `thread_pool.py:298, 321` — `save_thread` after user message and
    after assistant reply completes.
- `gui.py:442-451` — `_apply_thread_chunk`: accumulates text and calls
  `self._streaming_label.update(_rich_md(self._streaming_text))` on
  every chunk.
- `gui.py:456-462` — `_apply_thread_done`: already calls
  `_rich_md(self._streaming_text)` once at completion. This is the
  anchor that makes #4 safe: a final markdown render is guaranteed.

## Changes

### Part A — Offload writes (#3)

Goal: all full-file JSON writes run on a worker thread; callers
serialize via per-store `asyncio.Lock` so concurrent appends stay
consistent.

**`tutor/tutor_store.py`**

- Add lazy `asyncio.Lock` accessor (`_get_write_lock`) — constructed on
  first use so the store can still be built outside any event loop
  (unit tests, terminal mode).
- Keep existing sync `append` / `delete` / `_write` untouched for
  non-async callers.
- Add:

  ```python
  async def append_async(self, entry: TutorEntry) -> None:
      async with self._get_write_lock():
          entries = self.load()
          entries.append(entry)
          await asyncio.to_thread(self._write, entries)

  async def delete_async(self, anchor_id: str) -> bool:
      async with self._get_write_lock():
          entries = self.load()
          kept = [e for e in entries if e.id != anchor_id]
          if len(kept) == len(entries):
              return False
          await asyncio.to_thread(self._write, kept)
          return True
  ```

- `_write` already updates the in-memory cache at its tail; running it
  under `to_thread` is fine (GIL; only one writer holds the lock).

**`tutor/thread_store.py`**

- Add the same lazy lock accessor and:

  ```python
  async def save_thread_async(self, meta: ThreadMeta) -> None:
      async with self._get_write_lock():
          await asyncio.to_thread(self.save_thread, meta)
  ```

**`tutor/gui.py` — `on_explanation` callsite (line 420-428)**

- Introduce `self._pending_writes: set[asyncio.Task[None]] = set()` in
  `__init__`.
- Replace the sync `self._tutor_store.append(entry)` call with a
  fire-and-forget async task:

  ```python
  if self._tutor_store is not None:
      task = asyncio.create_task(self._tutor_store.append_async(entry))
      self._pending_writes.add(task)
      task.add_done_callback(self._pending_writes.discard)
  ```

- On shutdown, drain pending writes via `on_unmount`:

  ```python
  async def on_unmount(self) -> None:
      if self._pending_writes:
          await asyncio.gather(*self._pending_writes, return_exceptions=True)
  ```

**`tutor/thread_pool.py`**

- `delete_tutor_entry` (line 193): change to
  `await self._tutor_store.delete_async(anchor_id)`.
- `_run_send_message` (lines 298 and 321): change both to
  `await self._store.save_thread_async(at.meta)`.

### Part B — Remove per-chunk markdown re-parse (#4)

Goal: chunked updates do zero markdown work; markdown is applied once
at `on_thread_done`.

**`tutor/gui.py:442-451` — `_apply_thread_chunk`**

- Replace `self._streaming_label.update(_rich_md(self._streaming_text))`
  with `self._streaming_label.update(self._streaming_text)`.
- Keep `_streaming_text += chunk` — `_apply_thread_done` still needs
  it for the final markdown render (already wired at line 460).
- Keep the `container.scroll_end(animate=False)` call.

During streaming the user briefly sees raw markers (`**bold**`, list
dashes); the moment the response completes `_apply_thread_done`
replaces the `Static`'s content with `_rich_md(...)` and the final
rendered markdown appears.

### Not doing

- No change to `_apply_thread_done`'s final render — already correct.
- No coalescing of pending writes (multiple appends during a burst
  each do one write).
- No migration of terminal-mode sink's calls — `TerminalSink` is not
  on a Textual event loop, so the sync API stays correct there.

## Files to modify

- `tutor/tutor_store.py` — add lazy lock + `append_async` /
  `delete_async`.
- `tutor/thread_store.py` — add lazy lock + `save_thread_async`.
- `tutor/gui.py` —
  - `OhLanguageTutorApp.__init__`: `self._pending_writes`.
  - `on_explanation` (line 420): async task-based append.
  - `on_unmount`: drain pending writes.
  - `_apply_thread_chunk` (line 442): plain-text update, no markdown.
- `tutor/thread_pool.py` —
  - `delete_tutor_entry` (line 193): `await delete_async`.
  - `_run_send_message` (lines 298, 321): `await save_thread_async`.

## Reused existing pieces

- `asyncio.to_thread` (stdlib).
- Existing atomic tmpfile-rename write path in both stores.
- Existing `(mtime, size)` cache in `TutorStore` — still correctly
  invalidated because `_write` updates it at the tail.
- `_apply_thread_done` (`gui.py:456-462`) — already renders final
  markdown; anchors the streaming simplification.

## Verification

1. `uv run --frozen basedpyright` and `uv run --frozen ruff check`
   stay clean.
2. `uv run --frozen pytest -q` — existing suite passes.
3. **Idle-stream smoke:** launch the TUI against the user's live
   `state/` (752 entries). Pipe new lines through; DEL / ASK / OPEN
   remain immediate during steady explanation flow.
4. **Streaming smoke:** open a thread, send a prompt that produces a
   multi-kilobyte reply.
   - During streaming: raw text scrolls fluidly, literal markers
     visible.
   - On completion: block re-renders as formatted markdown.
5. **Shutdown durability:** trigger an explanation, immediately quit.
   Relaunch and confirm the entry is on disk (on_unmount flushed).
6. **Crash-consistency:** `kill -9` mid-write; relaunch and confirm
   `tutor.json` is either pre- or post-write state.
