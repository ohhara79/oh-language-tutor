# Stop CJK punctuation from forcing a horizontal scrollbar in the raw line list

## Context

Follow-up to `2026-05-23-18-raw-line-horizontal-scroll.md`. That change added
`box-sizing: border-box` to `.raw-toggle`, but a horizontal scrollbar remained,
and the user pinned it down: it appears on the **collapsed raw lines** in Desktop
Chrome and grows as the **font size** (`--content-scale`) is increased.

Reproducing against the live app with the real `ginga02` corpus (Japanese prose)
at 300% font showed **47 lines** overflowing the page by ~9px. Every offending
line ends in CJK closing punctuation — `」`, `？」`, `。`, `、`. This is **kinsoku**
line-breaking: such characters may not *start* a line, so the browser lets them
**hang past the line box**. The `.raw-toggle` button's `0.5rem` right padding
absorbs most of the hang, but ~9px escapes and widens the page; larger glyphs
(higher `--content-scale`) push more out.

This is not a text-wrapping problem. Measured in real Chrome, all of
`word-break: break-word` (current), `overflow-wrap: anywhere`,
`word-break: break-all`, and `line-break: anywhere` produced the **same** ~9px
overflow. Only clipping the horizontal overflow removed it. The scrollbar is
never wanted — raw lines should wrap and the stray punctuation hang is cosmetic.

## Change made

`tutor/static/app.css`, `.raw-toggle` rule: add `overflow-x: clip;` (with a
comment explaining the CJK-punctuation cause). Wrapping declarations are left
unchanged (`white-space: pre-wrap; word-break: break-word;`) since they were
shown not to affect this bug.

`clip` applies to the x-axis only; `overflow-y` stays `visible`, so vertical
scrolling and the sticky auto-hide header are unaffected. `.line-detail` (and the
`pre` code blocks inside expanded explanations, which keep their own
`overflow-x: auto`) is a **sibling** of `.raw-toggle`, not a child, so it is not
clipped.

## Critical files

- `tutor/static/app.css` — `.raw-toggle` rule (~line 245).

## Verification

Done with headless Chrome measuring `documentElement.scrollWidth - clientWidth`
against the live server, using the real persisted corpora:

- `overflowPx == 0` for `ginga02`, `marie`, `sword1`, `프렌즈.S01E01`,
  `老友记.S01E01`, and a Friends (English) episode at `--content-scale: 3`.
- `ginga02` (worst case) clean at scale 1, 1.5, 2, 3 and at window widths
  1400 / 600 / 500 px.
- `pre` blocks in expanded explanations still scroll horizontally on their own.
- `make lint` passes (CSS-only change; lint is Python-only).
