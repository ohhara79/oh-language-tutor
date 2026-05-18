# Separate Explain sections with blank lines in the prompt template

## Context

The per-line **Explain** output is supposed to render as five distinct
paragraphs:

```
🎯 Translation: …
🔁 Variant:     …   (Chinese-only; mandatory)
📚 Vocabulary: …
💡 Expression: …
🎬 Context:    …
```

In practice they often fuse into one run-on paragraph. The
"Explanation structure" template in `tutor/prompts.py:40-52` lists section
labels with only single `\n`s and no instruction about blank lines, so the
model mirrors that spacing. Python-markdown
(`tutor/markdown_util.py:38-41`) needs a blank line between block-level
elements; without one, consecutive label lines collapse into a single
`<p>` and the browser flattens the interior newlines to spaces.

`tutor/markdown_util.py:25-35` already injects a blank line before a list
marker, but does nothing for adjacent bare label lines (e.g.
`🎯 Translation: …` followed by `💡 Expression: …` with no list in
between) — which is exactly the case being hit. Fix is prompt-only;
`markdown_util.py` is unchanged.

## Approach

Prompt-only change in `build_base_system_prompt`:

1. Put a blank line between every section in the template so the model
   sees and mirrors the spacing.
2. Add an explicit instruction in the structure header line stating that
   each section must be separated by a blank line so it renders as its
   own paragraph.
3. Preserve the load-bearing invariants from commit `3054dc5`: the
   `ALWAYS include this row when the source is Chinese` wording, the
   absence of the `script-identical` carve-out, the `skip any empty
   section` rule, and the under-100-words budget.

## Exact edit

`tutor/prompts.py`, replace lines 40–52:

```python
        'Explanation structure (skip any empty section, stay under 100 words):\n'
        '\n'
        f'  \U0001f3af Translation: <natural {target_language} translation>\n'
        '  \U0001f501 Variant:     <raw line rewritten in the other Chinese '
        'script — simplified ↔ traditional. ALWAYS include this row when the '
        'source is Chinese, even if most characters coincide across scripts; '
        'the "skip any empty section" rule does not apply here. Omit ONLY '
        'when the source is not Chinese.>\n'
        f'  \U0001f4da Vocabulary: <2-3 items, {source_language} word [pronunciation] → {target_language}>\n'
        '  \U0001f4a1 Expression: <one idiom/slang/grammar pattern, explained in '
        f'{target_language}>\n'
        '  \U0001f3ac Context:    <one sentence on what the speaker means in THIS '
        'moment, referencing the surrounding context lines>\n'
```

with:

```python
        'Explanation structure (skip any empty section, stay under 100 words; '
        'separate each section below with a blank line so each renders as its '
        'own paragraph):\n'
        '\n'
        f'  \U0001f3af Translation: <natural {target_language} translation>\n'
        '\n'
        '  \U0001f501 Variant:     <raw line rewritten in the other Chinese '
        'script — simplified ↔ traditional. ALWAYS include this row when the '
        'source is Chinese, even if most characters coincide across scripts; '
        'the "skip any empty section" rule does not apply here. Omit ONLY '
        'when the source is not Chinese.>\n'
        '\n'
        f'  \U0001f4da Vocabulary: <2-3 items, {source_language} word [pronunciation] → {target_language}>\n'
        '\n'
        '  \U0001f4a1 Expression: <one idiom/slang/grammar pattern, explained in '
        f'{target_language}>\n'
        '\n'
        '  \U0001f3ac Context:    <one sentence on what the speaker means in THIS '
        'moment, referencing the surrounding context lines>\n'
```

The existing blank line that follows (before `Pronunciation notation:`)
stays unchanged. The four added blank lines add < 10 bytes to the prompt;
the per-arg cap budget is unaffected.

## Critical files

- `tutor/prompts.py:40-52` — the only code change.
- `tests/test_prompts.py` — add
  `test_build_base_system_prompt_separates_sections_with_blank_lines` that
  asserts each non-leading section label is preceded by `\n\n`, so a
  future edit cannot silently collapse the template back to single
  newlines.

## Verification

1. `uv run --frozen pytest tests/test_prompts.py -q` — all tests pass.
2. `make lint` — clean.
3. Manual smoke test:
   - Launch the app, open any dataset.
   - Click **Explain** on several lines (at least one Chinese line so the
     Variant row appears, and one non-Chinese line so it doesn't).
   - In DevTools, confirm that each section renders as its own `<p>` —
     not as a single run-on `<p>` with interior spaces.
   - Sanity: vocabulary list items still render as a `<ul>` (the
     existing `_insert_blank_before_lists` continues to work).
