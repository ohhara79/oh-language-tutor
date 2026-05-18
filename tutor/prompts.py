"""System prompt builders for oh-language-tutor."""

from __future__ import annotations

from pathlib import Path

from tutor.types import LineRecord

# Linux execve() per-arg cap is PAGE_SIZE * 32 = 128 KiB on x86_64, and the
# SDK passes system_prompt as a single argv entry. Stay well under with a
# safety margin for SDK framing and multi-byte UTF-8.
MAX_SYSTEM_PROMPT_BYTES = 96 * 1024

# How many preceding raw lines accompany each Explain click as context.
EXPLAIN_CONTEXT_K = 100

LEVELS: frozenset[str] = frozenset({'beginner', 'intermediate', 'advanced'})


class PromptTooLargeError(ValueError):
    """Raised when the constructed system prompt exceeds the execve per-arg cap."""


def build_base_system_prompt(
    source_language: str,
    target_language: str,
    level: str,
) -> str:
    """Build the audience/format half of the system prompt."""
    return (
        f'You are a private language tutor helping a native {target_language} '
        f'speaker learn {source_language}. '
        f"The learner's level is {level}.\n"
        '\n'
        'Each user message contains a recent context window followed by a '
        'single target line, in the format described below. Produce a short '
        f'explanation of the target line tailored to a {level} '
        f'{source_language} learner whose native language is {target_language}.\n'
        '\n'
        'Explanation structure (skip any empty section, stay under 100 words; '
        'separate each section below with a blank line so each renders as its '
        'own paragraph):\n'
        '\n'
        f'  \U0001f3af Translation: <natural {target_language} translation>\n'
        '\n'
        '  \U0001f501 Variant:     <raw line rewritten in the script variant '
        'for the source language. For Chinese: the other script (simplified ↔ '
        'traditional) — ALWAYS include when the source is Chinese, even if '
        'most characters coincide. For Japanese: copy the kyūjitai (旧字体) '
        'rewrite from the GROUND TRUTH block below verbatim, resolving any '
        '[A|B|C] group by picking the one form whose meaning fits the line '
        'in context (no brackets, no pipes in the final output). When no '
        'GROUND TRUTH block is supplied, the source is Japanese but the line '
        'has no convertible kanji — omit the row. The "skip any empty '
        'section" rule does not apply to this row. Omit ONLY when neither '
        'condition holds.>\n'
        '\n'
        f'  \U0001f4da Vocabulary: <2-3 items, {source_language} word [pronunciation] → {target_language}>\n'
        '\n'
        '  \U0001f4a1 Expression: <one idiom/slang/grammar pattern, explained in '
        f'{target_language}>\n'
        '\n'
        '  \U0001f3ac Context:    <one sentence on what the speaker means in THIS '
        'moment, referencing the surrounding context lines>\n'
        '\n'
        'Pronunciation notation:\n'
        '- Always include an IPA transcription in square brackets, in addition\n'
        '  to any language-specific romanization or kana below.\n'
        '- For languages where spelling and sound diverge\n'
        '  (English, French, Russian, Arabic, Thai, …), IPA alone suffices,\n'
        '  e.g. accept [əkˈsɛpt] → 받아들이다.\n'  # noqa: RUF001 — U+02C8 is the IPA primary-stress mark
        '- For Japanese, show both forms separated by " / " (shinjitai first, '
        'kyūjitai second) when any kanji in the word has a kyūjitai variant '
        'per the GROUND TRUTH mappings below — those mappings are the source '
        'of truth, not your recall. Hiragana and IPA go in the same parens, '
        'comma-separated, e.g. 学校 / 學校 (がっこう, [ɡakkoː]) → 학교.\n'  # noqa: RUF001 — IPA script-g and length mark
        '  Drop the slash and second form when no kanji in the word has a '
        'kyūjitai variant per the GROUND TRUTH mappings, e.g. 受け入れる '
        '(うけいれる, [ɯke̞iɾe̞ɾɯ]) → 받아들이다.\n'  # noqa: RUF001
        '- For Mandarin Chinese, show both scripts separated by " / " '
        '(raw-script first), with pinyin and IPA in the same parens,\n'
        '  comma-separated, e.g. 学习 / 學習 (xuéxí, [ɕɥěɕǐ]) → 학습.\n'
        '  Drop the slash and second form when the two scripts are identical '
        'for that word, e.g. 你好 (nǐ hǎo, [ni˨˩˦ xɑʊ̯˨˩˦]) → 안녕하세요.\n'  # noqa: RUF001
        '- For source languages whose script is already phonetic\n'
        '  (Korean Hangul, Spanish, Italian, Indonesian, …), still include the IPA\n'
        '  in brackets, e.g. 안녕하세요 [annjʌŋɦasejo] → 안녕하세요.\n'
        '\n'
        'Level guidance:\n'
        f'- beginner:     write almost everything in {target_language}; simple '
        'vocabulary; explain even basic words.\n'
        f'- intermediate: bilingual, {target_language}-first; focus on idioms, '
        'slang, and cultural references.\n'
        f'- advanced:     explain in plain {source_language}; only use '
        f'{target_language} for subtle points.\n'
    )


