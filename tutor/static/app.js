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
                populateLineThreads(line, c.anchorId);
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
            // Re-populate the active line's per-line thread sublist if we're
            // in line-detail view so SSE-driven updates are reflected.
            if (current().view === 'line') {
                const active = document.querySelector('.line.active');
                if (active) populateLineThreads(active, current().anchorId);
            }
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

    // Populate a line's per-line thread list by cloning matching items from
    // the global #thread-list. Keeps the UI reactive to SSE updates of the
    // global list without needing a new backend endpoint.
    function populateLineThreads(lineEl, anchorId) {
        const container = lineEl.querySelector('.line-threads');
        if (!container) return;
        container.innerHTML = '';
        const matches = document.querySelectorAll(
            `#thread-list .thread-item[data-anchor-id="${CSS.escape(anchorId)}"]`,
        );
        const heading = document.createElement('div');
        heading.className = 'line-threads-heading';
        heading.style.fontSize = '0.9rem';
        heading.style.color = '#888';
        heading.style.margin = '0.5rem 0 0.25rem';
        heading.textContent = `Threads (${matches.length})`;
        container.appendChild(heading);

        if (matches.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'empty';
            empty.textContent = 'No threads for this line yet.';
            container.appendChild(empty);
            return;
        }
        const ul = document.createElement('ul');
        ul.className = 'thread-list';
        matches.forEach((li) => { ul.appendChild(li.cloneNode(true)); });
        container.appendChild(ul);
        if (window.htmx) window.htmx.process(container);
    }

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
})();
