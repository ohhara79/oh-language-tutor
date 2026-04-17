// Three-view navigation controller: list / line-detail / thread-detail.
// The three views are gated by a body class; this module maintains a stack
// of {view, anchorId?} entries, syncs with browser history, and wires up
// tap handlers + HTMX afterSwap integration.
(function () {
    'use strict';

    const body = document.body;
    const stack = [{view: 'list'}];
    let ignoreNextPopState = false;

    function current() { return stack[stack.length - 1]; }

    function render() {
        const c = current();
        body.classList.remove('view-list', 'view-line', 'view-thread');
        body.classList.add(`view-${c.view}`);

        document.querySelectorAll('.line.active').forEach((el) => {
            el.classList.remove('active');
        });

        if (c.view === 'line') {
            const line = document.querySelector(`.line[data-anchor-id="${CSS.escape(c.anchorId)}"]`);
            if (line) {
                line.classList.add('active');
            }
            window.scrollTo(0, 0);
        } else if (c.view === 'thread') {
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

    // Tap a raw-line toggle in list view -> line-detail.
    document.getElementById('stream-pane').addEventListener('click', (e) => {
        if (current().view !== 'list') return;
        const toggle = e.target.closest('.raw-toggle');
        if (!toggle) return;
        const line = toggle.closest('.line');
        if (!line) return;
        const anchorId = line.dataset.anchorId;
        if (!anchorId) return;
        push('line', {anchorId});
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

        if (t.id === 'stream-pane') {
            // A new line appeared (explanation SSE); its empty .line-threads
            // may now match an existing orphan thread.
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
                    // Already in thread view (e.g. tapped a different thread in a
                    // per-line list from line-detail, but we never got there since
                    // tapping navigates from line to thread). Simply re-pin scroll.
                    t.scrollTop = t.scrollHeight;
                }
            } else if (current().view === 'thread') {
                // Thread was deleted while viewing it -> go back.
                history.back();
            }
        }
    });

    // Distribute threads from the hidden #thread-list source into per-line
    // .line-threads containers (by data-anchor-id) and push unmatched ones
    // into #orphan-threads. Called on load and after every thread_list /
    // stream-pane SSE swap.
    function distributeThreads() {
        const source = document.getElementById('thread-list');
        if (!source) return;
        const items = Array.from(source.querySelectorAll('.thread-item'));

        document.querySelectorAll('.line-threads').forEach((c) => {
            c.innerHTML = '';
        });

        const grouped = new Map();
        const orphans = [];
        for (const li of items) {
            const aid = li.dataset.anchorId || '';
            const line = aid
                ? document.querySelector(`.line[data-anchor-id="${CSS.escape(aid)}"]`)
                : null;
            if (line) {
                if (!grouped.has(aid)) grouped.set(aid, []);
                grouped.get(aid).push(li);
            } else {
                orphans.push(li);
            }
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

        const orphanContainer = document.getElementById('orphan-threads');
        if (orphanContainer) {
            orphanContainer.innerHTML = '';
            if (orphans.length > 0) {
                const ul = document.createElement('ul');
                ul.className = 'thread-list';
                orphans.forEach((li) => { ul.appendChild(li.cloneNode(true)); });
                orphanContainer.appendChild(ul);
                if (window.htmx) window.htmx.process(orphanContainer);
            }
        }
    }

    // Initial distribution after DOM parsed.
    distributeThreads();

    // Auto-scroll the page when new stream entries arrive in list view.
    new MutationObserver(() => {
        if (current().view === 'list') {
            window.scrollTo(0, document.body.scrollHeight);
        }
    }).observe(document.getElementById('stream-pane'), {childList: true, subtree: true});

    // Auto-scroll the conversation as messages stream in.
    new MutationObserver(() => {
        const c = document.getElementById('thread-conversation');
        if (c) c.scrollTop = c.scrollHeight;
    }).observe(document.getElementById('thread-conversation'), {childList: true, subtree: true});

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
        if (ta) ta.value = '';
    });
})();
