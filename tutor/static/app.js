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

    // Audience settings live in localStorage and surface as a single set
    // of controls inside the header hamburger menu (.menu-cfg). They are
    // global across all sentences; /commands/open_thread reads the audience
    // that was frozen on the entry at Explain time, so we only inject these
    // fields into /commands/explain.
    const CFG_DEFAULTS = {
        sourceLanguage: 'English',
        targetLanguage: 'Korean',
        level: 'intermediate',
    };
    const CFG_FIELDS = [
        {key: 'sourceLanguage', cls: 'cfg-source-language', form: 'source_language'},
        {key: 'targetLanguage', cls: 'cfg-target-language', form: 'target_language'},
        {key: 'level',          cls: 'cfg-level',           form: 'level'},
    ];
    function cfgStorageKey(key) { return 'tutor.' + key; }
    function cfgGet(key) {
        const raw = localStorage.getItem(cfgStorageKey(key));
        return raw !== null ? raw : CFG_DEFAULTS[key];
    }
    function cfgSet(key, value) {
        localStorage.setItem(cfgStorageKey(key), value);
    }
    const menuCfg = document.querySelector('.menu-cfg');
    function cfgHydrateMenu() {
        for (const f of CFG_FIELDS) {
            const el = menuCfg.querySelector('.' + f.cls);
            if (el) el.value = cfgGet(f.key);
        }
    }
    function cfgClassToKey(cls) {
        for (const f of CFG_FIELDS) {
            if (cls.contains(f.cls)) return f.key;
        }
        return null;
    }
    // <input> typing fires 'input'; <select> fires 'change'.
    function cfgOnFieldEvent(e) {
        const t = e.target;
        if (!t || !t.classList) return;
        const key = cfgClassToKey(t.classList);
        if (key !== null) cfgSet(key, t.value);
    }
    cfgHydrateMenu();
    menuCfg.addEventListener('input', cfgOnFieldEvent);
    menuCfg.addEventListener('change', cfgOnFieldEvent);

    document.body.addEventListener('htmx:configRequest', (evt) => {
        const path = evt.detail && evt.detail.path;
        if (path !== '/commands/explain') return;
        const params = evt.detail.parameters || {};
        for (const f of CFG_FIELDS) {
            params[f.form] = cfgGet(f.key);
        }
        evt.detail.parameters = params;
    });

    // Header menu: open/close + "show only explained" filter (persisted in
    // localStorage). The filter is a pure CSS body-class toggle; hidden lines
    // remain in the DOM and respect the same rule when appended via SSE.
    const FILTER_KEY = 'tutor.onlyExplained';
    const menuBtn = document.getElementById('menu-btn');
    const menuPanel = document.getElementById('menu-panel');
    const filterToggle = document.getElementById('filter-only-explained');

    function setMenuOpen(open) {
        menuBtn.setAttribute('aria-expanded', String(open));
        menuPanel.hidden = !open;
    }
    menuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        setMenuOpen(menuBtn.getAttribute('aria-expanded') !== 'true');
    });
    document.addEventListener('click', (e) => {
        if (!menuPanel.hidden && !menuPanel.contains(e.target) && e.target !== menuBtn) {
            setMenuOpen(false);
        }
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !menuPanel.hidden) setMenuOpen(false);
    });

    function applyFilter(on) {
        body.classList.toggle('filter-only-explained', on);
        filterToggle.checked = on;
    }
    applyFilter(localStorage.getItem(FILTER_KEY) === '1');
    filterToggle.addEventListener('change', () => {
        const on = filterToggle.checked;
        localStorage.setItem(FILTER_KEY, on ? '1' : '0');
        applyFilter(on);
    });

    // Hamburger "jump to Nth sentence" slider. Index is 1-based; #1 = oldest,
    // #N = newest (matches the rendered DOM order in #stream-pane).
    const jumpSlider = document.getElementById('jump-slider');
    const jumpCurrent = document.getElementById('jump-current');
    const jumpTotal = document.getElementById('jump-total');
    function jumpLines() {
        return document.getElementById('stream-pane').querySelectorAll('.line');
    }
    function jumpRefreshTotal() {
        const n = jumpLines().length;
        jumpTotal.textContent = String(n);
        jumpSlider.max = String(Math.max(n, 1));
        jumpSlider.disabled = n === 0;
        if (Number(jumpSlider.value) > n && n > 0) {
            jumpSlider.value = String(n);
            jumpCurrent.textContent = String(n);
        } else if (n === 0) {
            jumpCurrent.textContent = '0';
        }
    }
    function jumpScrollTo(index) {
        const lines = jumpLines();
        if (!lines.length) return;
        const i = Math.min(Math.max(index, 1), lines.length) - 1;
        lines[i].scrollIntoView({block: 'start'});
    }
    jumpSlider.addEventListener('input', () => {
        const v = Number(jumpSlider.value);
        jumpCurrent.textContent = String(v);
        jumpScrollTo(v);
    });

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

    // Tell the backend the user has navigated away from a thread so the
    // `claude` subprocess can be released (after any in-flight reply lands).
    // Fire-and-forget; double-calls are a safe no-op.
    function notifyHideThread(threadId) {
        if (!threadId) return;
        const fd = new FormData();
        fd.append('thread_id', threadId);
        fetch('/commands/hide_thread', {method: 'POST', body: fd, keepalive: true});
    }

    function push(view, params) {
        stack.push(Object.assign({view}, params || {}));
        history.pushState({depth: stack.length}, '');
        render();
    }

    function pop() {
        if (stack.length > 1) {
            const popped = stack.pop();
            if (popped.view === 'thread') notifyHideThread(popped.thread_id);
            render();
        }
    }

    window.addEventListener('popstate', () => {
        if (ignoreNextPopState) {
            ignoreNextPopState = false;
            return;
        }
        if (stack.length > 1) {
            const popped = stack.pop();
            if (popped.view === 'thread') notifyHideThread(popped.thread_id);
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
        if (!wasActive) {
            line.classList.add('active');
        }
        line.scrollIntoView({block: 'start', behavior: 'smooth'});
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
            // New line appeared via explanation SSE (beforeend). Newly-inserted
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
                const tid = t.querySelector('input[name="thread_id"]')?.value || '';
                if (current().view !== 'thread') {
                    push('thread', {thread_id: tid});
                } else {
                    // Already in thread view -> re-pin scroll to bottom.
                    current().thread_id = tid;
                    t.scrollTop = t.scrollHeight;
                }
                const ta = t.querySelector('form.thread-compose textarea[name="text"]');
                if (ta) ta.focus();
            } else if (current().view === 'thread') {
                // Thread was deleted while viewing it -> go back.
                // Don't fire hide on pop — delete already disconnected.
                current().thread_id = '';
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
            const heading = document.createElement('h3');
            heading.className = 'line-threads-heading';
            heading.textContent = 'Follow-ups';
            container.appendChild(heading);
            const ul = document.createElement('ul');
            ul.className = 'thread-list';
            list.forEach((li) => { ul.appendChild(li.cloneNode(true)); });
            container.appendChild(ul);
            if (window.htmx) window.htmx.process(container);
        }
    }

    // Initial distribution after DOM parsed.
    distributeThreads();

    // Scroll-position memory: persist the topmost visible line's anchor id
    // per dataset to localStorage so closing/reopening the browser lands
    // the user back where they were. Falls back to "scroll to newest"
    // (the previous default) when no saved anchor exists or the saved
    // line is no longer rendered (e.g. it was deleted).
    const datasetName = (document.querySelector('.view-dir-label')?.textContent || '').trim();
    function readLastAnchors() {
        try { return JSON.parse(localStorage.getItem('tutor.lastAnchors') || '{}'); }
        catch (e) { return {}; }
    }
    function writeLastAnchors(obj) {
        localStorage.setItem('tutor.lastAnchors', JSON.stringify(obj));
    }
    function topVisibleLineId() {
        for (const line of document.querySelectorAll('#stream-pane .line')) {
            if (line.getBoundingClientRect().bottom > 0) {
                return line.dataset.anchorId || '';
            }
        }
        return '';
    }

    let restoredScroll = false;
    const savedAnchor = datasetName ? readLastAnchors()[datasetName] : '';
    if (savedAnchor) {
        const el = document.querySelector(
            `.line[data-anchor-id="${CSS.escape(savedAnchor)}"]`);
        if (el) {
            el.scrollIntoView({block: 'start'});
            restoredScroll = true;
        }
    }
    if (!restoredScroll) {
        window.scrollTo(0, document.body.scrollHeight);
    }

    // Sticky-bottom auto-scroll: only follow new content if the user was
    // already at (or within NEAR_BOTTOM_PX of) the page bottom. Scrolling up
    // pauses auto-scroll; scrolling back to the bottom resumes it.
    const NEAR_BOTTOM_PX = 32;
    function isWindowAtBottom() {
        return window.innerHeight + window.scrollY >= document.body.scrollHeight - NEAR_BOTTOM_PX;
    }
    let wasAtBottom = true;
    let scrollSaveTimer = null;
    window.addEventListener('scroll', () => {
        wasAtBottom = isWindowAtBottom();
        if (current().view !== 'list') return;
        if (!datasetName) return;
        clearTimeout(scrollSaveTimer);
        scrollSaveTimer = setTimeout(() => {
            const aid = topVisibleLineId();
            if (!aid) return;
            const map = readLastAnchors();
            map[datasetName] = aid;
            writeLastAnchors(map);
        }, 200);
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

    // Keep the jump slider's total in sync with the current line count
    // (SSE appends new entries; tutor_entry_removed deletes them via OOB).
    jumpRefreshTotal();
    new MutationObserver(jumpRefreshTotal).observe(
        document.getElementById('stream-pane'), {childList: true});

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

    // When a Send starts, disable the textarea so pressing Enter during the
    // POST + SSE-streamed reply window can't bypass the disabled button via
    // form.requestSubmit().
    document.body.addEventListener('htmx:beforeRequest', (evt) => {
        const form = evt.target && evt.target.closest && evt.target.closest('form.thread-compose');
        if (!form) return;
        const ta = form.querySelector('textarea[name="text"]');
        if (ta) ta.disabled = true;
    });

    // After a Send, clear the textarea and keep both button + textarea disabled
    // until the assistant's streamed reply finishes (thread_done / error). On
    // failed POST, re-enable both.
    document.body.addEventListener('htmx:afterRequest', (evt) => {
        const form = evt.target && evt.target.closest && evt.target.closest('form.thread-compose');
        if (!form) return;
        const btn = form.querySelector('button');
        const ta = form.querySelector('textarea[name="text"]');
        if (!evt.detail || !evt.detail.successful) {
            if (btn) btn.disabled = false;
            if (ta) ta.disabled = false;
            return;
        }
        if (ta) ta.value = '';
        if (btn) btn.disabled = true;
    });

    // Re-enable the matching thread-compose form when its streamed reply
    // completes or errors. We match by thread_id parsed from the thread_done
    // payload's OOB selector (hx-swap-oob="outerHTML:#msg-stream-{thread_id}")
    // so cross-thread navigation doesn't accidentally re-enable an unrelated
    // form. Focus the textarea after re-enabling so the user can immediately
    // type the next message.
    document.body.addEventListener('htmx:sseBeforeMessage', (evt) => {
        const type = evt.detail && evt.detail.type;
        if (type !== 'thread_done' && type !== 'error') return;
        const data = (evt.detail && evt.detail.data) || '';
        const match = data.match(/#msg-stream-([^"\s]+)/);
        const inputs = match
            ? document.querySelectorAll(
                `form.thread-compose input[name="thread_id"][value="${CSS.escape(match[1])}"]`)
            : document.querySelectorAll('form.thread-compose input[name="thread_id"]');
        inputs.forEach((input) => {
            const form = input.closest('form');
            if (!form) return;
            const btn = form.querySelector('button');
            const ta = form.querySelector('textarea[name="text"]');
            if (btn) btn.disabled = false;
            if (ta) {
                ta.disabled = false;
                ta.focus();
            }
        });
    });
})();
