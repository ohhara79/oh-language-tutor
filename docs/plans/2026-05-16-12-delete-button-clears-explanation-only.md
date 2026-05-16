# Delete button clears explanation only (not the sentence)

## Context

In the web UI's left-pane "sentence view" (`tutor/templates/partials/line.html`),
the Delete button on an *explained* line currently removes the entire entry —
both the raw stdin line and its explanation — via
`POST /commands/delete_tutor_entry`. The user wants Delete on an explained line
to drop only the explanation (and its anchored Ask threads), leaving the
sentence so it can be re-explained from scratch.

Two related decisions captured from the user:

- Cascade-delete anchored Ask threads when clearing the explanation (same
  blast radius as today's full-entry delete; just keeps the raw line).
- The second Delete button shown on an *unexplained* line (Explain + audience
  inputs visible) should be removed entirely — no use case left.

After clearing, the line reverts to its unexplained variant (audience inputs
+ Explain button), exactly as `on_explain_aborted` already renders it after a
failed explain.

## Approach

Add a new "clear explanation" path that mirrors the existing
`delete_tutor_entry` cascade but, in place of deleting the entry, resets
`explanation` / `source_language` / `target_language` / `level` back to
`None`. Then re-broadcast the unexplained variant of the line so all
connected tabs swap their explained block out.

### Files to modify

1. **`tutor/tutor_store.py`** — add an async store method that clears the
   explanation and audience fields on a single entry. Mirrors
   `delete_async` / `update_explanation_async`:

   ```python
   async def clear_explanation_async(self, entry_id: str) -> bool:
       """Reset explanation + audience on *entry_id* back to None.

       Returns False if not found. The raw line is preserved so the user
       can re-Explain it.
       """
       async with self._get_write_lock():
           entries = self.load()
           for e in entries:
               if e.id == entry_id:
                   e.explanation = None
                   e.source_language = None
                   e.target_language = None
                   e.level = None
                   await asyncio.to_thread(self._write, entries)
                   return True
           return False
   ```

2. **`tutor/thread_pool.py`** — add `clear_tutor_entry_explanation`, modeled
   on `delete_tutor_entry` (lines 211–221). Same cascade for active +
   on-disk threads; in place of `tutor_store.delete_async` it calls the new
   `clear_explanation_async`; in place of `on_tutor_entry_removed` it asks
   the sink to broadcast the unexplained re-render:

   ```python
   async def clear_tutor_entry_explanation(self, anchor_id: str) -> None:
       """Drop the explanation on a tutor entry; cascade-delete its threads."""
       if not anchor_id:
           return
       active_to_close = [tid for tid, at in self._active.items()
                          if at.meta.anchor_id == anchor_id]
       for tid in active_to_close:
           await self.hide_thread(tid)
       self._store.delete_by_anchor_id(anchor_id)
       cleared = await self._tutor_store.clear_explanation_async(anchor_id)
       self._sink.on_thread_list(self.list_threads())
       if cleared:
           entry = next((e for e in self._tutor_store.load()
                         if e.id == anchor_id), None)
           if entry is not None:
               self._sink.on_entry_explanation_cleared(entry)
   ```

3. **`tutor/web_sink.py`** — add `on_entry_explanation_cleared(entry)`. Body
   is identical in shape to `on_explain_aborted` (lines 128–136): render the
   unexplained variant and OOB-replace `#line-{id}`. Use a distinct SSE
   event name so log readers can tell the two flows apart:

   ```python
   def on_entry_explanation_cleared(self, entry: TutorEntry) -> None:
       fragment = self.render_line(entry)
       oob_fragment = fragment.replace(
           f'id="line-{entry.id}"',
           f'id="line-{entry.id}" hx-swap-oob="outerHTML"',
           1,
       )
       self._broadcast('entry_explanation_cleared', oob_fragment)
   ```

4. **`tutor/web.py`** — add a new endpoint next to `delete_tutor_entry`
   (lines 317–322):

   ```python
   @app.post('/commands/clear_explanation')
   async def clear_explanation(  # pyright: ignore[reportUnusedFunction]
       anchor_id: Annotated[str, Form()],
   ) -> Response:
       await ctx.pool.clear_tutor_entry_explanation(anchor_id)
       return Response(status_code=204)
   ```

5. **`tutor/templates/partials/line.html`**
   - **Explained branch (lines 19–28)**: repoint the Delete form to
     `/commands/clear_explanation`, update the confirm prompt to
     `"Delete this explanation and its threads?"`. Keep the button label
     "Delete" — the action from the user's perspective is still "delete what's
     on screen."
   - **Unexplained branch (lines 67–76)**: remove the Delete form entirely.
     Leaves Explain as the sole action in the unexplained `<div class="line-actions">`.

6. **`tutor/templates/index.html`** (line 49) — extend the SSE event
   subscription list to include `entry_explanation_cleared`:

   ```
   sse-swap="thread_chunk,thread_done,tutor_entry_removed,entry_explained,
             explain_chunk,explain_aborted,entry_explanation_cleared,error"
   ```

### What stays unchanged

- `delete_tutor_entry` endpoint and `FollowupThreadPool.delete_tutor_entry`
  remain — nothing in this plan removes the full-entry-delete capability at
  the API level. (The UI just no longer exposes it.)
- `TutorEntry` shape, `tutor.json` schema, and `ThreadStore` cascade
  semantics are unchanged.
- `render_line` already handles all three variants (explained, streaming,
  unexplained); no template restructuring needed beyond the two button
  edits above.

## Verification

1. `make lint` — type-check + format pass (mandatory per `CLAUDE.md`).
2. Manual UI run:
   - Start the web UI per `README.md`. Pipe a few lines into stdin.
   - On an unexplained line, confirm only the Explain button shows (no
     Delete) and the audience inputs render as before.
   - Click Explain on a line; once the explanation finishes streaming, open
     an Ask thread (or two) on it via the Ask button.
   - Click Delete on the explained line, accept the new confirm prompt.
     Expected: the line snaps back to its unexplained variant (audience
     inputs + Explain), the Ask threads disappear from the thread list,
     and the raw line text is still there.
   - Open a second browser tab against the same server; repeat the Delete
     and confirm the OOB swap fires in the other tab too (SSE broadcast).
   - Reload the page — the line should still render as unexplained
     (persisted clear, not just an in-memory swap).
3. Spot-check `state/tutor.json` for the affected entry: `explanation`,
   `source_language`, `target_language`, `level` should all be `null`;
   `raw` and `id` preserved.
4. Spot-check `state/threads/` — the anchored thread files should be gone.
