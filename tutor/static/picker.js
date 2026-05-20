// Picker-page hamburger menu: just the Reset-settings escape hatch.
// Kept separate from app.js because app.js assumes the index view's DOM
// (stream pane, audience config, filter toggle, etc.) and would null-
// deref on this page.
(function () {
    'use strict';

    const menuBtn = document.getElementById('menu-btn');
    const menuPanel = document.getElementById('menu-panel');

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

    document.getElementById('reset-settings').addEventListener('click', () => {
        if (!confirm('Reset all settings? This clears audience choices and '
                + 'scroll position across all datasets.')) return;
        Object.keys(localStorage)
            .filter(k => k.startsWith('tutor.'))
            .forEach(k => localStorage.removeItem(k));
        location.reload();
    });
})();
