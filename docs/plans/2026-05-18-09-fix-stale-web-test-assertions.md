# Fix stale `tests/test_web.py` assertions

## Context

`make test` fails with 3 errors, all in `tests/test_web.py`. The tests
have stale assertions that don't match the current code — UI/route
changes landed in recent commits without updating the test suite:

- `bdc3379` made `GET /` redirect to `/tutor` (303) when a valid
  `view_state_dir` cookie is present. The picker must now be reached via
  `/?picker=1`. See `tutor/web.py:349-360`.
- `4a55cf5` removed the "stdin lines stream into a different dataset"
  banner from `/tutor` when viewing a non-writing dir.
- `f3a740e` removed the "Switch dataset" menu entry; the header dataset
  name itself is now the link to the picker
  (`tutor/templates/index.html:14`).

The code is correct. Only the tests need to be updated.

## Approach

Test-only edits in `tests/test_web.py` — three small assertion changes:

### 1. `test_get_root_renders_picker_with_writing_badge` (line ~304)

Currently sends `GET /` with the writing-dir cookie and expects `200`.
With a cookie present the route now redirects unless `?picker=1` is
passed. Change the request to `GET /?picker=1`. The body assertions
(`'writing'`, `'other'`, `'writes here'`) still hold.

### 2. `test_get_tutor_renders_entries` (line ~397)

Replace `assert 'Switch dataset' in body` with
`assert 'href="/?picker=1"' in body`, which verifies the header title
links to the picker. The `'writing' in body` assertion already covers
that the current dataset name is rendered.

### 3. `test_get_tutor_marks_non_writing_view` (line ~410)

Replace `assert 'stdin lines stream into' in body` with
`assert '>other</a>' in body`, which verifies the non-writing view dir
name renders inside the `.view-dir-label` link in the header.

## Critical files

- `tests/test_web.py` — three small assertion edits.

No production source files change.

## Verification

1. `make test` — `201 passed`.
2. `make lint` — clean.
