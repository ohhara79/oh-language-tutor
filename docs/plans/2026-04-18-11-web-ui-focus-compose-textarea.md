# Focus the compose textarea after Ask / follow-up send (web UI)

## Context

In the web UI, clicking the **Ask** button on a line opens the thread conversation (HTMX swap of `#thread-conversation`) but leaves keyboard focus on the Ask button — the user has to click into the textarea before typing. The same gap exists after sending a follow-up: the textarea is cleared but not refocused, so the user must click it again to type the next message.

The TUI (`tutor/tui.py`) already handles this correctly by calling `inp.focus()` after opening a new thread, reopening one, and after streaming completes. The web UI has no equivalent focus management — this plan adds it.

## Approach

Two small additions to `tutor/static/app.js`, both inside existing event handlers. No template or CSS changes.

### 1. Focus the textarea after the thread-conversation swap

In the `htmx:afterSwap` handler (currently `app.js:96-115`), when `t.id === 'thread-conversation'` and the content is not the empty-state (`!isEmpty`), query for the follow-up textarea inside `t` and call `.focus()` on it.

This covers every path that swaps `#thread-conversation`:
- Clicking **Ask** on a line (`tutor/templates/partials/line.html:7-12`)
- Tapping an existing thread entry
- Anything else that populates the conversation with a real thread

The `isEmpty` branch is already handled (it pops back to the previous view), so focusing only when non-empty is the right gate.

### 2. Focus the textarea after a successful follow-up send

In the `htmx:afterRequest` handler (currently `app.js:222-228`), after the existing `ta.value = ''` line, also call `ta.focus()`. This keeps the caret in the textarea after the response message appends, so the user can immediately type the next follow-up.

The handler already checks `evt.detail.successful`, so failures (network error, validation) won't steal focus.

## Critical files

- `tutor/static/app.js` — only file that needs editing
  - Edit 1: inside the `t.id === 'thread-conversation'` branch of `htmx:afterSwap` (~line 102), add `t.querySelector('textarea[name="text"]')?.focus()` in the non-empty path.
  - Edit 2: inside the `htmx:afterRequest` handler for `form.thread-compose` (~line 227), call `ta.focus()` right after `ta.value = ''`.

## Verification

Run the web server and exercise both paths in a browser:

1. `uv run --frozen <web-entrypoint>` — start the web UI (check `tutor/web.py` for the exact command if unsure).
2. Click **Ask** on any line. Expected: the compose textarea in the thread view is focused (blinking caret inside, typing a letter goes into the textarea without a click).
3. Type a follow-up and press **Enter** to send. Expected: after the response appends, the textarea is cleared *and* still focused; typing continues without a click.
4. Tap an existing thread entry (not the Ask button). Expected: same focus behavior — textarea is focused on arrival.
5. Delete a thread while viewing it. Expected: the history-back path still runs; no focus error in the console.
6. Open browser devtools console during all steps and confirm no JS errors (`querySelector` on missing textarea should be safe via optional chaining / null check).
