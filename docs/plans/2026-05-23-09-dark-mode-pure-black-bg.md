# Make dark-mode background pure black behind reduced opacity

## Context

In dark mode the body uses `background: #1a1a1a` (dark gray). The opacity
slider applies `opacity: var(--page-opacity, 1)` to `body`
(`tutor/static/app.css:123`). CSS `opacity` makes the whole element — including
its background — semi-transparent, so at lower opacity values the browser's
default `html` background (typically light) bleeds through, mixing with
`#1a1a1a` to produce a gray cast.

Two things need to change for the page to look truly black when opacity is
reduced:

1. The body's own background should be `#000` instead of `#1a1a1a`.
2. The `html` element behind the body needs an explicit black background in
   dark mode — otherwise the gray bleed-through persists no matter what the
   body color is.

## Change

`tutor/static/app.css`, dark mode block at lines 458–484. Update the body
background and add an `html` rule alongside it:

```css
@media (prefers-color-scheme: dark) {
    html { background: #000; }
    body { background: #000; color: #eee; }
    ...
}
```

No other rules need to change. Light mode is unaffected (it keeps `Canvas`).

## Verification

1. Start the app and load any view in a browser with the OS in dark mode.
2. Open the hamburger menu and drag the opacity slider from 100% down to 10%.
3. At every step the page background should remain pure black — no gray tint
   from the html element showing through.
4. Re-check in light mode (OS light theme) to confirm light mode appearance is
   unchanged.
