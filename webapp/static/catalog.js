(function () {
  const toggles = document.querySelectorAll('.catalog-accordion-toggle');
  toggles.forEach((toggle) => {
    const targetId = toggle.getAttribute('data-target');
    if (!targetId) return;
    const panel = document.getElementById(targetId);
    if (!panel) return;

    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      panel.hidden = expanded;
    });
  });
})();

(function () {
  const builderButtons = document.querySelectorAll('.catalog-select');
  if (!builderButtons.length) {
    return;
  }

  const overlay = document.getElementById('catalog-overlay');
  const statusEl = document.getElementById('catalog-overlay-status');
  const messageEl = document.getElementById('catalog-overlay-message');
  const openLink = document.getElementById('catalog-overlay-open');
  const closeBtn = document.getElementById('catalog-overlay-close');
  const currentSection = document.getElementById('current-selection');
  const currentCode = document.getElementById('current-selection-code');
  const currentMeta = document.getElementById('current-selection-meta');
  const currentSummary = document.getElementById('current-selection-summary');

  if (!overlay || !statusEl || !messageEl || !openLink || !closeBtn) {
    return;
  }

  const showOverlay = () => {
    overlay.hidden = false;
  };

  const hideOverlay = () => {
    overlay.hidden = true;
    overlay.dataset.state = '';
  };

  const setOverlayLoading = (title, message) => {
    overlay.dataset.state = 'loading';
    statusEl.textContent = title;
    messageEl.textContent = message;
    openLink.hidden = true;
  };

  const setOverlaySuccess = (payload) => {
    overlay.dataset.state = 'success';
    statusEl.textContent = 'Lesson ready!';
    messageEl.textContent =
      payload.message ||
      'Your AI lesson builder finished assembling resources. You can jump into the lesson now.';
    openLink.hidden = false;
    openLink.href = payload.redirect_url || '/overview';
  };

  const setOverlayError = (text) => {
    overlay.dataset.state = 'error';
    statusEl.textContent = 'Unable to build lesson';
    messageEl.textContent = text || 'Something went wrong. Please try again.';
    openLink.hidden = true;
  };

  closeBtn.addEventListener('click', () => {
    if (overlay.dataset.state === 'success') {
      hideOverlay();
      window.location.reload();
    } else {
      hideOverlay();
    }
  });

  builderButtons.forEach((button) => {
    button.addEventListener('click', async () => {
      const code = button.getAttribute('data-code');
      const label = button.getAttribute('data-label') || '';
      if (!code) {
        return;
      }

      showOverlay();
      const titleText = label ? `${code}: ${label}` : code;
      setOverlayLoading(
        'Building lesson…',
        `An AI agent is assembling activities and resources for ${titleText}.`
      );

      button.disabled = true;
      try {
        const response = await fetch('/api/build-lesson', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ expectation_code: code }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || 'The AI builder could not complete this request.');
        }
        setOverlaySuccess(payload);
        if (payload.selection && currentSection) {
          currentSection.hidden = false;
          if (currentCode) {
            currentCode.textContent = `${payload.selection.full_code} — ${payload.selection.label}`;
          }
         if (currentMeta) {
           currentMeta.textContent = `${payload.selection.unit_label} · ${payload.selection.discipline_label}`;
         }
         if (currentSummary) {
           const summaryText = payload.selection.lesson_summary || '';
           currentSummary.textContent = summaryText;
           currentSummary.hidden = summaryText.trim() === '';
         }
        }
        if (payload.question_seed && payload.question_seed.length) {
          const seedTarget = document.getElementById('question_seed');
          if (seedTarget) {
            seedTarget.value = payload.question_seed;
          }
        }
      } catch (error) {
        setOverlayError(error instanceof Error ? error.message : 'Unexpected error occurred.');
      } finally {
        button.disabled = false;
      }
    });
  });
})();
