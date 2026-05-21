# Reject explain requests when text language ≠ Learning Language

## Context

Users (Manu users especially) sometimes leave the **Learning Language** field
in the hamburger menu set to the wrong language (e.g. `English`) and then
paste in text in a different language (e.g. Japanese). The system happily
forwards both values into the system prompt:

> "You are a private language tutor helping a native Korean speaker
>  learn English."

…together with a Japanese line as the target. The model gets contradictory
instructions and produces a low-quality explanation. The user wants the
backend to detect this mismatch up front, show a clear error, and refuse
to start the explanation.

## Approach

Add a **script-based** mismatch check at the start of the
`/commands/explain` endpoint. We won't try to identify the exact language
(no `langdetect` dependency); we just check Unicode script coverage of
the target line and compare against the Learning Language using the
existing `is_japanese` / `is_chinese` / `is_korean` predicates.

This covers the high-impact failure mode the user described: CJK text
submitted under a non-CJK Learning Language (and vice versa). Latin-only
text under e.g. `English` vs `French` is *not* flagged — distinguishing
those reliably needs heavier machinery and was not the reported pain
point.

### Detection rules

Classify the target text into one bucket by scanning codepoints:

| Codepoint property                                      | Text bucket  |
| ------------------------------------------------------- | ------------ |
| Any Hangul (`U+1100..U+11FF`, `U+AC00..U+D7AF`)         | `korean`     |
| Any Hiragana/Katakana (`U+3040..U+30FF`, `U+31F0..U+31FF`) | `japanese`   |
| Any Han (`U+3400..U+9FFF`, `U+20000..U+2A6DF`) and none of the above | `han-only` (Chinese, but also matches Japanese kanji-only lines) |
| Any letter (`unicodedata.category` starts with `L`) and none of the above | `latin-or-other` |
| Otherwise (whitespace, digits, punctuation only)        | `unknown` — skip the check |

Classify the configured Learning Language with the existing predicates:

- `is_korean(L)` → expected `korean`
- `is_japanese(L)` → expected `japanese` **or** `han-only` (kanji-only
  sentences are rare but legal Japanese)
- `is_chinese(L)` → expected `han-only`
- Otherwise → expected `latin-or-other` (any non-CJK language)

Mismatch ⇒ block the explain. Skip the check when text bucket is
`unknown` (too little signal).

### Wiring

1. `tutor/languages.py` — add:
   - `text_has_hangul(text) -> bool`
   - `text_has_kana(text) -> bool`
   - `text_has_han(text) -> bool`
   - `text_has_letters(text) -> bool`
   - `detect_language_mismatch(learning_language: str, text: str) -> str | None`
     — returns a user-facing message (or `None` if OK / `unknown`).

2. `tutor/web.py:explain()` (around line 540, after `target = entries[idx]`
   and before kyujitai/prompt build):
   - Call `detect_language_mismatch(source_language, target.raw)`.
   - On mismatch: broadcast the message via `session.sink.on_error(msg)`
     so a toast appears (matches the failure path at
     `tutor/web.py:295-298`), then `raise HTTPException(status_code=400,
     detail=msg)` so HTMX does not swap and the line stays in its
     unexplained state. This mirrors the existing
     `_validate_audience` shape at `tutor/web.py:142-150`.

The error message should name both sides so the user can fix the
setting, e.g.:

> "Text appears to be Japanese, but Learning Language is set to
>  'English'. Update the Learning Language in the menu and try again."

### What is *not* changing

- No new runtime dependency.
- No client-side change. `tutor/static/app.js` already injects
  `source_language` from localStorage into every explain POST; the
  server-side error path is sufficient.
- The Ask/thread flow reuses the audience frozen on the entry at
  explain-time, so once an explain succeeds, no follow-up mismatch is
  possible. Validation lives only in `explain`.

## Files to touch

- `tutor/languages.py` — add script-detection helpers and
  `detect_language_mismatch`.
- `tutor/web.py` — invoke the check inside the `explain` route
  (`tutor/web.py:525-581`).
- `tests/test_languages.py` — cover each bucket: Hangul under English,
  kana under Korean, Han-only under Japanese (should pass), Han-only
  under English (mismatch), Latin under Japanese (mismatch), Latin
  under English (pass), punctuation-only (skipped), mixed-script lines.
- `tests/test_web.py` — add an integration test that posts to
  `/commands/explain` with a deliberate mismatch and asserts a 400 +
  the target line stays unexplained in `tutor.json`.

## Verification

1. `uv run --frozen pytest tests/test_languages.py tests/test_web.py`
2. `make lint`
3. Manual: start the web app, set Learning Language to `English`, paste
   a Japanese line, click Explain — expect a toast naming both
   languages, the line stays in its unexplained "Explain" button state,
   and no Claude call is made (check `state/tutor.log`).
4. Fix the Learning Language to `Japanese`, click Explain again —
   expect normal streamed explanation.
5. Repeat with Korean text under English-set, and Chinese text under
   English-set, to spot-check the other CJK buckets.
