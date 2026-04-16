# Fix intermittent slow ASK/DEL button response

## Context

After the TUI responsiveness fix (commit 8552938), thread dispatch is responsive, but ASK and DEL buttons in the left pane still sometimes take ~1 sec to respond. The root cause has three layers:

1. **DOM query overhead** (commit 3ba9b88): `_scroll_left_pane_to_anchor_id()` and `_apply_tutor_entry_removed()` did O(n) DOM walks via `stream.query(LineBlock)`. Fixed by maintaining a `_line_blocks` dict for O(1) lookup.

2. **Textual Button active-effect overhead**: Textual's `Button` widget calls `add_class("-active")` on every click, which triggers `update_node_styles()` → `stylesheet.update_nodes`. A timer then calls `remove_class("-active")`, triggering another round. Each cycle does CSS rule matching and can cascade into layout passes. With ~3,760 widgets this is expensive.

3. **`scroll_to_widget` forcing full layout** (main fix): `_scroll_left_pane_to_anchor_id` called `scroll_to_widget` synchronously. This accesses `widget.virtual_region_with_margin` → `screen.find_widget()` → `compositor.find_widget()` → `compositor.full_map`. After any scroll, Textual's `reflow_visible()` sets `_full_map_invalidated = True` (a fast-path optimization that only lays out visible widgets). When `full_map` is accessed with this flag set, it triggers `_arrange_root(visible_only=False)` which lays out ALL ~3,760 widgets synchronously. This is why the slowness appeared specifically after scrolling from one end of the list to the other.

### Failed approach: `can_focus=False`

Setting `can_focus=False` on buttons made the problem **worse** (always slow instead of intermittent). Reason: with `can_focus=False`, Textual's `get_focusable_widget_at()` walks ancestors and finds the `ScrollableContainer` (#stream-pane). Focus moves there, triggering `update_node_styles()` on the container — which calls `walk_children(with_self=True)` and processes ALL ~3,760 descendants. With `can_focus=True` (default), focus goes to the button itself (a leaf node), so only 1 widget is processed.

## Changes

**File: `tutor/gui.py`**

### 1. `_line_blocks` dict for O(1) lookup (already done in 3ba9b88)

- `self._line_blocks: dict[str, LineBlock] = {}` in `__init__`
- Populated in `_restore_tutor_entries` and `_apply_explanation`
- Cleaned up in `_apply_tutor_entry_removed`
- Used in `_scroll_left_pane_to_anchor_id` (replaces `stream.query(LineBlock)`)

### 2. `_QuickButton` subclass to eliminate active-effect overhead

Introduce `_QuickButton(Button)` (keeps `can_focus=True`) with `active_effect_duration = 0.0`. This eliminates the `-active` class add/remove cycle (2 `update_node_styles` calls + a timer per click) while keeping focus on the button itself (leaf node, cheap).

Use `_QuickButton` in place of `Button` in:
- `LineBlock.compose()` (ASK and DEL buttons)
- `ThreadListItem.compose()` (OPEN and DEL buttons)

### 3. Remove `remove_class('-active')` workaround

The line `event.button.remove_class('-active')` in `on_button_pressed` was a workaround for Textual's `-active` class getting stuck. With `active_effect_duration = 0`, the class is never added, so the workaround is unnecessary.

### 4. Defer `scroll_to_widget` via `call_after_refresh`

Replace the synchronous `scroll_to_widget` call in `_scroll_left_pane_to_anchor_id` with a deferred call via `self.call_after_refresh(...)`. This way the scroll runs after the next layout pass (which resolves `_full_map_invalidated` as part of its normal cycle), avoiding a redundant synchronous full-layout triggered by `find_widget` → `full_map`.

## Verification

1. `uv run --frozen basedpyright tutor/gui.py` — type check passes
2. Run the TUI and click ASK/DEL buttons rapidly — response should be immediate every time
3. Click ASK on last sentence, scroll to first sentence, click ASK there — should be fast
4. Verify delete arming/disarming still works (DEL → CFM? → DEL after timeout)
5. Verify thread OPEN and DEL buttons in right pane work correctly
6. Verify keyboard navigation (Tab) still works for Input widget
7. Verify reopen-thread scrolls the left pane to the correct anchor
