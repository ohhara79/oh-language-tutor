# Language tutor for any text stream via Claude Agent SDK

## Context

The user is a Korean native speaker learning English. Their first use
case is explaining the dialog of Blade Runner (ScummVM) as they play —
a debug hook in `engines/bladerunner/subtitles.cpp` already prints
every line to stdout, so piping that through a tutor script is the
obvious next step. But the tool shouldn't be tied to games at all.
The same "read a text stream, feed it to Claude, get back bite-sized
learner-friendly explanations" workflow is useful for:

- Game dialog (ScummVM, other engines).
- Movie/TV subtitles (from a live `.srt` tail or a player's debug hook).
- IRC/Slack/chat logs the user is trying to read along with.
- A book being read aloud that a tool transcribes line by line.
- Any other stream of lines the learner wants contextual translation
  for.

So the tool should be generic: one Python script, plus a small
**per-source system prompt file** that tells Claude everything
domain-specific. That system prompt is what tells Claude:

- What the source is and its setting (game, show, book, chat…).
- How to read the raw line format (e.g. `<speaker_id>: "<text>"`, or
  `[NPC] Name: text`, or whatever).
- The mapping from speaker ids to human-readable names, if any.
- What counts as noise vs. real content (so warnings, banners, or
  engine messages get filtered out).
- The target learner's native language and English level.
- The desired explanation format.

The Python script itself knows nothing about Blade Runner, speaker ids,
or noir slang. It is just a stdin pump, a persistent Claude session,
and a few CLI flags. All the domain knowledge lives in an optional
user-supplied extra system prompt file.

**System prompt in two layers.** The tool builds a **base system
prompt** from simple CLI flags:

- `--source-language` (the language the learner is reading/listening to)
- `--target-language` (the learner's native language)
- `--level` (beginner / intermediate / advanced)

That base prompt alone is enough for simple cases — e.g. "explain
English lines to a Korean intermediate learner, one at a time".
For anything that needs domain context (cast list, plot, log format,
jargon), the user also passes `--extra-system-prompt FILE`, whose
contents are appended to the base prompt. The base prompt handles
audience + format; the extra prompt handles source-specific knowledge.
Clean separation of concerns, and the simple path is one command with
three flags.

## Approach

One Python entry point (`main.py` in the existing
`~/work/oh-language-tutor/` uv project) plus one or more user-written
extra system prompt files. No changes to ScummVM — the debug hook in
`engines/bladerunner/subtitles.cpp` already emits dialog lines and
stays untouched.

### Tool: `main.py` in `~/work/oh-language-tutor/`

The user has already run `uv init` in `~/work/oh-language-tutor/`, so
the scaffolding exists:

```
~/work/oh-language-tutor/
├── .git/
├── .gitignore
├── .python-version         # 3.14
├── README.md               # empty, we fill it in
├── main.py                 # stub "Hello from oh-language-tutor!", we rewrite
└── pyproject.toml          # name=oh-language-tutor, deps=[]
```

We reuse `main.py` as the entry point — no new top-level script. All
CLI logic, base prompt building, stdin loop, and Claude session code
goes into `main.py`.

CLI:

```
uv run main.py --source-language NAME
               --target-language NAME
               [--level LEVEL]
               [--extra-system-prompt FILE]
               [--filter-regex REGEX]
               [--skip-token STR]
               [--model MODEL]
               [--session-file PATH]
               [--log-file PATH]
               [--new-session]
               [--resume-id ID]
```

- `--source-language` (required): full name of the language being
  learned, e.g. `English`, `Spanish`, `Japanese`. Passed verbatim into
  the base prompt so Claude refers to it naturally.
- `--target-language` (required): full name of the learner's native
  language, e.g. `Korean`, `French`. Same — used verbatim.
- `--level` (default `intermediate`): one of `beginner`, `intermediate`,
  `advanced`. Adjusts how much of the explanation is in the target
  language vs the source language, and how much jargon/idiom depth to
  include.
- `--extra-system-prompt` (optional): path to a Markdown/plain-text
  file whose contents are appended to the auto-generated base prompt.
  This is where source-specific knowledge goes — cast lists, plot
  context, log format, jargon tables, etc. Omit it entirely if the
  source needs no extra context.
- `--filter-regex` (optional): only lines matching this regex are sent
  to the LLM. Omitted → every stdin line is sent. Useful if a
  particular source's log is very noisy and you want to save cost by
  dropping obviously-not-content lines before they hit the API. Most
  sources won't need this.
- `--skip-token` (default `SKIP`): the sentinel word the LLM emits when
  a line is not dialog. See "LLM-side filtering" below. Allows the user
  to pick a different sentinel if `SKIP` could collide with something.
- `--model` (default `claude-opus-4-6`): model id passed through to
  the Agent SDK. Opus 4.6 gives the best cultural/idiom/noir
  explanations — at the cost of slightly higher latency and price per
  turn than Sonnet. For a text rate of one line every few seconds,
  Opus's latency is comfortably masked by normal gameplay pacing, and
  explanation quality is the whole point of the tool, so Opus is the
  right default. Swap to Sonnet 4.6 or Haiku 4.5 via this flag if you
  want cheaper/faster at the cost of depth.
- `--session-file` (default `~/work/oh-language-tutor/state/session.id`):
  where the session id for cross-run resumption is stored.
- `--log-file` (default `~/work/oh-language-tutor/state/tutor.log`):
  append-only log of raw input + explanations.

Both defaults live under a `state/` directory inside the project, which
we add to `.gitignore` so runtime artifacts don't end up in commits.
- `--new-session`: ignore any saved session id and start fresh.
- `--resume-id ID`: resume a specific session id (overrides the saved
  file).

### Core loop

1. Read stdin line-by-line.
2. **Passthrough**: write every raw line straight to stdout and to the
   log file, so the user's terminal still shows everything the source
   printed.
3. If `--filter-regex` is set and the line doesn't match, stop here
   for this line. Otherwise continue.
4. Dedup: skip lines identical to the previous sent line (cheap noise
   floor against repeated output).
5. Send the raw line as the next user turn on a persistent
   `ClaudeSDKClient` session. The session already holds every prior
   turn in this source stream (and across runs, if resuming), so
   Claude has full cumulative memory of what has been seen so far. No
   manual rolling window.
6. Buffer the streamed response until the assistant turn completes.
7. **LLM-side filtering**: if the buffered response, stripped and
   uppercased, equals the skip token (default `SKIP`), drop it — the
   line was not actually content worth explaining (e.g. an engine
   warning). Otherwise print the explanation to stdout with a visual
   separator, and append it to the log file.
8. Repeat until EOF, then close the session cleanly.

We buffer-then-print instead of streaming because short responses
(~100 tokens) only take ~1s and we need to inspect the first word to
decide whether to suppress. The trade-off is acceptable for this use
case. Streaming can be re-added later by watching the first few tokens
and deciding after the first whitespace.

### Claude Agent SDK usage pattern

Use **`ClaudeSDKClient`** as a persistent context manager. One client
instance = one continuous conversation covering the entire source
stream (and potentially across runs, via the resume mechanism).

```python
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, TextBlock,
)

options = ClaudeAgentOptions(
    system_prompt=system_prompt_text,       # base + optional --extra-system-prompt
    model=args.model,
    allowed_tools=[],                       # no tool use
    resume=load_saved_session(args),        # None on first run
)

async with ClaudeSDKClient(options=options) as client:
    save_session(client.session_id, args)   # persist for next launch

    async for raw_line in stdin_line_stream():
        passthrough(raw_line)
        if args.filter_regex and not args.filter_regex.search(raw_line):
            continue
        if raw_line == last_sent:
            continue
        last_sent = raw_line

        await client.query(raw_line)

        buf = []
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        buf.append(block.text)
        response = "".join(buf).strip()

        if response.upper() == args.skip_token.upper():
            continue
        print_block(response)
        log(response)
```

Key points:

- `client.query(msg)` submits one new user turn; history is preserved.
- `client.receive_response()` yields streaming chunks for that turn only.
- Prompt caching kicks in automatically inside the `claude` CLI backing
  the SDK, so per-turn cost stays roughly flat as the conversation
  grows.
- No tool use, keeping the agent loop single-shot.

### Base system prompt (generated by the tool)

Built in-process from the CLI flags. Rough template:

```
You are a private language tutor helping a native {target_language}
speaker learn {source_language}. The learner's level is {level}.

Each user message is ONE raw line of text from a stream that may or
may not contain actual {source_language} content worth explaining.
The stream may also include unrelated noise — engine warnings, log
banners, timestamps, debug prints — which should be ignored.

Decision rule:

- If the line is NOT real {source_language} content worth explaining
  (noise, metadata, technical output, unrelated output), respond with
  EXACTLY the single word `{skip_token}` and nothing else.
- Otherwise, produce a short explanation tailored to a {level}
  {source_language} learner whose native language is {target_language}.

Explanation structure (skip any empty section, stay under 100 words):

  🎯 Translation: <natural {target_language} translation>
  📚 Vocabulary: <2–3 items, {source_language} → {target_language}>
  💡 Expression: <one idiom/slang/grammar pattern, explained in
                  {target_language}>
  🎬 Context:     <one sentence on what the speaker means in THIS
                   moment, referencing earlier lines you've seen>

Level guidance:
- beginner:    write almost everything in {target_language}; simple
               vocabulary; explain even basic words.
- intermediate: bilingual, {target_language}-first; focus on idioms,
                slang, and cultural references.
- advanced:    explain in plain {source_language}; only use
               {target_language} for subtle points.

You have a persistent conversation history across every line sent
this session, so refer back to prior context naturally.
```

All the `{...}` fields are interpolated from CLI flags at startup.

### Extra system prompt (optional, user-provided)

Appended after the base prompt. This is where source-specific
knowledge lives — for example, for Blade Runner:

- Source description (Blade Runner 1997, noir, LA 2019).
- Raw line format: `<actor_id>: "<text>"`.
- Full cast table (all 73 actor ids).
- Any extra instructions about SKIP cases specific to ScummVM's log
  noise (e.g. "lines starting with `WARNING:` or `Subtitles font` are
  always noise").

For simple sources, no extra prompt file is needed — the base prompt
alone handles generic "any line of English → bilingual explanation".

### Session persistence across runs

Claude Code sessions have stable ids. `ClaudeAgentOptions` exposes a
`resume` field that maps to `claude --resume`. Plan:

- On first launch, `resume=None`. Read `client.session_id` after the
  context manager opens and write it to `--session-file`.
- On every subsequent launch, read that file and pass
  `resume=<id>` in options — same session, full memory of every
  prior run.
- `--new-session` ignores the saved id and starts fresh.
- `--resume-id <id>` resumes a specific older session id, overriding
  the saved file.

## Implementation order

Step 0 is fixed: before any code is written, copy this approved plan
into the project directory so it is git-tracked alongside the code.

1. **Write `~/work/oh-language-tutor/PLAN.md`** — copy the contents of
   `/home/ohhara/.claude/plans/distributed-petting-lobster.md`
   verbatim. This is the first concrete file action of the
   implementation, done before `uv add` or any edit to `main.py`, so
   the project repo always has the spec of record.
2. Environment setup (`uv add claude-agent-sdk`, `mkdir state extras`,
   `.gitignore` append).
3. Write `extras/bladerunner.md` (example extra prompt).
4. Rewrite `main.py` with the CLI, base-prompt builder, stdin loop,
   session management, passthrough/dedup/SKIP filtering, logging.
5. Rewrite `README.md` with usage examples.
6. Run the offline smoke test from the Verification section below.
7. Run the live Blade Runner test.

## Environment setup

The project is already `uv init`-ed. One-time setup steps:

```
cd ~/work/oh-language-tutor
uv add claude-agent-sdk                # installs into .venv, updates pyproject.toml + uv.lock
mkdir -p state extras
echo "state/" >> .gitignore            # runtime artifacts: session.id, tutor.log
```

After that, `uv run main.py ...` invokes the tutor with the right
environment. No global `pip install` needed.

The `claude` CLI that `claude-agent-sdk` shells out to must already be
on `$PATH` — the user has Claude Code installed, so this is a
one-line check, not a setup step.

## Files to create or modify

- **`~/work/oh-language-tutor/PLAN.md`** (new): verbatim copy of the
  approved plan file
  (`/home/ohhara/.claude/plans/distributed-petting-lobster.md`),
  written as the very first implementation step so the project repo
  has the spec of record before any code change.
- **`~/work/oh-language-tutor/main.py`** (rewrite): replace the stub
  with the CLI, base-prompt builder, stdin loop, session management,
  passthrough + dedup + LLM-side SKIP filtering, and logging. ~250
  lines.
- **`~/work/oh-language-tutor/pyproject.toml`** (touched by
  `uv add`): gains `claude-agent-sdk` in `dependencies`. No manual
  edit required.
- **`~/work/oh-language-tutor/.gitignore`** (append): add `state/`.
- **`~/work/oh-language-tutor/extras/bladerunner.md`** (new): example
  extra system prompt for the user's current Blade Runner setup.
  Contains ONLY source-specific knowledge (no audience/level/format —
  those come from the base prompt):
  - Source description (Blade Runner 1997, noir, LA 2019).
  - Raw line format (`<actor_id>: "<text>"`).
  - Full Blade Runner cast table (all 73 actor ids from
    `engines/bladerunner/game_constants.h` lines 26–101), e.g.
    `0=McCoy, 1=Steele, 2=Gordo, ..., 99=VoiceOver`.
  - Game-specific SKIP hints (e.g. lines starting with `WARNING:`,
    `STARTUP.MIX`, `Using pixel format`, `Subtitles font` are noise).
  - Blade Runner noir / cyberpunk vocabulary flavor notes.
- **`~/work/oh-language-tutor/README.md`** (rewrite): usage note
  showing (a) the zero-config form for a random English text stream,
  (b) the Blade Runner form with an extra prompt file, and (c) how to
  write a new extras file for another source (movie subtitles, chat
  log, book, etc.).
- **`~/work/oh-language-tutor/state/`** (new dir): empty, created
  automatically at first run if missing.

No changes to the ScummVM source. The C++ debug hook is already in
place and is game-engine agnostic from the tool's point of view — the
tool just reads stdout.

## Run command

Minimal form (no source-specific context — works for any plain
English stream):

```
some_source_of_english_text \
  | (cd ~/work/oh-language-tutor && uv run main.py \
      --source-language English \
      --target-language Korean \
      --level intermediate)
```

Blade Runner form (adds the extras file):

```
./scummvm 2>&1 \
  | (cd ~/work/oh-language-tutor && uv run main.py \
      --source-language English \
      --target-language Korean \
      --level intermediate \
      --extra-system-prompt extras/bladerunner.md)
```

The `cd` subshell is there so `uv run` finds `pyproject.toml` and the
project's `.venv`. An alternative is `uv run --project
~/work/oh-language-tutor main.py ...` from any directory, which
avoids the subshell.

Other sources are piped the same way, e.g. `tail -F subs.srt`,
`cat chat.log`, or `ffmpeg -i movie.mkv -map 0:s:0 -f srt -` piped
into the same command with (or without) a matching extras file.

Notes on the ScummVM invocation:

- `2>&1` merges ScummVM's warnings into the same stream so they also
  reach the tool. The LLM will emit the skip token for them.
- Single terminal, single consumer. The tutor passthrough-prints the
  raw lines AND its own explanations to the same stdout, so the user
  sees everything interleaved in one place.

## Example extras file

`~/work/oh-language-tutor/extras/bladerunner.md` — appended after the
base prompt. Contains only the Blade Runner-specific bits; audience
and format come from the base prompt built from the CLI flags.

```
SOURCE: "Blade Runner" (1997 Westwood adventure game, running under
ScummVM). Noir detective story set in Los Angeles, November 2019.
McCoy is a Blade Runner investigating Replicants.

RAW LINE FORMAT: dialog lines on stdin look like

    <actor_id>: "<text>"

where <actor_id> is an integer. Map it to a character name using this
table when you reference the speaker:

    0=McCoy, 1=Steele, 2=Gordo, 3=Dektora, 4=Guzza, 5=Clovis,
    6=Lucy, 7=Izo, 8=Sadik, 9=Crazylegs, 10=Luther, 11=Grigorian,
    ... [full list of 73 actors] ..., 99=VoiceOver

NOISE TO SKIP: lines that are clearly ScummVM or engine output —
`WARNING:`, `STARTUP.MIX:`, `Using pixel format`, `Subtitles font`,
`SliceAnimations`, etc. — are not dialog. Respond with the skip
token for them.

FLAVOR: this is a noir / cyberpunk source. Favor explanations of
detective slang, 1940s-style idioms, and cyberpunk vocabulary
(replicants, off-world colonies, blade runners, etc.) when they
appear.
```

No Korean-specific text, no format template, no level instructions —
all of that came from the base prompt via `--source-language English
--target-language Korean --level intermediate`. This file is swappable
for any other game or source.

## Verification

1. `cd ~/work/oh-language-tutor && uv add claude-agent-sdk && uv sync`;
   confirm `uv run python -c "import claude_agent_sdk"` works and
   the `claude` CLI is on `$PATH`.
2. **Offline smoke test**: feed a fixture file containing a mix of
   dialog lines and warning lines to `uv run main.py` with the
   Blade Runner extras. Expected: every line passes through to stdout;
   warning lines produce no explanation; dialog lines produce an
   explanation block.
3. **Live Blade Runner test**: run the real pipeline, walk McCoy into
   the Grigorian interrogation scene. Verify raw dialog and
   explanations appear interleaved in one terminal; explanations
   reference earlier lines ("he" → "Grigorian", "the Asian fellow" →
   "Izo"); `--session-file` gets created; engine warnings passthrough
   but produce no explanations.
4. **Cross-run session persistence**: quit, re-run. Play a later scene
   that mentions a character from an earlier scene. Claude should still
   remember. Also test `--new-session` — it should wipe the link.
5. **Zero-config test**: run with only the three language flags
   (`--source-language English --target-language Korean --level
   intermediate`) and feed a fixture of plain English sentences.
   Confirm the base prompt alone produces reasonable explanations.
6. **Generic-tool test**: write a trivial second extras file that
   targets a different source type (e.g. a movie-subtitle explainer
   for "Casablanca" with an `[HH:MM:SS] CHARACTER: text` format).
   Feed it a synthetic fixture. Confirm the same Python script works
   with zero code changes and uses the new extras file's format hints
   on top of the same base prompt.
7. **Level test**: run the same fixture at `--level beginner` and
   `--level advanced` and confirm the explanation language balance
   actually shifts.
8. **Non-TTY test**: `./scummvm 2>&1 | (cd ~/work/oh-language-tutor &&
   uv run main.py ...) | cat`. ANSI escape codes in the explanation
   separators should be suppressed.

## Non-goals

- KIA / dialogue menu / in-game UI text in Blade Runner — not hooked
  in C++, not parsed here.
- No in-source overlay (e.g. no in-game text overlay, no subtitle
  compositing). Explanations appear inline in the terminal only.
- No per-source Python code. All domain-specific logic lives in the
  system prompt file. If a future source needs structurally different
  behavior (different output format, different sentinel, etc.),
  that's adjusted in the prompt file, not the script.
- No token streaming to terminal. We buffer each response to inspect
  the skip sentinel. This adds ~1s per line latency, acceptable for
  a text rate of one line every few seconds. Streaming can be
  retrofitted later.
- No automatic cost/rate tracking. Typical line rates stay well within
  normal API limits for Opus 4.6 with session-level prompt caching,
  and the user can always drop to Sonnet/Haiku via `--model`.
