# Confine the "has-explanation" blue line to the raw-text row

## Context

In the raw-text list view, items that already have an explanation are marked by a blue vertical line on the left edge. Today that marker is rendered as a `border-left` on the wrapping `<section class="line has-explanation">`, so the blue line stretches the full height of the section — including the expanded explanation panel underneath. The user finds the blue line alongside the explanation body confusing: it should appear only against the raw-text row that owns the explanation, not against the explanation content itself.

## Approach

Move the blue `border-left` from the `.line.has-explanation` section to the inner `.raw-toggle` button (the element that renders the raw text). The wrapping section keeps its existing block-level styling; the marker now lives only on the raw-text row. The same move is done for the dark-mode color override.

The small left padding on the section (`padding-left: 0.5rem`) was there only to make room for the border. Removing both keeps things simple — the `.raw-toggle` already has its own `padding: 0.75rem 0.5rem`, so the raw text stays readable and the indented appearance of explained lines is preserved by the 3px border that now sits directly on the button. Lines without an explanation are unaffected.

## Files to change

- `tutor/static/app.css`

### Edit 1 — light mode (lines 167–170)

Replace:

```css
.line.has-explanation {
    border-left: 3px solid #0b6bcb;
    padding-left: 0.5rem;
}
```

with:

```css
.line.has-explanation .raw-toggle {
    border-left: 3px solid #0b6bcb;
}
```

### Edit 2 — dark mode (line 410)

Replace:

```css
.line.has-explanation { border-left-color: #9bf; }
```

with:

```css
.line.has-explanation .raw-toggle { border-left-color: #9bf; }
```

## Not changing

- `tutor/templates/partials/line.html` — the `has-explanation` class on `.line` is still useful as a hook, and the streaming branch (`{% if entry.explanation is not none or streaming %}`) also wants the marker on the raw row, which the new selector still covers.
- No JS changes; `app.js` doesn't read these classes for visual logic.

## Verification

1. Run the app: `uv run --frozen <whatever the start command is>` (per project convention) and open the dataset view.
2. Confirm:
   - A raw line **with** an explanation shows a blue vertical bar to the left of the raw text row only.
   - When that line is expanded, the explanation body underneath has **no** blue bar next to it.
   - A raw line **without** an explanation shows no blue bar (unchanged).
   - During an in-progress "Explain" stream, the streaming row shows the blue bar on the raw text only (the `streaming` branch still gets `has-explanation`).
3. Toggle OS dark mode and repeat — the bar should switch to the lighter `#9bf` color and still be confined to the raw row.
4. `make lint` to confirm nothing else regressed.
