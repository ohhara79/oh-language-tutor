# Mobile: Enter inserts newline instead of submitting

## Context

On mobile, the thread-compose textarea (`Ask a follow-up...`) cannot accept multi-line input. The on-screen keyboard's Enter/Return key submits the form because the current keydown handler treats plain Enter as submit on every device, and mobile keyboards don't expose a Shift modifier alongside Enter.

We want plain Enter on mobile to behave like Shift+Enter on desktop (insert a newline). The existing Send button stays as the only submit path on mobile. Desktop behavior is unchanged: Enter submits, Shift+Enter inserts a newline.

This matches the convention in Slack, WhatsApp, Discord, and Messages.

## Approach

Single-spot change in `tutor/static/app.js` in the existing keydown handler (lines 471–479). Detect a coarse primary pointer once at module load and, when matched, return early from the submit-on-Enter branch so the browser's default newline insertion runs instead.

Detection: `window.matchMedia('(pointer: coarse)').matches`. This matches touch-primary devices (phones, tablets) and does not misfire on touchscreen laptops where the primary pointer is a mouse/trackpad. No user-agent sniffing.

The check is evaluated each keydown rather than cached, so a tablet with an attached Bluetooth keyboard plus the on-screen keyboard collapsed still gets the right answer if the OS reports the primary pointer accurately. The cost is negligible.

IME-composition guard (`e.isComposing || e.keyCode === 229`) is preserved unchanged — important for Korean/Japanese input on both platforms.

## Files to change

- `tutor/static/app.js` — keydown handler at lines 471–479. Add one line before the `e.preventDefault()` that early-returns when `window.matchMedia('(pointer: coarse)').matches` is true. Update the comment above to mention the mobile carve-out.

No template, CSS, or Python changes. The Send button already exists at `tutor/templates/partials/thread_conversation.html:29-32` and remains the submit path on mobile.

## Sketch

```js
// Enter submits the compose form; Shift+Enter inserts a newline.
// On touch-primary devices (mobile/tablet) plain Enter inserts a newline
// instead — submit via the Send button. IME composition (e.g. Korean
// jamo -> hangul) must not trigger submit on any device.
document.body.addEventListener('keydown', (e) => {
    if (!(e.target instanceof HTMLTextAreaElement)) return;
    const form = e.target.closest('form.thread-compose');
    if (!form) return;
    if (e.key !== 'Enter' || e.shiftKey) return;
    if (e.isComposing || e.keyCode === 229) return;
    if (window.matchMedia('(pointer: coarse)').matches) return;
    e.preventDefault();
    form.requestSubmit();
});
```

## Verification

End-to-end manual test (both required):

1. **Desktop** (mouse/trackpad, fine pointer):
   - Open a thread, focus the follow-up textarea.
   - Press Enter → form submits, textarea clears.
   - Type some text, press Shift+Enter → newline inserted, no submit.
   - Korean IME: type 안녕 with jamo composition, press Enter to commit the composition → no submit; press Enter again on the committed text → submits.

2. **Mobile** (phone or Chrome DevTools device-emulation with touch enabled):
   - Open the same thread on a phone (or `Toggle device toolbar` → pick iPhone/Pixel in Chrome DevTools so `(pointer: coarse)` matches).
   - Focus the textarea, tap the on-screen Enter/Return key → newline inserted, form does NOT submit.
   - Tap the Send button → form submits, textarea clears.

3. **Lint:** `make lint` (no Python changes expected, but the project rule says to run it before declaring done).

No automated tests exist for this JS handler; the change is small enough that manual verification on both pointer classes is sufficient.
