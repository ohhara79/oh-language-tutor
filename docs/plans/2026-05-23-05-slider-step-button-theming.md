# Fix `.slider-step` button theming in hamburger menu

## Context

In commit `6b60105` (plan `2026-05-23-04`) I added `−` / `+` step buttons
next to the Opacity and Font Size sliders. The buttons render badly in
the dark theme: the fill is a hardcoded light grey `#f5f5f5` against the
menu's dark background, the `−` / `+` glyphs are nearly invisible
because no `color` is set, and the disabled `+` button on the Opacity
row (value at 100%) shows up as a solid opaque grey block with no
visible glyph.

Root cause: `.slider-step` was written with light-mode-only colors and
no `@media (prefers-color-scheme: dark)` override. Every other control
inside the menu (`.cfg-field input`, `.cfg-field select`, `.menu-item`)
uses the project's actual convention: **`background: transparent;
border: 1px solid #bbb; color: inherit;`** — so the OS theme drives the
surface, and the glyph color inherits from `body` (which itself flips
between `#000` and `#eee` in the existing dark-mode block at
`app.css:454`).

## Decisions

Rewrite the `.slider-step` rule set in `tutor/static/app.css` to follow
the same convention as `.cfg-field input` / `.cfg-field select`
(`app.css:173–188`):

- `background: transparent` (was `#f5f5f5`) — so the menu panel's
  `Canvas` system color shows through and adapts to OS theme.
- `color: inherit` (new) — glyphs read against either light or dark
  body color automatically.
- `border: 1px solid #bbb` (was `#999`) — matches the input border
  exactly.
- `font: inherit; line-height: 1.2` — match input metrics so the
  vertical alignment of the `−` glyph sits where the user expects.
- Keep `min-width: 32px; min-height: 32px; border-radius: 4px;
  padding: 0 0.5rem; cursor: pointer; flex: 0 0 auto`.
- Replace the prior `:active { background: #e0e0e0 }` with the
  theme-neutral `rgba(128, 128, 128, 0.1)` pattern used by
  `.menu-item:hover` (`app.css:67–77`); apply it to **both
  `:hover:not(:disabled)` and `:active:not(:disabled)`** so there is
  tactile feedback before the click registers and the disabled button
  never gains the highlight.
- Add `:focus-visible { outline: 2px solid #8ab; outline-offset: 1px; }`
  mirroring the inputs at `app.css:186` for keyboard users.
- Disabled state changes from `opacity: 0.5` to `opacity: 0.4`
  (slightly more aggressive) + `cursor: not-allowed`. Because the base
  is now transparent with an inherited glyph color, the disabled
  button reads as a faded outlined button rather than an opaque grey
  block — the glyph stays visible at ~40% which is the desired "you
  cannot click further" cue.

No HTML changes. No JS changes. No new CSS variable — the existing
convention is hardcoded hex per rule and a `@media
(prefers-color-scheme: dark)` override block; `.slider-step` does not
need its own dark override because every color it now uses is either
`inherit`, `transparent`, or the same `#bbb` already used by the dark
override on inputs.

## Files to modify

1. `tutor/static/app.css` — replace the `.slider-step` /
   `.slider-step:active` / `.slider-step:disabled` rules (currently
   `app.css:102–115`) with the rule set described above. The
   `.slider-row` rule directly above stays as-is.

That is the entire patch — one CSS block.

## Verification

1. `make lint` — must pass.
2. Open the hamburger menu in light mode (or with `prefers-color-scheme:
   light`): buttons show a white-ish surface with a subtle `#bbb`
   border and dark `−` / `+` glyphs — matches the Learning / Native
   text inputs sitting below.
3. Switch the OS / browser to dark mode and reopen the menu: buttons
   now blend into the dark panel with the same `#bbb` border but
   light glyphs (inherited from body `#eee`) — readable against the
   dark surface.
4. Drag Opacity to 100%: the `+` button becomes disabled. Confirm the
   `+` glyph is still visible (at ~40% opacity), the button is
   outlined, and clicking it does nothing. This is the specific
   "solid grey block" case from the bug report — it should now read
   as a faded `+`.
5. Drag Opacity to 30%: `−` is the disabled one; same visual check.
6. Hover or tap-and-hold a non-disabled step button: faint
   `rgba(128,128,128,0.1)` highlight appears, matching the existing
   `.menu-item:hover` feedback elsewhere in the menu.
7. Keyboard-focus a step button via Tab: a `#8ab` outline appears,
   matching the inputs below.
