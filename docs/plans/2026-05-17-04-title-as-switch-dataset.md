# Promote header title to "Switch dataset" link

## Context

The hamburger menu has a "Switch dataset" entry (`<a href="/?picker=1">`)
that the user wants to remove. The dataset name in the sticky header
(`.view-dir-label`) is the natural affordance for "change what I'm
looking at," so making it clickable lets the menu item go away without
losing the action. The title click goes to `/?picker=1` — the same
target as today's menu link.

This continues the menu-trimming work from the prior commit
(`468858a` "Compact the hamburger menu panel."): one fewer row + one
fewer separator further reduces panel height and keeps the menu
focused on settings and filters.

## Approach

### HTML — `tutor/templates/index.html`

- Change the title element from a `<span>` to an `<a>`:
  ```html
  <a class="view-dir-label" href="/?picker=1" title="{{ view_dir }}">{{ view_dir }}</a>
  ```
  Keep the `title` attribute — it already shows the full directory name
  on hover when ellipsized, which we want to retain.
- Delete lines 35-36 (the separator + Switch dataset link).

### CSS — `tutor/static/app.css`

Extend `.view-dir-label` (currently lines 32-41) so it behaves like a
plain title at rest and a link on hover:

```css
.view-dir-label {
    /* existing rules */
    color: inherit;
    text-decoration: none;
    cursor: pointer;
}
.view-dir-label:hover { text-decoration: underline; }
.view-dir-label:focus-visible { outline: 2px solid #8ab; outline-offset: 2px; }
```

`color: inherit` + `text-decoration: none` neutralize the default
user-agent link styling so the title visually matches today. The
hover underline + focus ring provide the affordance the user picked.

### JS — no change

`document.querySelector('.view-dir-label')?.textContent` at the top of
the IIFE in `tutor/static/app.js` (line 16) keeps working — `<a>` and
`<span>` both expose `.textContent` the same way.

## Files to touch

- `tutor/templates/index.html` — convert the `<span>` to `<a>` on line
  14; delete the menu separator + Switch dataset link (lines 35-36).
- `tutor/static/app.css` — add three properties to `.view-dir-label`
  and two new selectors (`:hover`, `:focus-visible`).

No backend changes; the `/?picker=1` route already exists and is
unchanged.

## Verification

1. `make lint` passes.
2. Manual browser check:
   - Open a dataset. Confirm the title looks the same as before (same
     font, same color, no underline at rest).
   - Hover the title on desktop → cursor turns pointer, underline
     appears.
   - Click the title → lands on the dataset picker (same as the old
     menu item).
   - Tab to the title with a keyboard → visible focus ring; Enter
     activates it.
   - Open the hamburger menu → "Switch dataset" row and its separator
     are gone; remaining items (Show only explained, Jump slider,
     audience config, Reset settings) are intact.
   - Mobile / DevTools touch emulation → tap the title navigates to
     the picker. (No hover affordance is expected; the `title` tooltip
     also doesn't fire on touch, which is normal.)
   - Switch to a dataset with a long name → the title still ellipsizes
     and the `title=` tooltip still shows the full name on hover.
