# oh-language-tutor

Pipe any text stream into Claude, get bite-sized bilingual
explanations out. Designed for language learners who want contextual
translation of whatever they happen to be reading — game dialog,
movie subtitles, chat logs, a book being read aloud, anything that
emits one line at a time to stdout.

The tool itself is source-agnostic. All audience knowledge (source
language, target language, level) is built in-process from CLI flags.
All source-specific knowledge (cast lists, log format, jargon) lives
in an optional `--extra-system-prompt` file. Claude sees the combined
prompt via a persistent session that remembers every prior line in
the stream, so explanations can reference earlier context naturally.

See `PLAN.md` in this directory for the full design spec.

## Setup

The project is a `uv` project on Python 3.14.

```sh
cd ~/work/oh-language-tutor
uv sync
```

You also need the `claude` CLI on your `$PATH` — the Claude Agent SDK
shells out to it. `which claude && claude --version` to check.

## Usage

### Minimal form (no source-specific context)

Explain any plain English text stream to a Korean intermediate
learner:

```sh
some_command_that_prints_english \
  | uv run main.py \
      --source-language English \
      --target-language Korean \
      --level intermediate
```

The tool passthrough-prints every input line to stdout, and for each
non-empty line it asks Claude for an explanation. If Claude decides
the line isn't real content worth explaining (e.g. log noise), it
emits the skip token and the tool suppresses the response.

### Blade Runner form (with extras file)

```sh
./scummvm 2>&1 \
  | uv run main.py \
      --source-language English \
      --target-language Korean \
      --level intermediate \
      --extra-system-prompt extras/bladerunner.md
```

The extras file supplies the Blade Runner cast table, log format,
noir-flavor hints, and a list of ScummVM log patterns to skip.

### Writing a new extras file

Copy `extras/bladerunner.md` and edit it. Keep source-specific
knowledge only — cast/speaker tables, format hints, flavor notes,
noise-skip hints. Do NOT include audience instructions, the
explanation template, or the skip-token rule — those come from the
base prompt built by the tool and will be injected automatically.

## CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--source-language` | _required_ | Language being learned, e.g. `English`. |
| `--target-language` | _required_ | Learner's native language, e.g. `Korean`. |
| `--level` | `intermediate` | `beginner` / `intermediate` / `advanced`. |
| `--extra-system-prompt` | _off_ | Path to a file whose contents are appended to the base prompt. |
| `--filter-regex` | _off_ | Only send lines matching this regex to the LLM. Saves cost on noisy sources. |
| `--skip-token` | `SKIP` | Sentinel word the LLM emits for non-content lines. |
| `--model` | `claude-opus-4-6` | Claude model id. Drop to Sonnet/Haiku to trade quality for speed/cost. |
| `--session-file` | `state/session.id` | Where the session id is persisted across runs. |
| `--log-file` | `state/tutor.log` | Append-only log of raw lines + explanations. |
| `--new-session` | _off_ | Ignore the saved session id and start fresh. |
| `--resume-id ID` | _off_ | Resume a specific session id (overrides `--session-file`). |

## Persistence

The first run creates `state/session.id` recording the session id.
Every subsequent run resumes that session so Claude remembers every
dialog line you've seen. `--new-session` wipes the link; `--resume-id`
resumes a specific older one.

`state/tutor.log` records the raw stream and every explanation in
chronological order, for later review.

Both `state/` files are `.gitignore`-d.

## Non-goals

- No in-source overlay. Explanations appear in the terminal only.
- No token streaming to terminal — responses are buffered to inspect
  the skip sentinel first. This adds ~1 s per explanation, fine for
  text rates around one line per few seconds.
- No per-source Python code. Anything domain-specific goes in an
  extras file.
