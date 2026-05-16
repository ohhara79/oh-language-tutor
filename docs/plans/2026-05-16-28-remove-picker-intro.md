# Remove the picker page introductory paragraph

## Context

The picker page (`/`, rendered by `tutor/templates/picker.html`) showed an introductory paragraph above the dataset list:

> "Pick which tutor data to open. New stdin lines (if any) always write to `<writing_dir>`."

The user considered it redundant: the radio list and the per-item `writes here` badge already convey the same information. Removing the paragraph further tightens the picker view.

## Approach

Two deletions, no replacements:

1. **Template** (`tutor/templates/picker.html`) — deleted the `<p class="picker-sub">…</p>` line.
2. **CSS** (`tutor/static/app.css`) — deleted the now-dead `.picker-sub` and `.picker-sub code` rules.

Grep confirmed `.picker-sub` was referenced only at those three locations (the `.picker-submit` matches in the same files are a separate class).

The route handler at `tutor/web.py:343-353` still passes `writing_dir` to the template — used by the per-item `{% if name == writing_dir %}<span class="picker-badge">writes here</span>{% endif %}` badge in `tutor/templates/picker.html`.

## Files modified

- `tutor/templates/picker.html` — removed the intro `<p class="picker-sub">` line.
- `tutor/static/app.css` — removed the two `.picker-sub` rules.

## Verification

Manual:

1. `make lint` clean.
2. Open `/` (e.g. on mobile viewport): picker now shows only the `<h1>` title, the dataset list, and the "Open" button — no intro paragraph.
3. The dataset whose name matches `writing_dir` still has its `writes here` badge next to it in the list.
4. Pick a dataset → click "Open" → navigates to `/tutor` as before.
