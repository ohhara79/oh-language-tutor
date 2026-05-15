# Add in-flight loading state to line action buttons

## Context

The per-line **Explain** button (added in commit 2205539) calls Claude on the
backend and can take several seconds. Today the button gives no visual feedback
while the request is in flight, so users may click it again — re-submitting the
form. The **Ask** and **Delete** buttons share the same risk to a lesser
degree.

We want a clear "this is processing" signal: while the HTMX request is in
flight, the button should gray out, become un-clickable, and swap its label to
a present-progressive form (e.g. `Explain` → `Explaining…`). Scope confirmed
with the user: apply to Explain, Ask, and both Delete buttons.

## Approach

HTMX has first-class primitives for this — no JS needed.

- `hx-disabled-elt="this"` adds the `disabled` attribute to the button while
  the request is in flight, blocking double-submits.
- HTMX automatically adds the class `.htmx-request` to the element that
  initiated the request for the duration of the request. We use this to drive
  CSS (gray background + label swap).
- Label swap uses two child `<span>`s — idle and busy — toggled via the
  `.htmx-request` class. This is more accessible than a CSS `content`
  pseudo-element and avoids hard-coding text inside CSS.

Specificity note: `.btn.htmx-request` and `.btn:disabled` both compute to
specificity (0,2,0), which beats the existing `.btn-ask` / `.btn-del`
single-class rules (0,1,0) — so the gray styling wins regardless of source
order.

## Files to modify

### 1. `tutor/templates/partials/line.html`

Update all four action buttons (Explain at line 27, Ask at line 12, and the
two Delete buttons at lines 18 and 33). Each becomes:

```html
<button type="submit" class="btn btn-ask" hx-disabled-elt="this">
  <span class="btn-label-idle">Explain</span>
  <span class="btn-label-busy">Explaining…</span>
</button>
```

Label pairs:
- Explain → `Explaining…`
- Ask → `Opening…` (the action POSTs to `/commands/open_thread`)
- Delete → `Deleting…` (both occurrences)

The Delete buttons retain their `hx-confirm` — the loading state only kicks in
*after* the user accepts the browser confirm dialog, which is the desired
behavior.

### 2. `tutor/static/app.css`

Add a new block right after the existing button rules (after line 102), so
edits stay co-located:

```css
.btn .btn-label-busy { display: none; }
.btn.htmx-request .btn-label-idle { display: none; }
.btn.htmx-request .btn-label-busy { display: inline; }

.btn:disabled,
.btn.htmx-request {
    cursor: not-allowed;
    color: #888;
    border-color: #ccc;
    background: rgba(128, 128, 128, 0.08);
}
.btn:disabled:hover,
.btn.htmx-request:hover {
    background: rgba(128, 128, 128, 0.08);
}
```

And in the dark-mode block (extend the rules added near line 238–240):

```css
.btn:disabled,
.btn.htmx-request { color: #888; border-color: #555; }
```

## What we are NOT changing

- No JavaScript changes — `tutor/static/app.js` is untouched. HTMX provides
  everything we need.
- No backend changes — `tutor/web.py` is untouched.
- We do not introduce a generic spinner or `hx-indicator`. The button itself
  is the indicator; that's sufficient and avoids new DOM.

## Verification

1. Run `make lint` — purely template + CSS, so it should pass; this confirms
   nothing in Python regressed.
2. Start the web server (per project README — typically `uv run --frozen
   oh-language-tutor` or similar; check README if unsure) and open the UI.
3. Load a `.srt` so lines appear, then:
   - Click **Explain** on a line without an explanation. Confirm the label
     switches to **Explaining…**, the button turns gray, the cursor becomes
     `not-allowed`, and a second click is ignored (the button has the
     `disabled` attribute — verifiable in DevTools). When the response
     returns, the button is replaced by the rendered explanation block.
   - Click **Ask** on an explained line. Confirm **Opening…** + gray state
     during the POST to `/commands/open_thread`.
   - Click **Delete**, accept the confirm dialog, and confirm **Deleting…**
     + gray state during the request.
4. Toggle the OS to dark mode and re-verify the disabled state still reads as
   visibly distinct from the active state.