def read_extras_system_prompt(path: str) -> str:
    """Read the optional `--extra-system-prompt` file at startup.

    Raises ``SystemExit`` on read errors — the path comes from a CLI flag,
    so a bad path is a launch-time configuration error.
    """
    p = Path(path).expanduser()
    try:
        return p.read_text(encoding='utf-8')
    except OSError as exc:
        msg = f'oh-language-tutor: cannot read --extra-system-prompt {p}: {exc}'
        raise SystemExit(msg) from exc


def _render_kyujitai_mappings(mappings: dict[str, list[str]]) -> str:
    """Render per-kanji kyūjitai mappings as indented prompt lines."""
    lines: list[str] = []
    for shinjitai, kyujitai_forms in mappings.items():
        if len(kyujitai_forms) == 1:
            lines.append(f'      {shinjitai} → {kyujitai_forms[0]}')
        else:
            joined = ' / '.join(kyujitai_forms)
            lines.append(f'      {shinjitai} → {joined}  (pick by meaning)')
    return '\n'.join(lines)


def build_system_prompt(
    source_language: str,
    target_language: str,
    level: str,
    extras_text: str | None = None,
    *,
    kyujitai_variant: str | None = None,
    kyujitai_mappings: dict[str, list[str]] | None = None,
) -> str:
    """Build the explain system prompt for one request.

    *kyujitai_variant*, when supplied, is the precomputed kyūjitai rewrite
    of the target line. *kyujitai_mappings*, when non-empty, is the
    per-kanji subset of the lookup table for the target line — it's
    consulted by the LLM when emitting dual-script Vocabulary items.
    Both are injected as bullets in a single GROUND TRUTH block so the
    Variant row and Vocabulary share the same source of truth.

    Raises :class:`PromptTooLargeError` if the result exceeds the SDK's
    execve per-arg cap.
    """
    result = build_base_system_prompt(source_language, target_language, level)
    if extras_text:
        result += '\n\nADDITIONAL SOURCE-SPECIFIC CONTEXT:\n\n' + extras_text
    if kyujitai_variant is not None or kyujitai_mappings:
        result += '\n\nGROUND TRUTH FOR THE TARGET LINE:\n'
    if kyujitai_variant is not None:
        result += (
            '- Kyūjitai (旧字体) rewrite of the target line:\n'
            f'    {kyujitai_variant}\n'
            '  Use this string in the \U0001f501 Variant row. Where you see '
            '"[A|B|C]", that position has multiple kyūjitai forms whose '
            'choice depends on meaning — pick exactly one form (no '
            'brackets, no pipes) using the meaning of the target line in '
            'context. Do not substitute or invent kanji forms outside what '
            'the brackets list. Where no brackets appear, copy the '
            'character verbatim.\n'
        )
    if kyujitai_mappings:
        result += (
            '- Per-kanji kyūjitai mappings for the target line — use these '
            'when emitting Vocabulary items containing any of these kanji, '
            'applying the same "[A|B|C] = pick by meaning" rule as the '
            'Variant row:\n'
            f'{_render_kyujitai_mappings(kyujitai_mappings)}\n'
        )
    size = len(result.encode('utf-8'))
    if size > MAX_SYSTEM_PROMPT_BYTES:
        msg = (
            f'system prompt is {size:,} bytes but the Linux execve '
            f'per-arg cap limits it to {MAX_SYSTEM_PROMPT_BYTES:,} bytes.'
        )
        raise PromptTooLargeError(msg)
    return result


