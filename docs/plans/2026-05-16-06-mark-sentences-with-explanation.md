# Mark sentences that have an explanation in the list view

## Context

In the stream pane, every sentence is rendered the same way regardless of
whether it has already been explained. The user has to tap a line open to find
out — and when scanning a long log (e.g. a full subtitle file) there is no way
to tell which lines have stored explanations and which are still untouched.

The underlying data already distinguishes the two states:
`TutorEntry.explanation` (`tutor/types.py:26-35`) is `None` until the user runs
Explain, after which it holds the rendered explanation text. The list response
and the SSE update path both carry this field unchanged, so this is purely a
template/CSS change.

The chosen indicator is a **thin colored left-border bar** along the line —
quiet, scans well, no extra horizontal space, no extra DOM nodes.

## Approach

Add a `has-explanation` modifier class to the existing `.line` section when
`entry.explanation` is not `None`, and style it with a left border in CSS.

### 1. `tutor/templates/partials/line.html` (line 1)

Append the modifier class onto the existing `<section class="line ...">` tag.
The template already branches on `entry.explanation is not none` for the
buttons, so the same condition reuses cleanly:

```jinja2
<section class="line{% if active %} active{% endif %}{% if entry.explanation is not none %} has-explanation{% endif %}"
         id="line-{{ entry.id }}" data-anchor-id="{{ entry.id }}">
```

The `entry_explained` SSE handler in `tutor/web_sink.py:84-96` re-renders the
whole section via OOB swap, so the class flips on automatically the moment an
explanation arrives. The initial page render in
`tutor/templates/index.html:32-36` uses the same partial, so historical lines
get the bar on load.

### 2. `tutor/static/app.css` (in the "Stream / raw lines" block, near line 34)

Add a left-border style for the new class. Reusing the existing `--btn-ask`
blue (`#0b6bcb` / `#9bf` in dark mode) keeps the palette consistent with the
Ask/Explain buttons that signal "explanation-related" state elsewhere:

```css
.line.has-explanation {
    border-left: 3px solid #0b6bcb;
    padding-left: 0.5rem;
}
```

And in the existing dark-mode block (`tutor/static/app.css:250-265`):

```css
.line.has-explanation { border-left-color: #9bf; }
```

The `padding-left` matches the bar width so the raw text doesn't shift when
the bar appears/disappears — without it, an unexplained line would sit 3px
further left than its explained neighbor.

### 3. `tutor/web_sink.py:91-95` — loosen the OOB-swap class match

The existing implementation injects `hx-swap-oob="outerHTML"` by a literal
string-replace that matches `<section class="line active" id="line-…"`. Once
the new `has-explanation` modifier is added the class attribute becomes
`line active has-explanation`, so the literal substring no longer appears and
the OOB swap silently breaks.

Loosen the replace to key on the unique `id="line-{entry.id}"` substring,
which is stable regardless of class composition:

```python
oob_fragment = fragment.replace(
    f'id="line-{entry.id}"',
    f'id="line-{entry.id}" hx-swap-oob="outerHTML"',
    1,
)
```

## Files to modify

- `tutor/templates/partials/line.html` — append `has-explanation` modifier
  class on the `<section>` tag.
- `tutor/static/app.css` — add `.line.has-explanation` rule near the `.line`
  block and a dark-mode override in the existing
  `@media (prefers-color-scheme: dark)` block.
- `tutor/web_sink.py` — relax the OOB-swap string-replace anchor so it does
  not depend on the exact class list.

## Verification

1. `make lint` — should be a no-op for this change but run it per project rules.
2. Start the dev server and open the app.
3. On a transcript with a mix of explained and unexplained lines (e.g.
   `state/bladerunner/tutor.json` has both), confirm explained lines show
   the left bar and unexplained lines do not.
4. Click Explain on an unexplained line and watch the bar appear without a
   full page reload (driven by the `entry_explained` OOB swap).
5. Toggle the OS into dark mode and confirm the bar uses the lighter blue
   variant.
6. Confirm text alignment: an explained line and an unexplained line stacked
   next to each other should have their raw text at the same x position (the
   `padding-left: 0.5rem` compensates for the 3px border).
