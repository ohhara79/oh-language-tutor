# Fix: Only the title text should open the picker

## Context

In the writing view, the header shows the current dataset directory name as a link (`<a class="view-dir-label" href="/">`) next to a hamburger menu button. Clicking that link navigates to `/`, which is the dataset picker screen.

The user reports that clicking the empty space *around* the title also opens the picker. The picker should open only when the user clicks the title text itself.

## Root cause

`tutor/templates/index.html:13-18` renders the header row:

```html
<div class="header-row">
  <a class="view-dir-label" href="/" title="{{ view_dir }}">{{ view_dir }}</a>
  <button type="button" id="menu-btn" class="btn menu-btn" ...>&#9776;</button>
</div>
```

`tutor/static/app.css:26-45` styles it:

```css
.header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
}

.view-dir-label {
    ...
    min-width: 0;
    flex: 1;                  /* <-- causes the issue */
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    ...
}
```

The `flex: 1` on `.view-dir-label` makes the `<a>` grow to fill all space between itself and the menu button. The whole expanded box is clickable, so clicking the gap between the title text and the menu button is treated as a click on the link and navigates to the picker.

## Change

Remove `flex: 1` from `.view-dir-label` in `tutor/static/app.css` (line 38).

After the change, the link is sized to its content (default flex `0 1 auto`). Short titles produce a narrow link with no surrounding click area; the menu button is still right-aligned via the existing `justify-content: space-between` on `.header-row`. Long titles still truncate correctly because `min-width: 0`, `overflow: hidden`, `white-space: nowrap`, and `text-overflow: ellipsis` remain in place — the flex container will shrink the link to fit alongside the menu button, and the truncated text fills the entire link box (so the click area still maps to "the title").

## Files

- `tutor/static/app.css` — remove the `flex: 1;` line inside the `.view-dir-label` rule (around line 38).

## Verification

1. Start the app the usual way and open the writing view for a dataset.
2. Click directly on the title text → picker opens (unchanged behavior).
3. Click the empty area between the title and the hamburger button → nothing happens (was: opened the picker).
4. With a very long directory name that gets ellipsized, click on the ellipsized text → picker still opens; click on any gap that may exist between the ellipsis and the menu button → no navigation.
5. Confirm the hamburger menu button still works and is right-aligned.
