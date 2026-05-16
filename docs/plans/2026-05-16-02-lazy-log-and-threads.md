# Make per-dir `tutor.log` + `threads/` creation lazy

## Context

After the picker change, `make_dir_session` eagerly materializes a
`DirSession` whenever a user picks a tutor-data directory. Two side
effects dirty the picked dir's filesystem even if the user only browses:

1. **`tutor.log`** — `_open_session_log()` in `tutor/web.py` opens the
   file in append mode and writes a `=== session start ... ===` banner
   immediately. The `open('a', ...)` call alone creates the file.
2. **`threads/`** — `sink.on_thread_list(pool.list_threads())` (the
   warm-up inside `make_dir_session`) chains through to
   `ThreadStore.list_threads()`, which calls `_ensure_dir()` before
   iterating — i.e. it `mkdir`s the directory just to ask whether any
   thread files exist.

`tutor.json` is already lazy (`TutorStore.load()` returns `[]` for a
missing file). The state dir itself is only `mkdir`ed for the writing
dir at startup — other dirs were real directories to appear in the
picker in the first place — so the dir-mkdir is already correct.

Intended outcome: picking a previously-untouched directory and just
browsing leaves it untouched on disk. Files only appear when something
is actually written — a thread opens, a follow-up sends, an
explanation runs, stdin streams a line in.

## Design

### `LazyLog` — defer the file open until the first write

Add a class in `tutor/web.py` that subclasses `io.TextIOBase`, wraps a
`pathlib.Path` + a header string, and only opens the file on the first
`write()`. The header is buffered as the first thing written to the
file so it lands together with the first real entry. `flush()` and
`close()` are no-ops when never opened, so shutdown can call them
unconditionally. An `opened` property lets the shutdown path skip the
`=== session end ===` banner — writing it unconditionally would
force-open the file and defeat laziness.

`@override` decorators on `write`/`flush`/`close` satisfy
basedpyright's `reportImplicitOverride` (we target 3.14).

Replace `_open_session_log()` with `_make_lazy_log()` that just
constructs a `LazyLog` — nothing else changes in `make_dir_session`.
`_close_session()` gains the `if session.log.opened` gate around the
end banner.

### `ThreadStore.list_threads()` — tolerate missing `threads/`

In `tutor/thread_store.py`, drop the `self._ensure_dir()` call from
`list_threads()` and short-circuit on `not self._dir.is_dir() → []`.
The same edit applies to `delete_by_anchor_id` (nothing to delete if
the dir doesn't exist). `_ensure_dir()` stays in `save_thread`, so
the directory still appears the first time a thread is actually
persisted.

### Type plumbing — new `LogSink` Protocol

`LazyLog` inherits from `io.TextIOBase`, which doesn't fully satisfy
`typing.TextIO` per basedpyright (lots of abstract methods we don't
implement). Rather than stub them, narrow what `WebSink`,
`FollowupThreadPool`, and `replay.notify_fallback` actually need.

Add `LogSink(Protocol)` in `tutor/types.py` with a single member:
`write(s: str, /) -> int`. Switch those three call sites'
`log: TextIO` annotation to `log: LogSink`. Both `LazyLog` (prod) and
`io.StringIO` (unit tests' `_sink`/`_pool` fixtures in
`test_web_sink.py` and `test_thread_pool.py`) satisfy the protocol
unchanged.

`DirSession.log` stays as the concrete `LazyLog` so `_close_session`
can read `.opened` without casts.

## Files to change

- `tutor/web.py` — `LazyLog` class (+`@override` decorators), replace
  `_open_session_log` with `_make_lazy_log`, change `DirSession.log`
  type to `LazyLog`, gate the end banner in `_close_session` on
  `session.log.opened`.
- `tutor/thread_store.py` — drop `_ensure_dir()` from `list_threads`
  and `delete_by_anchor_id`; return `[]` on missing dir.
- `tutor/types.py` — add `LogSink(Protocol)`.
- `tutor/web_sink.py`, `tutor/thread_pool.py`, `tutor/replay.py` —
  `log: TextIO` → `log: LogSink` (TYPE_CHECKING imports updated).
- `tests/test_web.py` — `_make_session` builds a real `LazyLog`
  backed by `state_dir / 'tutor.log'`. New `_read_log()` helper reads
  the on-disk file. Replace the two `cast('io.StringIO',
  ctx.writing_session.log).getvalue()` call sites. Drop the now-unused
  `io`/`cast` imports.
- `tests/test_web.py` — add `test_get_tutor_does_not_create_log_or_threads_dir`
  and `test_lazy_log_creates_file_on_first_write`.
- `tests/test_thread_store.py` — add `test_list_threads_missing_dir_returns_empty_without_creating`
  and `test_delete_by_anchor_id_missing_dir_returns_empty_without_creating`.

## Verification

End-to-end (manual):

1. `mkdir -p /tmp/oltest/{writing,empty1}` (two empty dirs).
2. `uv run --frozen main.py --state-dir /tmp/oltest/writing` (no
   stdin). Pick `empty1`, click around `/tutor`, quit.
3. `ls -la /tmp/oltest/empty1 /tmp/oltest/writing` — both directories
   are still completely empty (just `.` and `..`). No `tutor.log`,
   no `threads/`.
4. `echo 'a line' | uv run --frozen main.py --state-dir
   /tmp/oltest/with-stdin --web-port 18767` — `tutor.json` and
   `tutor.log` appear (log starts with the session banner + the
   piped raw line). `threads/` stays absent until a thread is
   actually opened.

Automated: `make lint` clean; 152 tests pass (4 new). The two
pre-existing `test_web_sink.py` failures are unrelated and remain.
