document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('vocab-toggle');
  const drawer = document.getElementById('vocab-drawer');
  const closeBtn = document.getElementById('close-vocab');

  if (!toggle || !drawer) {
    return;
  }

  const openDrawer = () => {
    drawer.setAttribute('aria-hidden', 'false');
    toggle.setAttribute('aria-expanded', 'true');
    drawer.classList.add('open');
    toggle.classList.add('open');
  };

  const closeDrawer = () => {
    drawer.setAttribute('aria-hidden', 'true');
    toggle.setAttribute('aria-expanded', 'false');
    drawer.classList.remove('open');
    toggle.classList.remove('open');
  };

  toggle.addEventListener('click', () => {
    if (drawer.classList.contains('open')) {
      closeDrawer();
    } else {
      openDrawer();
    }
  });

  closeBtn?.addEventListener('click', closeDrawer);
});
