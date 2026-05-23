# Make state-dir picker open on click

## Context

The dataset picker (first screen) currently makes the user do two steps to
open a state dir: click a radio button to select the dir, then click an
**Open** button. The user finds the Open button redundant — clicking the dir
should be enough.

The redundancy is real in the code. `picker.html` renders a `<form>` of radio
buttons plus an **Open** submit button that POSTs to
`/commands/open_state_dir` (`tutor/web.py:352`). That handler only validates
the name and 303-redirects to `GET /tutor/{dir_name}` — a route that already
exists and is fully self-sufficient (`tutor/web.py:363`). So the radio +
button + POST round-trip lands exactly where a plain link would.

For a picker screen whose sole purpose is to enter one dataset,
single-click-to-open is the expected pattern and accidental-click risk is low.
Outcome: clicking a dir row navigates straight into it; no Open button.

## Approach

Turn each directory row into a direct link to `/tutor/{name}` and remove the
form, radios, Open button, and the now-dead POST handler.

### `tutor/templates/picker.html`

Replace the `<form>…</form>` block (lines 24-38) with a plain list of links.
Each row becomes an anchor to the GET route; keep the `writes here` badge.

```html
<ul class="picker-list">
  {% for name in dirs %}
  <li class="picker-item">
    <a class="picker-link" href="/tutor/{{ name | urlencode }}">
      <span class="picker-name">{{ name }}</span>
      {% if name == writing_dir %}<span class="picker-badge">writes here</span>{% endif %}
    </a>
  </li>
  {% endfor %}
</ul>
```

Notes:
- The `current_view` highlight / radio `checked` state goes away — picking is
  a one-shot action here, so a persistent selection has no meaning. `current_view`
  can be dropped from the template render call (`tutor/web.py:347`) if unused
  elsewhere.
- Confirm Jinja's `urlencode` filter matches the existing `quote(name, safe="")`
  encoding the POST handler used; both percent-encode path-unsafe chars. (The
  dir names are filesystem subdir names, so this mainly guards spaces/specials.)

### `tutor/web.py`

- Drop the `open_state_dir` POST handler (lines 352-361) — it becomes dead code.
- Remove the `current_view=` kwarg from the picker render (line 347) if the
  template no longer reads it.
- Check whether `Form` / `quote` imports become unused after removal and drop
  them if so (verify they aren't used by other routes first).

### `tutor/static/app.css`

Update picker styles (lines ~165-178): the `label`/radio rules
(`.picker-item label`, radio-specific styling) are replaced by a `.picker-link`
rule. Make `.picker-link` a block/flex element with `cursor: pointer`, padding,
and the existing gap between name and badge, so the whole row is a comfortable
tap target.

## Verification

1. `make lint` passes (basedpyright + formatting).
2. Run the app (`uv run --frozen` entrypoint) and open the picker at `/`:
   - Each dataset shows as a clickable row; clicking one navigates straight to
     `/tutor/<name>` and loads that dataset.
   - The `writes here` badge still appears on the writing dir.
   - Row is an easy tap target on a narrow (mobile) viewport.
3. Confirm `/commands/open_state_dir` is gone (404) and nothing else references
   it (grep templates/JS for `open_state_dir`).
4. Empty state still shows "No tutor data directories found." when there are no
   dirs.
