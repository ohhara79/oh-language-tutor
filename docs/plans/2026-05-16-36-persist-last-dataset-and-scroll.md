# Persist last dataset and last scroll position across browser restarts

## Context

Closing the browser dropped two pieces of state:

1. **Dataset choice.** The server already tracked it via the `view_state_dir` cookie, but `set_cookie` was called without `max_age` so it was a session cookie — most browsers discard it on close. On reopen, the user was bounced back to the picker.
2. **Scroll position.** `tutor/static/app.js` unconditionally jumped to the bottom (newest sentence) on every load.

Goal: reopening the browser (either restoring `/tutor` from a previous tab or visiting `/`) lands the user back on the same dataset, scrolled to the same position.

Storage split: cookie for the dataset (the server already reads it to resolve the session — single source of truth), localStorage for the scroll-anchor map (purely client state; no point putting it on every HTTP request).

## Approach

### `tutor/web.py`

- `open_state_dir`: add `max_age=365 * 24 * 3600` to the `set_cookie` call so the dataset cookie persists for a year.
- `picker`: when the request has a valid `view_state_dir` cookie *and* no `?picker=1` query, redirect to `/tutor`. Reuses the existing `_resolve_view_session` helper for cookie validation. When `?picker=1` is set, render the picker as before so the "Switch dataset" flow still works.

### `tutor/templates/index.html`

- Change `Switch dataset` link from `href="/"` to `href="/?picker=1"`.

### `tutor/static/app.js`

- Read the dataset name from `.view-dir-label`'s text content.
- Store a JSON map under `localStorage['tutor.lastAnchors']` mapping dataset name → anchor id (the line's `data-anchor-id`, populated from `entry.id` — stable UUID).
- On init, before the existing scroll-to-bottom, look up the saved anchor; if the matching `.line` is rendered, `scrollIntoView({block: 'start'})`. If not found, fall back to scroll-to-bottom.
- Extend the existing `wasAtBottom` scroll listener with a 200 ms debounced save of the topmost-visible line's anchor (list view only).

## Files modified

- `tutor/web.py`
- `tutor/templates/index.html`
- `tutor/static/app.js`

## Verification

1. `make lint` clean.
2. Pick dataset A → scroll → close browser → reopen at `/tutor`: lands on dataset A at the saved line.
3. Reopen at `/`: server redirects to `/tutor` with dataset A at the saved position.
4. Hamburger → Switch dataset: picker is shown (because `?picker=1` is set). Pick dataset B → scroll → close → reopen: lands on dataset B at its own saved position; dataset A's saved position untouched.
5. Scroll to bottom → reload: still at bottom.
6. Delete the line that's the saved anchor → reload: falls back to scroll-to-newest.
7. Brand-new browser (no cookie, no localStorage): `/` shows picker; pick once → `/tutor` lands at bottom.
