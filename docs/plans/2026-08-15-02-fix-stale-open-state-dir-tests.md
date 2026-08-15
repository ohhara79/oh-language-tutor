# Retire the stale `open_state_dir` tests

## Context

`uv run --frozen pytest` reported 4 failures, all in `tests/test_web.py` and all
the same shape: a `POST` to `/commands/open_state_dir` returned `404` instead of
the expected `303`/`400`.

- `test_post_open_state_dir_redirects_to_dir_path`
- `test_post_open_state_dir_supports_non_ascii_name`
- `test_post_open_state_dir_rejects_unknown_dir`
- `test_post_open_state_dir_rejects_traversal`

The tests were stale, not the code. `0bd4e69` ("Open state-dir picker rows on
click", planned in `2026-05-23-17-picker-open-on-click.md`) deliberately deleted
the `POST /commands/open_state_dir` handler and replaced the picker's radio
form with direct links to `GET /tutor/{name}`. That commit updated
`tutor/web.py`, `tutor/templates/picker.html` and `tutor/static/app.css` but
never touched the tests. `2026-08-15-01-update-agent-sdk-and-opus-5.md` then
recorded the 4 failures as pre-existing and out of scope.

Outcome: no failing tests, and the behavior that *replaced* the dead route is
covered instead.

## Approach

`tests/test_web.py` only — no production code changes.

- Section header `# -- picker / open_state_dir --` → `# -- picker --`.
- `test_post_open_state_dir_redirects_to_dir_path` →
  `test_get_root_renders_picker_rows_as_links`: asserts the picker renders each
  dir as an `href` to its `/tutor/{name}` URL.
- `test_post_open_state_dir_supports_non_ascii_name` →
  `test_picker_link_supports_non_ascii_name`: same CJK round-trip guard (a real
  past bug, `8234740`), retargeted from the POST `Location` header to the
  picker's `href`, still following the link to prove it resolves. Builds the
  expected URL with the existing `_dir_url` helper, which emits
  `quote(name, safe='')` — byte-identical to Jinja's `urlencode` filter for a
  basename, since both percent-encode everything but `/`.
- `test_post_open_state_dir_rejects_unknown_dir` — deleted; covered by
  `test_get_tutor_unknown_dir_redirects_to_picker`.
- `test_post_open_state_dir_rejects_traversal` — deleted; covered by
  `test_get_tutor_with_dot_prefix_dir_redirects` and
  `test_get_tutor_with_encoded_slash_dir_rejects`, which between them exercise
  both guards in `_resolve_view_session` that a `../../etc` payload would trip.

## Verification

- `uv run --frozen pytest --cov` — 273 passed, 0 failed (271 + 2). `tutor/web.py`
  coverage unchanged at 89%; the removed tests only covered a route that no
  longer exists.
- `make lint` — clean.
- `grep -rn open_state_dir tests/ tutor/` — no hits. Remaining mentions are in
  older `docs/plans/` files, which are records of past decisions and stay as-is.
