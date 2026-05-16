# Keep tapped sentence visible below the sticky header

## Context

In sentence-list view, tapping a `.raw-toggle` calls
`line.scrollIntoView({block: 'start', behavior: 'smooth'})`
(`tutor/static/app.js:221`), which aligns the `.line`'s top edge with the
viewport top. The header is `position: sticky; top: 0`
(`tutor/static/app.css:18-23`) and overlays that same edge, so the
just-scrolled-to sentence ends up hidden behind the header.

The hamburger "Jump to N" slider has the same issue — it also uses
`scrollIntoView({block: 'start'})` (`tutor/static/app.js:137`).

## Approach

Add `scroll-margin-top` to `.line`. CSS `scroll-margin-top` is specifically
designed for sticky-header offsets: when an element is targeted by
`scrollIntoView()` (or scroll-snap, or an anchor jump), the browser leaves
that much space above it. Both call sites benefit automatically — no JS
changes.

### Header height budget

The sticky header contains the menu button (`min-height: 36px`) plus
`0.75rem` padding top/bottom (~24px) plus a 1px border, totaling ~61px.
`scroll-margin-top: 4.5rem` (72px) covers the header with a small breathing
gap and stays robust if the header content shifts slightly.

## File to modify

- `tutor/static/app.css` — extend the existing `.line` rule (currently
  `app.css:147-150`) with one declaration:

  ```css
  .line {
      border-top: 1px solid #ddd;
      padding: 0.25rem 0;
      scroll-margin-top: 4.5rem;
  }
  ```

## Verification

1. `make lint` — unaffected; CSS only.
2. Open `/tutor` on a populated dataset. Tap a sentence near the bottom —
   it should scroll up and rest *below* the sticky header, fully visible.
3. Tap a sentence near the top — should still expand without odd jumps
   (browsers cap scroll at the natural bounds, so the margin only kicks in
   when there's room to scroll).
4. Open the hamburger menu and drag the "Jump to N" slider — the targeted
   sentence should also land below the sticky header.
5. Confirm dark mode still looks correct (scroll-margin doesn't affect
   layout, only scroll resting position, so no visual change expected).
