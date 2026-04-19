// Two-view navigation controller: list / thread-detail.
// The views are gated by a body class; this module maintains a stack of
// {view} entries, syncs with browser history, and wires up tap handlers +
// HTMX afterSwap integration. In list view, a raw-text tap toggles a
// `.line.active` class to inline-expand that line's explanation panel.
(function () {
    'use strict';

    const body = document.body;
    const stack = [{view: 'list'}];
    let ignoreNextPopState = false;

    function current() { return stack[stack.length - 1]; }

    function render() {
        const c = current();
        body.classList.remove('view-list', 'view-thread');
        body.classList.add(`view-${c.view}`);

        if (c.view === 'thread') {
            window.scrollTo(0, 0);
            const convo = document.getElementById('thread-conversation');
            convo.scrollTop = convo.scrollHeight;
        }
    }

    function push(view, params) {
        stack.push(Object.assign({view}, params || {}));
        history.pushState({depth: stack.length}, '');
        render();
    }

    function pop() {
        if (stack.length > 1) {
            stack.pop();
            render();
        }
    }

    window.addEventListener('popstate', () => {
        if (ignoreNextPopState) {
            ignoreNextPopState = false;
            return;
        }
        if (stack.length > 1) {
            stack.pop();
            render();
        }
    });

    // Back button: delegates to browser history so hardware Back and on-screen
    // Back share one code path (the popstate listener above).
    document.getElementById('back-btn').addEventListener('click', () => {
        history.back();
    });

    // Tap a raw-line toggle in list view -> inline-expand that line's detail.
    // Clicking a different line collapses the previous one; clicking the same
    // line again collapses it (toggle).
    document.getElementById('stream-pane').addEventListener('click', (e) => {
        if (current().view !== 'list') return;
        const toggle = e.target.closest('.raw-toggle');
        if (!toggle) return;
        const line = toggle.closest('.line');
        if (!line) return;
        const wasActive = line.classList.contains('active');
        document.querySelectorAll('.line.active').forEach((el) => {
            el.classList.remove('active');
        });
        if (!wasActive) line.classList.add('active');
    });

    // HTMX swap integration.
    document.body.addEventListener('htmx:afterSwap', (evt) => {
        const t = evt.target;
        if (!t || !t.id) return;

        if (t.id === 'thread-list') {
            // SSE replaced the hidden source; redistribute to lines + orphans.
            distributeThreads();
            return;
        }

        if (t.id === 'stream-pane' || t.id === 'load-older-sentinel') {
            // stream-pane: new line appeared via explanation SSE (beforeend).
            // load-older-sentinel: auto-load revealed older lines (outerHTML
            // swap of the sentinel itself). In both cases, newly-inserted
            // .line-threads containers may match existing thread items.
            distributeThreads();
            return;
        }

        if (t.id === 'thread-conversation') {
            // Swapped by tapping a thread, pressing Ask, or after a delete.
            // The delete endpoint returns <p class="empty">Thread deleted.</p>,
            // and the initial page load leaves the same empty-state element.
            // Use that marker to tell "real thread loaded" from "empty state".
            const isEmpty = !!t.querySelector('p.empty');
            if (!isEmpty) {
                if (current().view !== 'thread') {
                    push('thread');
                } else {
                    // Already in thread view -> re-pin scroll to bottom.
                    t.scrollTop = t.scrollHeight;
                }
                const ta = t.querySelector('form.thread-compose textarea[name="text"]');
                if (ta) ta.focus();
            } else if (current().view === 'thread') {
                // Thread was deleted while viewing it -> go back.
                history.back();
            }
        }
    });

    // Distribute threads from the hidden #thread-list source into per-line
    // .line-threads containers (by data-anchor-id). Threads whose anchor
    // line isn't currently in the DOM (older-not-yet-loaded) are dropped
    // from the view silently; they reappear once auto-load reveals the
    // anchor. Called on load and after every thread_list / stream-pane
    // SSE swap.
    function distributeThreads() {
        const source = document.getElementById('thread-list');
        if (!source) return;
        const items = Array.from(source.querySelectorAll('.thread-item'));

        document.querySelectorAll('.line-threads').forEach((c) => {
            c.innerHTML = '';
        });

        const grouped = new Map();
        for (const li of items) {
            const aid = li.dataset.anchorId || '';
            if (!aid) continue;
            const line = document.querySelector(`.line[data-anchor-id="${CSS.escape(aid)}"]`);
            if (!line) continue;
            if (!grouped.has(aid)) grouped.set(aid, []);
            grouped.get(aid).push(li);
        }

        for (const [aid, list] of grouped) {
            const line = document.querySelector(`.line[data-anchor-id="${CSS.escape(aid)}"]`);
            if (!line) continue;
            const container = line.querySelector('.line-threads');
            if (!container) continue;
            const ul = document.createElement('ul');
            ul.className = 'thread-list';
            list.forEach((li) => { ul.appendChild(li.cloneNode(true)); });
            container.appendChild(ul);
            if (window.htmx) window.htmx.process(container);
        }
    }

    // Initial distribution after DOM parsed.
    distributeThreads();

    // Sticky-bottom auto-scroll: only follow new content if the user was
    // already at (or within NEAR_BOTTOM_PX of) the page bottom. Scrolling up
    // pauses auto-scroll; scrolling back to the bottom resumes it.
    const NEAR_BOTTOM_PX = 32;
    function isWindowAtBottom() {
        return window.innerHeight + window.scrollY >= document.body.scrollHeight - NEAR_BOTTOM_PX;
    }
    let wasAtBottom = true;
    window.addEventListener('scroll', () => {
        wasAtBottom = isWindowAtBottom();
    }, {passive: true});
    document.addEventListener('DOMContentLoaded', () => {
        wasAtBottom = isWindowAtBottom();
    });

    new MutationObserver(() => {
        if (current().view !== 'list') return;
        if (!wasAtBottom) return;
        window.scrollTo(0, document.body.scrollHeight);
    }).observe(document.getElementById('stream-pane'), {childList: true, subtree: true});

    new MutationObserver(() => {
        if (current().view !== 'thread') return;
        if (!wasAtBottom) return;
        window.scrollTo(0, document.body.scrollHeight);
    }).observe(document.getElementById('thread-conversation'), {childList: true, subtree: true});

    // When the load-older sentinel fires, preserve the reader's content
    // position so the viewport doesn't jump to the newly-prepended older
    // content. This also pushes the replacement sentinel out of the viewport,
    // preventing an immediate re-fire cascade.
    let _loadOlderBefore = null;
    document.body.addEventListener('htmx:beforeRequest', (evt) => {
        const t = evt.target;
        if (!t || t.id !== 'load-older-sentinel') return;
        _loadOlderBefore = {
            scrollY: window.scrollY,
            height: document.documentElement.scrollHeight,
        };
    });
    document.body.addEventListener('htmx:afterSettle', () => {
        if (_loadOlderBefore === null) return;
        const delta = document.documentElement.scrollHeight - _loadOlderBefore.height;
        window.scrollTo(0, _loadOlderBefore.scrollY + delta);
        _loadOlderBefore = null;
    });

    // Auto-dismiss toasts so they don't pile up if many arrive.
    document.body.addEventListener('htmx:oobAfterSwap', (evt) => {
        const t = evt.target;
        if (t && t.classList && t.classList.contains('toast')) {
            setTimeout(() => t.remove(), 5000);
        }
    });

    // Enter submits the compose form; Shift+Enter inserts a newline.
    // IME composition (e.g. Korean jamo -> hangul) must not trigger submit.
    document.body.addEventListener('keydown', (e) => {
        if (!(e.target instanceof HTMLTextAreaElement)) return;
        const form = e.target.closest('form.thread-compose');
        if (!form) return;
        if (e.key !== 'Enter' || e.shiftKey) return;
        if (e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        form.requestSubmit();
    });

    // Clear the compose textarea after a successful send.
    document.body.addEventListener('htmx:afterRequest', (evt) => {
        const form = evt.target && evt.target.closest && evt.target.closest('form.thread-compose');
        if (!form) return;
        if (!evt.detail || !evt.detail.successful) return;
        const ta = form.querySelector('textarea[name="text"]');
        if (ta) {
            ta.value = '';
            ta.focus();
        }
    });
})();
