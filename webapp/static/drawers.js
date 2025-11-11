document.addEventListener('DOMContentLoaded', () => {
  function setupDrawer(toggleId, panelId, closeId) {
    const toggle = document.getElementById(toggleId);
    const panel = document.getElementById(panelId);
    const closeBtn = document.getElementById(closeId);
    if (!toggle || !panel) {
      return;
    }

    const openDrawer = () => {
      panel.setAttribute('aria-hidden', 'false');
      toggle.setAttribute('aria-expanded', 'true');
      panel.classList.add('open');
      toggle.classList.add('active');
    };

    const closeDrawer = () => {
      panel.setAttribute('aria-hidden', 'true');
      toggle.setAttribute('aria-expanded', 'false');
      panel.classList.remove('open');
      toggle.classList.remove('active');
    };

    toggle.addEventListener('click', () => {
      if (panel.classList.contains('open')) {
        closeDrawer();
      } else {
        openDrawer();
      }
    });

    closeBtn?.addEventListener('click', closeDrawer);
  }

  setupDrawer('vocab-toggle', 'vocab-drawer', 'close-vocab');
  setupDrawer('standards-toggle', 'standards-drawer', 'close-standards');
  setupDrawer('mi-standards-toggle', 'mi-standards-drawer', 'close-mi-standards');
});
