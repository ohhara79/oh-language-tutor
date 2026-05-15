# Fix: loading-state CSS never matches because `.htmx-request` lands on the form

## Context

Commit `36fa3fe` added an in-flight loading state to the Explain / Ask /
Delete buttons in `tutor/templates/partials/line.html`, plus CSS in
`tutor/static/app.css` that targets `.btn.htmx-request` and uses
`hx-disabled-elt="this"` on each button.

In the browser, nothing visibly changes when Explain is clicked: no graying,
no "Explaining…" label, no disabled state. The user reports "There is no
changes."

**Root cause.** HTMX 2.0.4 (`tutor/templates/index.html:8`) attaches the
`.htmx-request` class to the *requesting element*, not to whatever element
triggered the submit. For

```html
<form hx-post="/commands/explain">
  <button type="submit" class="btn btn-ask" hx-disabled-elt="this">…</button>
</form>
```

the requesting element is the `<form>` (it owns `hx-post`). Verified against
the htmx 2.0.4 minified source — the `Zt` function does
`if(t==null){t=[e]}` then `e.classList.add(...requestClass)` with `e` being
the requester. So:

1. `.htmx-request` is applied to the `<form>`, not the `<button>` — our
   selector `.btn.htmx-request` (button+class on the same element) never
   matches.
2. `hx-disabled-elt` is read from the requesting element. Since it's set on
   the button (not the form), HTMX never sees it and never disables anything.

The label-swap rules and the gray styling are therefore both dead code, and
double-clicks are not prevented.

## Approach

Two surgical changes, no JS, no restructuring:

1. **Move `hx-disabled-elt` onto the form** and point it at the inner button
   with HTMX's `find` selector modifier, so HTMX both sees the attribute and
   applies `disabled` to the right element.
2. **Switch the CSS selectors to descendant form** — `form.htmx-request .btn`
   — so the rules fire when HTMX adds `.htmx-request` to the `<form>`.

This keeps the existing per-form structure (hidden `<input>` for IDs,
`hx-confirm` on Delete) untouched.

## Files to modify

### 1. `tutor/templates/partials/line.html`

For each of the four `<form>` blocks (Explain, Ask, and both Delete forms):

- Remove `hx-disabled-elt="this"` from the inner `<button>`.
- Add `hx-disabled-elt="find button"` to the `<form>`.

The two label spans (`btn-label-idle` / `btn-label-busy`) stay as-is.

Example diff for the Explain form:

```html
<form hx-post="/commands/explain"
      hx-target="#line-{{ entry.id }}"
      hx-swap="outerHTML"
      hx-disabled-elt="find button">
  <input type="hidden" name="entry_id" value="{{ entry.id }}">
  <button type="submit" class="btn btn-ask">
    <span class="btn-label-idle">Explain</span>
    <span class="btn-label-busy">Explaining…</span>
  </button>
</form>
```

### 2. `tutor/static/app.css`

Replace the block added after the existing `.btn-*` rules (lines 104–118
post-commit) so the selectors target the button via its busy parent form:

```css
form.htmx-request .btn-label-idle { display: none; }
form.htmx-request .btn-label-busy { display: inline; }
.btn .btn-label-busy { display: none; }

.btn:disabled,
form.htmx-request .btn {
    cursor: not-allowed;
    color: #888;
    border-color: #ccc;
    background: rgba(128, 128, 128, 0.08);
}
.btn:disabled:hover,
form.htmx-request .btn:hover {
    background: rgba(128, 128, 128, 0.08);
}
```

In the dark-mode block, update the corresponding rule:

```css
.btn:disabled,
form.htmx-request .btn { color: #888; border-color: #555; }
```

Note: `.btn:disabled` is kept because `hx-disabled-elt="find button"` adds
the real `disabled` attribute to the button — covering it in CSS keeps the
visuals consistent even without the form class, and is the styling HTML
elements naturally take when disabled.

## Why not move all `hx-*` to the button instead?

That works (the button would become the requester and the original CSS
would match) but it requires removing the wrapping `<form>`, moving hidden
inputs into `hx-vals`, and moving `hx-confirm` to the button — a bigger
diff that loses the form-based grouping. We're keeping the form-centric
pattern that's already established in this template.

## Verification

1. Restart the dev server (the static-asset cache buster
   `?v={{ version }}` in `tutor/templates/index.html` is computed from
   `time.time()` on each render, so a page reload after restart will pick
   up the new CSS — no hard refresh needed).
2. Open the UI, load a `.srt`, click **Explain** on a line without an
   explanation:
   - Label switches to **Explaining…** during the request
   - Button is visibly gray, cursor is `not-allowed`
   - Re-clicking the button is a no-op (DevTools: the `<button>` has
     `disabled` attribute while the request is in flight)
   - On response, the line block is replaced by the rendered explanation
3. Click **Ask** on an explained line → **Opening…** + gray during the POST.
4. Click **Delete**, accept the confirm dialog → **Deleting…** + gray during
   the POST.
5. Toggle OS to dark mode and re-confirm the gray state is still distinct
   from the active state.
6. `make lint` — purely template + CSS, should remain green.
