# Scroll left pane to anchor on thread open/reopen

## Context

When the user reopens a saved thread from the right pane, the left pane stays where it was — often nowhere near the line the thread is anchored to. The user has to scroll manually to see the source context for the conversation.

`ThreadMeta.anchor_idx` (`tutor/types.py:53`) already stores the tutor.json array position of each thread's anchor line, and every `LineBlock` widget in the left pane carries that same position as `tutor_pos` (`tutor/gui.py:143-150`). Matching them up and scrolling is straightforward.

**Feasibility:** Yes. The left pane (`#stream-pane`) is a `ScrollableContainer` (`tutor/gui.py:301`), which inherits `scroll_to_widget()` from Textual's `Widget`. The existing `scroll_end()` calls in the same file confirm programmatic scrolling works on this widget.

## Approach

Add a small helper that finds the `LineBlock` whose `tutor_pos` matches a given `anchor_idx` and scrolls the left pane to it. Call the helper from both thread-entry paths in `tutor/gui.py`:

- `_open_new_thread()` (line 429) — uses the `anchor_idx` parameter directly.
- `_reopen_thread()` (line 452) — reads `meta.anchor_idx` from the loaded `ThreadMeta`.

Use `scroll_to_widget(target, animate=False)` with default `top=False` so the pane only scrolls when the line is not already visible (avoids jarring movement when the user clicks Ask on a visible line in `_open_new_thread`).

Legacy threads saved before commit `2581f0c` have `anchor_idx == -1`. In that case, skip scrolling silently — `anchor_raw` text-matching is fragile (duplicate lines) and not worth the complexity.

## Changes

**File:** `tutor/gui.py`

1. Add helper method on the app class (near the other thread-management helpers around line 427):

   ```python
   def _scroll_left_pane_to_anchor(self, anchor_idx: int) -> None:
       if anchor_idx < 0:
           return
       stream = self.query_one('#stream-pane', ScrollableContainer)
       for block in stream.query(LineBlock):
           if block.tutor_pos == anchor_idx:
               stream.scroll_to_widget(block, animate=False)
               return
   ```

2. Call it at the end of `_open_new_thread()` (after line 450, after `inp.focus()`):

   ```python
   self._scroll_left_pane_to_anchor(anchor_idx)
   ```

3. Call it at the end of `_reopen_thread()` (after line 483, after `inp.focus()`):

   ```python
   self._scroll_left_pane_to_anchor(meta.anchor_idx)
   ```

No changes needed in `types.py`, `thread_pool.py`, or anywhere else — `anchor_idx` is already plumbed through.

## Critical files

- `tutor/gui.py` — lines 301 (stream-pane), 140-161 (LineBlock with `tutor_pos`), 429-450 (`_open_new_thread`), 452-483 (`_reopen_thread`)
- `tutor/types.py:53` — `ThreadMeta.anchor_idx` source

## Verification

1. Run the app and feed enough input to produce many lines so the left pane scrolls below the fold.
2. Click Ask on an early (off-screen-above) line, then click Ask on a late line. The left pane should reveal the clicked line each time (or stay put if already in view).
3. Reopen a saved thread whose anchor line is currently off-screen. Left pane should scroll so the anchor line is visible.
4. Reopen a legacy thread with `anchor_idx == -1` (if any exist) — left pane should not scroll and no error should be raised.
5. Type-check: `uv run --frozen basedpyright tutor/gui.py`.
