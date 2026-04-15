# Match right pane Del button color to left pane

## Context
The left pane's Del button is red (`variant='error'`) while the right pane's Del button is blue (`variant='primary'`). The user wants both to be red for visual consistency — delete actions should share the same affordance.

## Change
**File:** `tutor/gui.py:198`

Change the `ThreadListItem` Del button variant from `'primary'` to `'error'`:

```python
# Before
yield Button('Del', id=f'delete-{self._meta.thread_id}', classes='thread-delete-btn', variant='primary')

# After
yield Button('Del', id=f'delete-{self._meta.thread_id}', classes='thread-delete-btn', variant='error')
```

This mirrors the left pane's `line-delete-btn` (tutor/gui.py:166-172), which already uses `variant='error'`. The armed-state CSS (`.thread-delete-btn.armed`) is unchanged — it continues to flip to `$warning` (yellow) on first click, matching the left-pane two-click confirm flow.

## Verification
- Run the GUI and visually confirm the right-pane thread Del button is red in its default state.
- Click once: background turns yellow (armed).
- Click again: thread is deleted.
- Confirm the left-pane Del button still looks identical to the right-pane one.
