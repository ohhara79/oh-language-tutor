# Widen reader layout to use full screen width

## Context

The reader currently caps `body` at `max-width: 44rem` in `tutor/static/app.css:6`, so on wide-screen monitors the sentence list sits in a narrow centered column with large empty margins on both sides (see screenshot). The user wants the content to flow into that empty space without a hard breakpoint — the layout should simply use whatever width is available, on every screen size.

## Approach

Remove the artificial column cap. The existing 1rem horizontal padding on `body` already provides edge gutters, and the sticky `header` already uses `margin: 0 -1rem` to align with the body padding, so dropping `max-width` will not break header alignment.

### Change

`tutor/static/app.css`, in the `body` rule (lines 3–9):

- Delete `max-width: 44rem;`
- Keep `margin: 0 auto` (harmless when there's no max-width, and preserves centering if a max is reintroduced later)

After the change:

```css
body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    margin: 0 auto;
    padding: 0 1rem 1rem;
    line-height: 1.55;
}
```

That's the only change. No HTML, no JS, no new media queries.

### Why this is sufficient

- `.line`, `.raw-toggle`, `.line-detail`, `.explanation-body`, and `.thread-conversation` are all already `display: block` / `width: 100%` inside `body`, so they grow with the body automatically.
- The hamburger menu panel (`.menu-panel`) is anchored to `right: 1rem` and has a fixed `width: 15rem`, so it stays in the same visual position regardless of body width.
- The `.line.has-explanation` left blue border, the per-line top divider, and the existing font-size / opacity sliders all continue to work — they don't depend on column width.
- Header `margin: 0 -1rem` still aligns with body padding regardless of viewport width.

### Trade-off (acknowledged, not addressed in this plan)

On ultra-wide monitors, the English/Korean explanation markdown (`.explanation-body`) will wrap at the full viewport width, which can hurt long-prose readability. The user explicitly asked to "just use the available area" without a breakpoint, so we keep this plan minimal. If readability becomes a problem later, the targeted follow-up would be to cap `.explanation-body { max-width: …; }` only — leaving the source-sentence column full-width.

## Verification

1. Run the app per the project's run skill / `make` target and load a state directory with several entries.
2. In a wide browser window (≥ 1600px), confirm the sentence list spans nearly the full window width (with the 1rem side padding) instead of being pinned to a ~700px centered column.
3. Resize the window narrow (e.g., phone width ~ 400px) and confirm the layout still looks correct: sentences still readable, header sticky, hamburger menu still anchored to the right, no horizontal scroll.
4. Open the hamburger menu and verify the panel still appears in the top-right corner and the existing sliders (opacity, font size, jump) still function.
5. Expand a sentence (tap it) and verify the inline explanation panel still renders correctly at the new width.
6. `make lint` (per CLAUDE.md, even though no Python changed, to confirm no incidental regressions).
