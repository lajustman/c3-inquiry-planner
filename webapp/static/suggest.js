document.addEventListener('DOMContentLoaded', () => {
  const suggestBtn = document.getElementById('suggest-question');
  const addSuggestedBtn = document.getElementById('add-suggested');
  const suggestedWrapper = document.getElementById('suggested-question');
  const suggestedText = document.getElementById('suggested-text');
  const textarea = document.getElementById('student_questions');
  const suggestContainer = document.getElementById('suggest-container');
  const suggestedActions = document.getElementById('suggested-actions');
  const seedInput = document.getElementById('question_seed');
  let buttonInPanel = false;

  if (!suggestBtn || !suggestedWrapper || !suggestContainer || !suggestedActions) {
    return;
  }

  const moveButtonToPanel = () => {
    if (buttonInPanel) {
      return;
    }
    suggestedActions.prepend(suggestBtn);
    suggestContainer.hidden = true;
    suggestBtn.textContent = 'Suggest another question';
    buttonInPanel = true;
  };

  const moveButtonToContainer = () => {
    if (!buttonInPanel) {
      return;
    }
    suggestContainer.hidden = false;
    suggestContainer.appendChild(suggestBtn);
    suggestBtn.textContent = 'Suggest a question';
    buttonInPanel = false;
  };

  suggestBtn.addEventListener('click', async () => {
    suggestBtn.disabled = true;
    moveButtonToPanel();
    suggestedWrapper.hidden = false;
    suggestedText.textContent = 'Generating...';
    addSuggestedBtn.style.display = 'none';
    suggestBtn.textContent = 'Generating...';
    try {
      const response = await fetch('/api/suggest-question', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({ prompt: '' }),
      });
      const data = await response.json();
      if (data.error) {
        suggestedText.textContent = data.error;
        addSuggestedBtn.style.display = 'none';
      } else {
        suggestedText.textContent = data.question;
        addSuggestedBtn.style.display = 'inline-block';
      }
    } catch (error) {
      suggestedText.textContent = 'Unable to generate a question right now.';
      addSuggestedBtn.style.display = 'none';
    } finally {
      suggestBtn.disabled = false;
      suggestBtn.textContent = buttonInPanel ? 'Suggest another question' : 'Suggest a question';
    }
  });

  addSuggestedBtn?.addEventListener('click', () => {
    const question = suggestedText.textContent.trim();
    if (!question) {
      return;
    }
    const current = textarea.value ? `${textarea.value.trim()}\n${question}` : question;
    textarea.value = current;
    suggestedWrapper.hidden = true;
    moveButtonToContainer();
    if (seedInput) {
      seedInput.value = '';
    }
  });

  showSeedIfAvailable();
});
  const showSeedIfAvailable = () => {
    if (!seedInput || !seedInput.value.trim()) {
      return;
    }
    moveButtonToPanel();
    suggestedWrapper.hidden = false;
    suggestedText.textContent = seedInput.value.trim();
    addSuggestedBtn.style.display = 'inline-block';
  };
