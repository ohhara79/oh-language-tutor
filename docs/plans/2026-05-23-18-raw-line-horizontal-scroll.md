# Remove horizontal scrollbar in the raw text list view

## Context

The raw text list view (the main `#stream-pane` in `tutor/templates/index.html`)
showed an unwanted horizontal scrollbar. Each entry renders a `.raw-toggle`
button inside a `.line` section.

There is no global `box-sizing: border-box` reset in `tutor/static/app.css`
(only `.cfg-field input/select` and `.thread-compose textarea` set it
individually). `.raw-toggle` uses `width: 100%` together with
`padding: 0.25rem 0.5rem`, so under the default `content-box` its rendered
width becomes 100% **plus** 1rem of horizontal padding. On explained lines it
is worse: `.has-explanation .raw-toggle` adds a 3px `border-left`, which
`content-box` also stacks on top of the 100% width. Both push the row past the
viewport's right edge, forcing the horizontal scrollbar.

The text itself already wraps (`white-space: pre-wrap; word-break: break-word`),
so the scrollbar was never necessary — it was purely the box-model overflow.

## Recommended change

In `tutor/static/app.css`, add `box-sizing: border-box` to `.raw-toggle` so the
horizontal padding and the explained-line border are included within the 100%
width instead of being added on top of it.

```css
.raw-toggle {
    display: block;
    width: 100%;
    box-sizing: border-box;
    ...
}
```

## Critical files

- `tutor/static/app.css` — `.raw-toggle` rule (around line 231).

## Verification

1. `uv run --frozen` start the app and load the index list view.
2. Confirm there is no horizontal scrollbar in the raw text list.
3. Check a line that has an explanation (3px `border-left`) — still no overflow.
4. Confirm long raw lines still wrap rather than scroll.
5. `make lint` — no Python changes, but run for hygiene (passes).
