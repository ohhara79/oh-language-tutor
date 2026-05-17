# Make audience settings dataset-scoped

## Context

The four settings exposed in the header hamburger menu —
**Learning** (source language), **Native** (target language), **Level**, and
**Show only explained** — are currently persisted as four flat `localStorage`
keys (`tutor.sourceLanguage`, `tutor.targetLanguage`, `tutor.level`,
`tutor.onlyExplained`) and shared across every dataset.

That doesn't match how users work: different datasets often want different
audience profiles (e.g. a Korean-learner watching English Friends wants
`Learning=English, Native=Korean`; the same user studying a Korean novel
wants `Learning=Korean, Native=English`). Toggling these every time you
switch datasets is friction. The "current sentence" (Jump slider) is already
per-dataset — it's derived from scroll position which is persisted in
`tutor.lastAnchors` keyed by dataset (see `tutor/static/app.js:319-353`).

This plan extends that same per-dataset pattern to the four audience
settings.

## Approach

Replace the four flat `localStorage` keys with a single nested object
`tutor.audienceByDataset`, mirroring the shape of the existing
`tutor.lastAnchors` map:

```js
// tutor.audienceByDataset
{
  "Friends - [1x01] - The One where Monica gets a Roommate": {
    sourceLanguage: "English",
    targetLanguage: "Korean",
    level: "intermediate",
    onlyExplained: "0"
  },
  "sword1": {
    sourceLanguage: "Korean",
    targetLanguage: "English",
    level: "advanced",
    onlyExplained: "1"
  }
}
```

Dataset identity reuses the same source as scroll persistence:
`document.querySelector('.view-dir-label')?.textContent.trim()`
(`tutor/static/app.js:324`).

**Read fallback** (smooth transition for existing users): when a setting is
not yet recorded for the current dataset, fall back to the legacy flat key
(`tutor.sourceLanguage` etc.), then to `CFG_DEFAULTS`. This means anyone
who already has settings configured today keeps them on first load of every
dataset; once they change a setting on a given dataset, that dataset gets
its own entry and subsequent reads skip the legacy fallback. We don't
delete the legacy keys — they decay naturally as people interact with each
dataset.

**Write**: always writes to `tutor.audienceByDataset[datasetName][key]`.
The four legacy keys become read-only (and read-only as a fallback,
not on the write path).

**Empty dataset name** (defensive — shouldn't happen in practice but the
scroll-persistence code already guards): treat as "no per-dataset entry"
and use the legacy/default fallback path on reads; skip writes silently,
matching the scroll-position code at `tutor/static/app.js:367`.

### Why one combined object instead of four parallel maps

Four parallel keys (`tutor.sourceLanguageByDataset`, etc.) would more
literally mirror `tutor.lastAnchors`, but the four audience settings are
conceptually one bundle ("who is this dataset for"). A single object also
keeps storage smaller and read/write paths simpler. The structural
precedent is the same — a single localStorage key holding a JSON object
keyed by dataset name.

## Files to touch

- `tutor/static/app.js` — replace `cfgStorageKey`/`cfgGet`/`cfgSet`
  (lines 28-35) and the `FILTER_KEY`-based read/write on lines 73, 100,
  103 with calls into the new per-dataset map. The `CFG_DEFAULTS`,
  `CFG_FIELDS`, `cfgHydrateMenu`, and the htmx `configRequest` injection
  (lines 60-68) keep their existing shape — they all flow through
  `cfgGet`/`cfgSet`, so only those two functions change.

No backend changes needed: `view_state_dir` cookie / dataset switching
already triggers a full page reload, so `datasetName` is naturally fresh
on each load.

## Verification

1. `make lint` passes.
2. Manual browser check:
   - Open dataset A, set Learning=English / Native=Korean / Level=intermediate
     / "Show only explained"=off.
   - Switch to dataset B (via the menu's "Switch dataset"). Confirm the
     same values appear (legacy fallback on first visit).
   - Change dataset B's settings: Learning=Korean, Native=English,
     Level=advanced, toggle "Show only explained" on.
   - Switch back to dataset A. Confirm A's original values are restored
     (English/Korean/intermediate/off).
   - Reload the browser on each dataset; values persist per-dataset.
   - Open devtools → Application → Local Storage. Confirm
     `tutor.audienceByDataset` contains both datasets as separate entries
     and the legacy keys are untouched (still hold the pre-change values).
3. Edge cases:
   - Open a brand-new dataset that's never been visited. Confirm it
     inherits the legacy global values on first view, then can be
     overridden independently.
   - With localStorage cleared, confirm `CFG_DEFAULTS`
     (English/Korean/intermediate/off) apply.
