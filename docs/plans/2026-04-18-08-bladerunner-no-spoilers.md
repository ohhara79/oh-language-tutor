# Blade Runner prompt — no spoilers guidance

## Problem

`extras/bladerunner.md` is the system-prompt extra used when the tutor
is running over Blade Runner (1997) dialog. It already tells the model
to favor noir / cyberpunk vocabulary and to reference the Blade Runner
universe.

Claude sometimes uses that latitude to explain a line by citing the
original novel or film, and in doing so leaks plot information the
player has not yet reached in the in-game story (replicant identities,
late-game reveals, branch-specific outcomes, etc.). The player is
experiencing the game in real time, so this is a spoiler.

## Goal

Keep the encouragement to reference the Blade Runner source material
for vocabulary and tone, but explicitly forbid revealing story beats
the player has not yet seen.

## Change

Append a `NO SPOILERS` section to `extras/bladerunner.md` after the
existing `FLAVOR` section. The new section states:

- film / novel / franchise references are welcome when they illuminate
  a word, idiom, or tone
- do not reveal plot points, twists, character identities, or outcomes
  the player has not yet reached
- specifically: replicant status, late-game allegiances / betrayals /
  deaths / endings, branch outcomes, Voight-Kampff results, hidden
  motives — all off-limits until the dialog itself exposes them
- when in doubt, treat the on-screen dialog as the only context the
  player has and explain from there

No code changes. No other prompt files touched.

## Out of scope

- Generalizing this to other sources in `extras/`. Each source has its
  own spoiler surface; handle per-file when it comes up.
- Retroactively editing earlier conversations or cached context.
