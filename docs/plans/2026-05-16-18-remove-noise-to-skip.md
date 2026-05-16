# Remove `NOISE TO SKIP` sections from prompt files

## Context

`extras/bladerunner.md` and `extras/sword1.md` are tutor prompt files. They
each currently contain a `NOISE TO SKIP:` block that tells Claude how to
identify and skip ScummVM/SDL/engine output lines that aren't game dialog.

That guidance is dead weight: the wrapper scripts already filter the
captured stream, so only real dialog lines reach Claude. Lines matching
those noise patterns are never delivered, so the instruction can never
fire. Removing the sections shortens the prompt and removes a misleading
contract.

## Changes

### `extras/bladerunner.md`
Delete lines 94–107 (the `NOISE TO SKIP:` block, including its trailing
blank line). The file should flow directly from the cast table (ending
`99 = VoiceOver`) to the `FLAVOR:` section, separated by a single blank
line.

### `extras/sword1.md`
Delete lines 41–55 (the `NOISE TO SKIP:` block, including its trailing
blank line). The file should flow directly from the unnamed-speaker
guidance (ending `…than from a wrong name`) to the `FLAVOR:` section,
separated by a single blank line.

No other content in either file changes.

## Verification

- `git diff extras/bladerunner.md extras/sword1.md` shows only the
  `NOISE TO SKIP` block removed in each file.
- `grep -n "NOISE TO SKIP" extras/*.md` returns no matches.
- Spot-read each file end-to-end to confirm the cast-table → FLAVOR
  transition reads naturally with exactly one blank line between them.
