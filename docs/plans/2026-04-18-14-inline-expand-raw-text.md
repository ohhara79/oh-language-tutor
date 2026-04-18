# Inline-expand raw text explanations (replace line-detail view)

## Context

Today, clicking a raw text in the list navigates into a dedicated line-detail view (`body.view-line`) that hides every other line and shows the explanation + Ask/Delete buttons for the clicked one. Returning to the list requires the Back button. That's a full screen transition for what is essentially "show me this one explanation."

The proposed change: in the list view, clicking a raw text expands its explanation + Ask/Delete buttons inline directly beneath it, accordion-style. Clicking another raw text collapses the previous panel and expands the new one. Clicking the same raw text again collapses it (toggle). The browser Back button is no longer tied to expansion — it only applies to the thread view.

Benefits: one-tap disclosure, no round-trip navigation, can glance at neighboring entries while reading an explanation. The DOM already has the pieces needed (`.line.active` class, `.line-detail` block, Ask/Delete forms), so this is primarily a JS + CSS change.

## Changes

### 1. CSS — `tutor/static/app.css`

Collapse the `view-line` body state entirely; expansion is now controlled by `.line.active` alone, independent of which view is active.

- **Remove** the line-view rules (lines 223–230):
  ```
  body.view-line #back-btn { display: inline-flex; }
  body.view-line .line { display: none; }
  body.view-line .line.active { display: block; }
  body.view-line .line.active .line-detail { display: block; }
  body.view-line .line.active .raw-toggle { font-weight: 600; cursor: default; }
  body.view-line #orphan-threads-section,
  body.view-line #thread-conversation { display: none; }
  ```
- **Replace** the list-view hide rule at line 220 with an active-aware version:
  ```
  body.view-list .line:not(.active) .line-detail { display: none; }
  body.view-list .line.active .raw-toggle { font-weight: 600; }
  ```
  (The `body.view-thread #stream-pane { display: none; }` rule at line 234 already hides expanded panels when the thread view is active, so we don't need a thread-view override.)

### 2. JS — `tutor/static/app.js`

Remove the `'line'` view from the navigation stack and turn the raw-toggle click into a pure DOM toggle.

- **Click handler** (lines 67–76): instead of `push('line', {anchorId})`, toggle `.active` on the clicked `.line`, clearing `.active` from any other line first. Works in list view only (thread view hides the stream-pane anyway, so the guard can stay as `current().view !== 'list' return;` — or be simplified).
  ```js
  document.getElementById('stream-pane').addEventListener('click', (e) => {
      if (current().view !== 'list') return;
      const toggle = e.target.closest('.raw-toggle');
      if (!toggle) return;
      const line = toggle.closest('.line');
      if (!line) return;
      const wasActive = line.classList.contains('active');
      document.querySelectorAll('.line.active').forEach((el) => el.classList.remove('active'));
      if (!wasActive) line.classList.add('active');
  });
  ```
- **`render()`** (lines 14–34): drop the `.line.active` clearing loop and the `c.view === 'line'` branch. The function now only handles `list` and `thread`. The `view-line` body class is never added.
- **`popstate` listener and `pop()`**: keep as-is — they still serve the thread view.
- **Thread-view back from Ask**: when the user clicks Ask inside an expanded panel, `htmx:afterSwap` on `#thread-conversation` still fires `push('thread')` from list view (not from line view anymore). Back from thread view pops to list view; the previously-expanded `.line` keeps its `.active` class in the DOM, so the panel stays open. This is the desired behavior.
- **Delete from thread view**: the existing `history.back()` branch at line 115 pops thread → list, which is still correct.

### 3. Template — no changes

`tutor/templates/partials/line.html` already renders the `.line-detail` block with Ask/Delete inside each `.line`. The `body.view-list` CSS change is what makes it visible when `.active` is toggled.

## Files to modify

- `tutor/static/app.js` — click handler + `render()` simplification
- `tutor/static/app.css` — remove `view-line` rules, update list-view visibility rules

## Verification

1. Start the app (check README/pyproject for the dev entrypoint) and open the browser.
2. Click a raw text → its explanation + Ask/Delete buttons appear directly below it; other lines remain visible.
3. Click a different raw text → the previous panel collapses; the new one expands.
4. Click the same raw text a second time → it collapses.
5. With a panel expanded, click Ask → thread view opens; press Back → returns to list view with the same panel still expanded.
6. With a panel expanded, click Delete → line + its threads disappear; list view remains; no stale `.active` state left behind.
7. Let SSE deliver a new explanation → new line appears at the bottom in the list; does not disturb any currently expanded panel.
