# Scroll to bottom on startup

## Context
When the app starts and restores saved entries (left pane) and thread list (right pane), neither pane scrolls to the bottom. The user wants to see the most recent content immediately.

## Plan

Edit `on_mount` in `tutor/gui.py` to schedule a scroll-to-bottom for both panes after restore completes.

**File:** `tutor/gui.py`

In `on_mount` (line 240), after `_restore_tutor_entries()`, add a `call_after_refresh` callback that scrolls both `#stream-pane` and `#thread-list-container` to the end:

```python
def on_mount(self) -> None:
    self.console.push_theme(_MD_THEME)
    self._refresh_thread_list()
    self.query_one('#thread-messages', ScrollableContainer).display = False
    self.query_one('#thread-input', Input).display = False
    self._restore_tutor_entries()
    self.call_after_refresh(self._scroll_panes_to_end)

def _scroll_panes_to_end(self) -> None:
    self.query_one('#stream-pane', ScrollableContainer).scroll_end(animate=False)
    self.query_one('#thread-list-container', ScrollableContainer).scroll_end(animate=False)
```

Using `call_after_refresh` ensures the layout is computed before scrolling.

## Verification
- Run the app with existing saved state (`tutor.json` with entries, saved threads)
- Confirm both panes show the bottom content on startup
