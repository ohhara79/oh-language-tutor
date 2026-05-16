# Tighten the hamburger panel width and cap the audience inputs

## Context

After the previous compact-mode change (commit `e79a996`), the menu panel rendered ~46rem wide on a real device — short rows like "Show only explained" / "Switch dataset" had a half-screen gap of empty space on the right, and the audience inputs stretched correspondingly wide for no reason.

Root cause: `.menu-panel` had `position: absolute; right: 1rem;` with no `width` and only `min-width: 14rem`. With only `right` set and no `left`/`width`, the browser uses the "shrink-to-fit" sizing algorithm, which interacts badly with flex children that use `flex: 1; min-width: 0`. The audience inputs grow to "fill available space" — and the available space resolves to the containing block (the header), so the panel ends up at roughly the header's width.

Fix: give the panel an explicit `width`, and replace `flex: 1` on the audience inputs/select with a fixed `flex-basis` so they sit at a sensible size.

## Approach

One file: `tutor/static/app.css`.

- `.menu-panel`: replace `min-width: 14rem` with `width: 15rem`. 15rem ≈ 240px — comfortably wider than "Show only explained" + checkbox (~13rem) and the audience row (label 4rem + gap 0.5rem + input 8rem = 12.5rem of `.menu-cfg` content, plus 1.5rem padding = 14rem). Narrower than the previous shrink-to-fit width, so the panel hugs its content. Fits inside a 320px-wide viewport.
- `.menu-cfg .cfg-field input, .menu-cfg .cfg-field select`: replace `flex: 1; min-width: 0; width: auto` with `flex: 0 1 8rem; min-width: 0`. The inputs no longer expand to fill the row; they sit at ~8rem and can still shrink if the panel is ever forced narrower. 8rem comfortably fits the longest dropdown option ("intermediate") plus the native select arrow.

## Files to modify

- `tutor/static/app.css`

## Verification

1. `make lint` clean.
2. Reload `/tutor`, click the hamburger.
3. Panel renders ~240px wide. Empty space on the right of "Show only explained" / "Switch dataset" is minimal.
4. Each audience row's right edge aligns; input boxes sit at ~8rem with "intermediate" fitting comfortably.
5. Explain still POSTs `source_language` / `target_language` / `level`.
