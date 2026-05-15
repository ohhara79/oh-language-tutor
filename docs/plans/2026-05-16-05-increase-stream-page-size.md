# Increase sentence stream page size 10x

## Context

`_STREAM_PAGE_N` in `tutor/web.py` governs both the initial sentence batch
rendered by `GET /` and the default batch served by the htmx "load older"
endpoint (`GET /partials/older`). At 50 it produced a sparse initial view
and required many scroll-triggered fetches to walk back through a long
transcript. Bumping it to 500 gives a denser first paint and far fewer
fetches when scrolling up, with no other changes needed.

## Approach

Single-constant edit. `_STREAM_PAGE_N` is the only source of truth — it
feeds both routes and is passed to the templates as `page_n`, which the
sentinel uses to build the next `/partials/older?...&n=...` URL. The
underlying `TutorStore.load_tail` / `load_before` already accept any `n`.

## Files touched

- `tutor/web.py` — `_STREAM_PAGE_N = 500` (was `50`).

## Verification

- `make lint` clean.
- Manual: open the web UI; initial sentence list renders up to 500 entries
  (or all available, whichever is smaller). Scroll to the top; the sentinel
  fires once and returns the next batch of up to 500.
