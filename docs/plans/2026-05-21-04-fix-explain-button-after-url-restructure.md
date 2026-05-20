# Fix Explain button after URL restructure

## Context

Commit bc36ebd moved the Explain form action from `/commands/explain` to
`/tutor/{view_dir | urlencode}/commands/explain` (per-tab routing fix). The
`htmx:configRequest` listener in `tutor/static/app.js` that injects the
audience fields (`source_language`, `target_language`, `level`) into the
Explain POST was missed in that change. It still gates on
`path !== '/commands/explain'`, which never matches the new URL, so the
audience fields are silently dropped and the server returns 400 for the
missing required form fields. Result: Explain appears to do nothing.

## Change

`tutor/static/app.js:90-98` — update the path check to match the new
URL. Use the same `/tutor/<encoded-dir>/...` construction style already in
use for the `hide_thread` fetch at line 207, so both call sites read the
same.

```javascript
const explainPath = '/tutor/' + encodeURIComponent(datasetName) + '/commands/explain';
document.body.addEventListener('htmx:configRequest', (evt) => {
    const path = evt.detail && evt.detail.path;
    if (path !== explainPath) return;
    const params = evt.detail.parameters || {};
    for (const f of CFG_FIELDS) {
        params[f.form] = cfgGet(f.key);
    }
    evt.detail.parameters = params;
});
```

`datasetName` is the existing const at line 16 (now sourced from
`body.dataset.stateDir`), so no new wiring is needed.

## Files

- `tutor/static/app.js` — one path-check edit.

## Verification

1. `uv run --frozen pytest` — existing suite stays green (this is a JS-only
   change; server tests already cover the explain handler with the audience
   fields present).
2. `make lint` — clean.
3. Manual browser check:
   - Pick a dataset; click **Explain** on an unexplained line.
   - DevTools → Network → confirm the POST goes to
     `/tutor/<encoded-dir>/commands/explain` with form fields
     `entry_id`, `source_language`, `target_language`, `level`.
   - The line transitions to the `Explaining…` streaming variant and lands
     with an explanation. Confirm in a second tab on a *different* dataset
     that Explain there also works and writes to the other dir.
