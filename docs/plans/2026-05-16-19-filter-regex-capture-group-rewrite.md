# Extend `--filter-regex` with implicit capture-group rewrite

## Context

Today `--filter-regex` only decides keep-vs-drop on each stdin line via
`filter_re.search(raw_line)` (`tutor/core.py:84`). When the matched line carries
boilerplate the user doesn't want stored — e.g. `1: aa bb` where only `aa bb`
is interesting — the user has no way to strip it: the entire raw line lands in
`tutor.json` and the web UI.

We extend the flag with a minimal, backwards-compatible affordance: if the
regex contains at least one capture group, the persisted line becomes
`match.group(1)`. Patterns without a group keep today's behavior bit-for-bit.

This avoids a new CLI flag and keeps the "single regex, single concern" feel
the user has built around (see `README.md:47`).

## Approach

Replace the one-line gate in `tutor/core.py` with a four-line block that
captures the match once and rewrites the line when group 1 is present.
Behavior:

1. Run `m = filter_re.search(raw_line)`. If no match, `continue` (today's
   drop behavior).
2. If the compiled pattern has groups (`filter_re.groups >= 1`) **and**
   `m.group(1) is not None`, use `m.group(1)` as the line to persist.
   Otherwise use `raw_line` unchanged.
3. `sink.on_raw_line(raw_line)` keeps logging the **original** stdin line
   to `tutor.log` (decision confirmed with user). Only the persisted
   `TutorEntry.raw` carries the rewritten text.
4. Apply the existing blank-line and duplicate checks to the rewritten
   value — a regex that strips to empty/whitespace drops via the blank
   check, and `last_kept` tracks the post-rewrite text so duplicates are
   detected after stripping.

Edge cases:
- **Multiple groups** — use group 1 only. Document briefly in `--help`.
- **Group 1 didn't participate** (alternation like `(foo)|bar`) —
  `m.group(1)` is `None`; fall back to `raw_line` rather than skip. This
  matches the principle that a successful overall match means "keep this
  line."
- **Group 1 is empty string** — distinct from `None`; that's a valid
  rewrite to "", which the existing blank-line guard then drops. No
  special handling needed.

## Files to modify

- `tutor/core.py` — replace `tutor/core.py:84` with the match/rewrite
  block described above. No signature changes; `stdin_loop` still takes a
  compiled `re.Pattern[str] | None`.
- `tutor/args.py:24-27` — extend the `--filter-regex` help text to mention
  that a capture group rewrites the line to its contents. Keep it one
  sentence.
- `README.md:70` — update the CLI-flags table row to mention the
  capture-group rewrite. One short clause appended.
- `tests/test_core.py` — add two new tests next to
  `test_stdin_loop_filter_regex_skips_non_matching` (`tests/test_core.py:70`):
  - capture-group rewrite: regex `r'^\d+:\s*(.+)$'` on `1: aa bb` →
    `sink.raws == ['1: aa bb']` (raw log untouched),
    `[e.raw for e in sink.appended] == ['aa bb']`.
  - non-participating group: regex `r'^(foo)|bar$'` on `bar` →
    appended line is `'bar'` (fallback to raw, not crash).

No new imports, no new CLI flag, no schema migrations. The pattern's
`.groups` attribute is already on the standard-library
`re.Pattern[str]` type so basedpyright is happy.

## Verification

End-to-end:

```sh
# Pre-existing behavior — no group, unchanged
printf '1: aa bb\nnope\n' \
  | uv run --frozen --no-dev main.py --filter-regex '^\d+: ' \
      --state-dir state/_verify
# expect: state/_verify/tutor.json entry with raw == '1: aa bb'

# New behavior — capture group rewrites
printf '1: aa bb\nnope\n' \
  | uv run --frozen --no-dev main.py --filter-regex '^\d+:\s*(.+)$' \
      --state-dir state/_verify2
# expect: state/_verify2/tutor.json entry with raw == 'aa bb'
# expect: state/_verify2/tutor.log still shows '1: aa bb' (unmodified)
```

Automated:

```sh
make lint        # basedpyright + ruff, project rule
uv run --frozen pytest tests/test_core.py -k filter_regex -q
```

Both new tests must pass; existing `test_stdin_loop_filter_regex_skips_non_matching`
must continue to pass unchanged.
