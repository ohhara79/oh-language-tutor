# Fix `**bold**` markdown not rendering in panes

## Context

In both the left (explanation) and right (thread) panes, `**bold**` and `*italic*`
text sometimes shows raw asterisks instead of rendering as bold/italic. The root
cause is CommonMark's strict emphasis delimiter rules: a closing `**` preceded by
punctuation and followed by a word character (common in CJK text where no space
separates bold spans) is not recognised as a right-flanking delimiter.

## Changes

**File: `tutor/gui.py`**

### 1. Add `_CJKMarkdown` subclass of Rich's `Markdown`

- Pre-processes markup: regex converts `**text**` → `<strong>text</strong>` and
  `*text*` → `<em>text</em>` before markdown-it parses.
- Overrides `_flatten_tokens` to map resulting `html_inline` tokens for
  `<strong>`/`<em>` back to `strong_open`/`strong_close`/`em_open`/`em_close`
  that Rich knows how to style.

### 2. Update `_rich_md()` to return `_CJKMarkdown` instead of `RichMarkdown`

### 3. Render markdown during thread streaming (line 322)

Changed `self._streaming_label.update(self._streaming_text)` to use `_rich_md()`.

### 4. Add `markdown.strong` and `markdown.emph` to `_MD_THEME`

Pins bold/italic to `bold white` / `italic white` for visual consistency.

## Verification

Tested against all 95 stored entries (tutor.json + thread files) containing `**`
patterns — zero failures.
