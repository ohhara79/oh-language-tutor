# Writing plan files

## Location

`docs/plans/`. Every plan file lives at the top level of this directory; do not nest subfolders.

## Naming

`YYYY-MM-DD-NN-slug.md`

- `YYYY-MM-DD` — the date the plan is written.
- `NN` — two-digit sequence for that day, **always present**, zero-padded, starts at `01`. Even the first plan of a day is `-01-`, not omitted.
- `slug` — short kebab-case description.

Example: `2026-04-18-01-add-web-mode.md`.

## One decision per file

Each plan covers one scoped change or decision. If scope grows, split into a follow-up plan rather than expanding an existing one. The filename ordering acts as the index — there is no TOC file.

## Structure

Lead with a **Context** section (why the change), then the approach, files to touch, and a verification section. Keep it scannable.
