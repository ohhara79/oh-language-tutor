# oh-language-tutor

Pipe any text stream into Claude, get bite-sized bilingual
explanations out in a browser UI. Designed for language learners who
want contextual translation of whatever they happen to be reading —
game dialog, movie subtitles, chat logs, a book being read aloud,
anything that emits one line at a time to stdout.

The tool itself is source-agnostic. Audience settings (source
language, target language, level) live in the browser UI and persist
in `localStorage`, so they survive reloads and can be changed without
restarting the server. All source-specific knowledge (cast lists, log
format, jargon) lives in an optional `--extra-system-prompt` file
that is appended to every per-request system prompt.

## Setup

The project is a `uv` project on Python 3.14.

```sh
uv sync --frozen --no-dev
```

You also need the `claude` CLI on your `$PATH` — the Claude Agent SDK
shells out to it. `which claude && claude --version` to check.

## Usage

### Minimal form (no source-specific context)

```sh
some_command_that_prints_text | uv run --frozen --no-dev main.py
```

On start, the tool serves a browser UI at `http://127.0.0.1:8000`
(override with `--web-host` / `--web-port`). Set source language,
target language, and level in the header controls; values persist
across reloads via `localStorage`. Click Explain on any line to
stream a bilingual explanation from Claude.

### Blade Runner form (with extras file)

```sh
scummvm 2>&1 \
  | uv run --frozen --no-dev main.py \
      --extra-system-prompt extras/bladerunner.md \
      --filter-regex '^\w+: "'
```

The extras file supplies the Blade Runner cast table, log format,
noir-flavor hints, and a list of ScummVM log patterns to skip.

See [`docs/examples/bladerunner.md`](docs/examples/bladerunner.md) and
[`docs/examples/bladerunner.png`](docs/examples/bladerunner.png) for
example.

### Writing a new extras file

Copy `extras/bladerunner.md` and edit it. Keep source-specific
knowledge only — cast/speaker tables, format hints, flavor notes,
noise-skip hints. Do NOT include audience instructions, the
explanation template, or the skip-token rule — those come from the
base prompt built by the tool and will be injected automatically.

## CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--extra-system-prompt` | _off_ | Path to a file whose contents are appended to every per-request system prompt. |
| `--filter-regex` | _off_ | Only send lines matching this regex to the LLM. Saves cost on noisy sources. If the pattern has a capture group, group 1 replaces the sent line — e.g. `^\d+:\s*(.+)$` turns `1: aa bb` into `aa bb`. |
| `--explain-model` | `claude-opus-5` | Claude model id for streaming explanations. |
| `--ask-model` | `claude-opus-5` | Claude model id for ask-thread follow-ups. |
| `--state-dir` | `state/scratch` | Write target for stdin lines. The web picker lists sibling dirs of this path so you can pick which dataset to view. |
| `--web-host` | `127.0.0.1` | Bind address for the browser UI. |
| `--web-port` | `8000` | Port for the browser UI. |

Audience settings (source language, target language, level) are
chosen in the browser header and persisted in `localStorage`.

## Persistence

The first run creates `state/session.id` recording the session id.
Every subsequent run resumes that session so Claude remembers every
dialog line you've seen. `--new-session` wipes the link; `--resume-id`
resumes a specific older one.

`state/tutor.log` records the raw stream and every explanation in
chronological order, for later review. Followup threads live in
`state/threads/`.

The whole `state/` tree is `.gitignore`-d.

## Non-goals

- No in-source overlay. Explanations live in the browser UI.
- No per-source Python code. Anything domain-specific goes in an
  extras file.
