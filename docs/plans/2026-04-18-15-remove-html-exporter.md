# Remove HTML exporter (Ctrl+E)

## Context

The TUI has a Ctrl+E keybinding that renders the current session state
(`tutor.json` + `threads/*.json`) to a single self-contained HTML file via
`tutor/html_export.py`. It was built in April 2026
(`docs/plans/2026-04-14-03-gui-html-export.md`) as a way to view session
output offline from the Textual TUI.

The web UI (`tutor/web.py`, templates in `tutor/templates/`) has since
superseded this: it renders the same content live with a two-pane layout,
reuses the same stores, and has its own CSS. The static HTML export is now
redundant, so we are removing it.

## Scope of removal

All removal is local — no migration or data changes. Nothing on disk depends
on the exporter output; the emitted `tutor.html` is a one-way dump and users
who want one can still point a browser at the web UI and save the page.

## Files to delete

- `tutor/html_export.py` — the whole module (190 lines). Self-contained;
  nothing imports from it except `tutor/tui.py`.

## Files to modify

### `tutor/tui.py`

Three edits:

1. Remove the import `from tutor.html_export import export_to_html`.
2. Remove the keybinding tuple `('ctrl+e', 'export_html', 'Export HTML')`
   from `BINDINGS`. Textual drops the footer entry automatically.
3. Delete the `action_export_html` method.

No other TUI plumbing references the exporter — `_tutor_store`,
`_thread_store`, `_state_dir`, and `_status_bar` remain in use for other
features, so nothing else gets deleted.

## Files to keep as-is (important)

- `tutor/markdown_util.py` — `render_markdown` is shared with `tutor/web.py`,
  `tutor/web_sink.py`, and the Jinja templates. The exporter was one consumer
  of many; removing it does not make `markdown_util` dead code.
- `tutor/types.py::format_created_at_utc` — still used by the web UI.
- Tutor/thread stores — obviously kept.
- `README.md`, `Makefile`, `pyproject.toml`, `main.py`, `tutor/args.py`,
  `tutor/terminal.py` — none reference `html_export`; no edits needed.

## Docs

Historical plan files in `docs/plans/` that reference `html_export.py` are
point-in-time design records, not living docs. We do not rewrite old plans
to reflect later changes — they remain accurate as history.

## Verification

1. **Static checks**
   - `make lint` — runs ruff format, ruff check, basedpyright, xenon.
2. **TUI smoke test**
   - `uv run --frozen main.py --tui --source-language English --target-language Korean`
   - Footer no longer shows `^E Export HTML`.
   - Pressing Ctrl+E does nothing.
   - Escape-to-hide-thread and `q` to quit still work.
3. **Web UI smoke test**
   - `uv run --frozen main.py --web --source-language English --target-language Korean`
   - Still renders lines and threads — confirms shared `markdown_util`
     and store code paths are intact.
4. **Grep confirms no stragglers**
   - `rg 'html_export|action_export_html' tutor/ main.py` returns no matches.
