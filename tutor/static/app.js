// Keep the stream pane scrolled to the bottom as new content arrives.
// Observe mutations instead of wiring per-swap handlers so it covers both
// SSE appends and HTMX swaps.
(function () {
    'use strict';

    function autoScroll(id) {
        const el = document.getElementById(id);
        if (!el) return;
        const observer = new MutationObserver(() => {
            el.scrollTop = el.scrollHeight;
        });
        observer.observe(el, { childList: true, subtree: true });
        el.scrollTop = el.scrollHeight;
    }

    document.addEventListener('DOMContentLoaded', () => {
        autoScroll('stream-pane');
        autoScroll('thread-conversation');
    });

    // When HTMX swaps the thread-conversation innerHTML, re-observe the new
    // thread-messages container so subsequent chunk appends keep scrolling.
    document.body.addEventListener('htmx:afterSwap', (evt) => {
        const convo = document.getElementById('thread-conversation');
        if (evt.target === convo) {
            convo.scrollTop = convo.scrollHeight;
        }
    });

    // Auto-dismiss toasts so they don't pile up if many arrive.
    document.body.addEventListener('htmx:oobAfterSwap', (evt) => {
        const t = evt.target;
        if (t && t.classList && t.classList.contains('toast')) {
            setTimeout(() => t.remove(), 5000);
        }
    });
})();
