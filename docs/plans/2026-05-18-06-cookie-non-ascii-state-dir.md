# Fix `UnicodeEncodeError` when state-dir name has non-ASCII chars

## Context

Running `./scripts/ass.sh ./老友记.S01E01.ass 2` triggers a 500 on `POST /commands/open_state_dir`. Starlette's `Response.set_cookie` encodes the whole `Set-Cookie` header as latin-1 (per RFC 6265), but the cookie value here is the state-dir basename, which can legitimately contain Chinese (or any non-ASCII) characters — `老友记.S01E01` cannot be latin-1 encoded, so the request blows up before redirecting to `/tutor`.

Goal: let users open and view state dirs whose names contain non-ASCII characters, without changing the cookie contract for ASCII names.

## Approach

Percent-encode the cookie value when writing, percent-decode when reading. ASCII names round-trip unchanged (e.g. `quote('other', safe='') == 'other'`), so existing behavior and tests are preserved; non-ASCII names survive transport as e.g. `%E8%80%81%E5%8F%8B%E8%AE%B0...`.

Path-traversal checks must run on the *decoded* value, so an attacker can't smuggle `/` as `%2F` past the existing guards.

### Changes — `tutor/web.py`

1. Add `from urllib.parse import quote, unquote` to the imports.

2. Add a small helper near `VIEW_COOKIE` (line 56):

   ```python
   def _read_view_cookie(request: Request) -> str | None:
       raw = request.cookies.get(VIEW_COOKIE)
       return unquote(raw) if raw else None
   ```

   (Single-purpose helper — no `_write_view_cookie` since the write happens at exactly one site and reads `quote(...)` inline is clearer than another wrapper.)

3. `_resolve_view_session` (line 253): replace `cookie_val = request.cookies.get(VIEW_COOKIE)` with `cookie_val = _read_view_cookie(request)`. The existing `/`, `\`, leading-`.` checks already operate on the right value once it's decoded.

4. `picker` route (line 347): replace `request.cookies.get(VIEW_COOKIE)` with `_read_view_cookie(request)`. The decoded basename is what the template wants to compare against `dirs`.

5. `open_state_dir` route (line 366): pass `quote(dir_name, safe='')` instead of `dir_name`. `safe=''` is deliberate — we don't want `/` to slip through as itself, since we percent-decode on read and any literal `/` in the cookie would defeat the traversal check.

### Changes — `tests/test_web.py`

6. In `_client` (line 296): wrap the cookie write as `cookies[VIEW_COOKIE] = quote(name, safe='')` so test setup matches the new contract. Add `from urllib.parse import quote` at the top.

7. Add one regression test next to `test_post_open_state_dir_sets_cookie_and_redirects` (line 326) using a non-ASCII dir name (e.g. `老友记`), asserting:
   - status 303 and `location: /tutor`
   - the `Set-Cookie` value is percent-encoded (`r.cookies.get(VIEW_COOKIE)` will be the encoded form — check via the raw header or by hitting a follow-up endpoint that re-reads the cookie)
   - a subsequent `GET /tutor` with that cookie resolves to the right `view_dir`

   Prefer the round-trip assertion (post then get) — it pins the contract end-to-end and avoids over-specifying the wire format.

## Critical files

- `tutor/web.py` — lines 56, 253, 347, 364–370
- `tests/test_web.py` — line 296, plus new test after line 333

## Verification

- `make lint` and `make format` clean.
- `uv run --frozen pytest tests/test_web.py -k cookie` passes (existing ASCII tests stay green).
- New non-ASCII regression test passes.
- Manual: `./scripts/ass.sh ./老友记.S01E01.ass 2`, open `http://127.0.0.1:8000/`, select the Chinese-named dir from the picker — it should redirect to `/tutor` and load the entries instead of 500'ing. Reload the browser; the cookie should still resolve to the same dir.
