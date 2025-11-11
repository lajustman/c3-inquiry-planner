document.addEventListener('DOMContentLoaded', () => {
  const gradeSelect = document.getElementById('mi-grade-select');
  if (!gradeSelect) {
    return;
  }

  const panels = document.querySelectorAll('.mi-grade-panel');
  const ensurePanel = (panelId) => {
    panels.forEach((panel) => {
      if (panel.dataset.gradePanel === panelId) {
        panel.classList.remove('hidden');
      } else {
        panel.classList.add('hidden');
      }
    });
  };

  ensurePanel(gradeSelect.value);
  gradeSelect.addEventListener('change', () => ensurePanel(gradeSelect.value));
});