def _render_thread_system_prompt(
    source_language: str,
    target_language: str,
    level: str,
    anchor: LineRecord,
    context_lines: list[LineRecord],
) -> str:
    """Render the thread system prompt without size-trimming."""
    context_block = '\n'.join(
        f'  {lr.raw}' + (f'\n  [explanation: {lr.explanation}]' if lr.explanation else '') for lr in context_lines
    )
    anchor_block = f'>>> {anchor.raw}'
    if anchor.explanation:
        anchor_block += f'\n{anchor.explanation}'

    return (
        f'You are a private language tutor helping a native {target_language} '
        f'speaker learn {source_language}. '
        f"The learner's level is {level}.\n"
        '\n'
        'The learner is asking follow-up questions about a specific line from '
        'a dialog stream they are watching. Answer their questions directly '
        'and concisely. This is a focused thread — they may ask follow-up '
        'questions, and you can build on what you have said earlier in this '
        'thread.\n'
        '\n'
        'You do NOT have access to the full prior conversation, only the '
        'recent dialog snippet below for context.\n'
        '\n'
        'Recent dialog (oldest first):\n'
        '---\n'
        f'{context_block}\n'
        '---\n'
        '\n'
        'ANCHOR LINE (the one the learner is asking about):\n'
        f'{anchor_block}\n'
        '---\n'
        '\n'
        "Now wait for the learner's question about the marked line.\n"
    )


def build_explain_user_message(target: str, context: list[str]) -> str:
    """Render the per-click Explain user message: context lines + target line."""
    if context:
        context_block = '\n'.join(f'> {line}' for line in context)
        return f'Recent context (oldest first):\n---\n{context_block}\n---\nExplain this line:\n{target}\n'
    return f'Explain this line:\n{target}\n'


def _truncate_to_utf8_bytes(text: str, limit: int) -> str:
    """Cut *text* to at most *limit* UTF-8 bytes on a codepoint boundary."""
    encoded = text.encode('utf-8')
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode('utf-8', errors='ignore') + '…'


def build_thread_system_prompt(
    source_language: str,
    target_language: str,
    level: str,
    anchor: LineRecord,
    context_lines: list[LineRecord],
) -> str:
    """Build a side-session system prompt, trimming to fit the argv cap.

    The SDK embeds the returned string directly into a single execve()
    argument (see ``_bundled/claude --system-prompt``), which Linux caps
    at 128 KiB per arg. Drop the oldest context entries first (most
    recent ones are most relevant) until the rendered prompt fits
    ``MAX_SYSTEM_PROMPT_BYTES``. If the anchor alone is still too large
    (very unusual — the explainer is word-capped), truncate its
    explanation rather than fail the open.
    """
    trimmed = list(context_lines)
    while True:
        prompt = _render_thread_system_prompt(
            source_language,
            target_language,
            level,
            anchor,
            trimmed,
        )
        if len(prompt.encode('utf-8')) <= MAX_SYSTEM_PROMPT_BYTES:
            return prompt
        if not trimmed:
            break
        trimmed.pop(0)

    short_anchor = LineRecord(
        idx=anchor.idx,
        raw=_truncate_to_utf8_bytes(anchor.raw, MAX_SYSTEM_PROMPT_BYTES // 4),
        explanation=(
            _truncate_to_utf8_bytes(anchor.explanation, MAX_SYSTEM_PROMPT_BYTES // 2) if anchor.explanation else None
        ),
    )
    return _render_thread_system_prompt(
        source_language,
        target_language,
        level,
        short_anchor,
        [],
    )
