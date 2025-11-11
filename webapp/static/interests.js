document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('interest-form');
  const suggestBtn = document.getElementById('interest-suggest');
  const aiContainer = document.getElementById('ai-suggestions');
  const status = document.getElementById('ai-status');
  const topicsInput = document.getElementById('interest-topics');
  const saveBtn = document.getElementById('interest-save');
  const requirementsHint = document.getElementById('interest-requirements');

  if (!form) {
    return;
  }

  const requiredSections = {
    interest_modes: form.querySelector('[data-required-section="interest_modes"]'),
    topics: form.querySelector('[data-required-section="topics"]'),
    learning_mode: form.querySelector('[data-required-section="learning_mode"]'),
    support_preference: form.querySelector('[data-required-section="support_preference"]'),
  };

  const toggleSectionState = (key, isComplete) => {
    const section = requiredSections[key];
    if (section) {
      section.classList.toggle('is-incomplete', !isComplete);
    }
  };

  const validateRequiredFields = () => {
    const hasInterestModes = form.querySelectorAll('input[name="interest_modes"]:checked').length > 0;
    const hasTopics = (topicsInput?.value.trim().length || 0) > 0;
    const hasLearningMode = form.querySelectorAll('input[name="learning_mode"]:checked').length > 0;
    const hasSupportPreference = Boolean(form.querySelector('input[name="support_preference"]:checked'));

    toggleSectionState('interest_modes', hasInterestModes);
    toggleSectionState('topics', hasTopics);
    toggleSectionState('learning_mode', hasLearningMode);
    toggleSectionState('support_preference', hasSupportPreference);

    const complete = hasInterestModes && hasTopics && hasLearningMode && hasSupportPreference;
    if (saveBtn) {
      saveBtn.disabled = !complete;
    }
    if (requirementsHint) {
      requirementsHint.hidden = complete;
    }
    return complete;
  };

  const watchedSelectors = [
    'input[name="interest_modes"]',
    'input[name="learning_mode"]',
    'input[name="support_preference"]',
  ];
  watchedSelectors.forEach((selector) => {
    form.querySelectorAll(selector).forEach((element) => {
      element.addEventListener('change', validateRequiredFields);
    });
  });
  topicsInput?.addEventListener('input', validateRequiredFields);
  validateRequiredFields();

  const collectKeywords = () => {
    const raw = topicsInput?.value || '';
    return raw
      .split(/[,\\n]/)
      .map((chunk) => chunk.trim())
      .filter(Boolean);
  };

  const buildConversation = () => {
    const prompts = Array.from(document.querySelectorAll('.prompt-list li'))
      .map((li) => li.textContent.trim())
      .filter(Boolean);
    const keywords = collectKeywords();
    const modes = Array.from(form.querySelectorAll('input[name="interest_modes"]:checked')).map(
      (input) => input.value,
    );
    const learning = form.querySelector('input[name="learning_mode"]:checked')?.value || '';
    const support = form.querySelector('input[name="support_preference"]:checked')?.value || '';

    const conversation = [];
    if (keywords.length && prompts.length) {
      conversation.push({ prompt: prompts[0], response: keywords.join(', ') });
    }
    if (modes.length) {
      conversation.push({ prompt: 'Preferred exploration modes', response: modes.join(', ') });
    }
    if (learning) {
      conversation.push({ prompt: 'Preferred learning feel', response: learning });
    }
    if (support) {
      conversation.push({ prompt: 'Support preference', response: support });
    }
    return { conversation, keywords };
  };

  const renderSuggestions = (suggestions) => {
    if (!status || !aiContainer) {
      return;
    }
    if (!Array.isArray(suggestions) || suggestions.length === 0) {
      status.textContent = 'No new exemplar ideas were generated yet. Try adding more detail.';
      return;
    }
    aiContainer.hidden = false;
    const existingIds = new Set(
      Array.from(aiContainer.querySelectorAll('[data-suggestion-id]')).map((el) =>
        el.getAttribute('data-suggestion-id'),
      ),
    );
    const existingValues = new Set(
      Array.from(form.querySelectorAll('input[name="selected_exemplars"]')).map((input) => input.value),
    );

    let added = 0;
    suggestions.forEach((suggestion, index) => {
      const id = suggestion.id || `ai_suggestion_${Date.now()}_${index}`;
      if (existingIds.has(id)) {
        return;
      }

      const label = document.createElement('label');
      label.className = 'exemplar-card exemplar-card--ai';
      label.dataset.suggestionId = id;

      const input = document.createElement('input');
      input.type = 'checkbox';
      input.name = 'selected_exemplars';
      input.value = suggestion.title || `Exemplar Idea ${index + 1}`;
      if (existingValues.has(input.value)) {
        input.checked = true;
      }

      const body = document.createElement('div');
      body.className = 'exemplar-card__body';

      const heading = document.createElement('h4');
      heading.textContent = suggestion.title || `Exemplar Idea ${index + 1}`;
      body.appendChild(heading);

      if (suggestion.description) {
        const desc = document.createElement('p');
        desc.textContent = suggestion.description;
        body.appendChild(desc);
      }

      if (suggestion.era_or_setting || suggestion.discipline_emphasis) {
        const meta = document.createElement('ul');
        meta.className = 'exemplar-meta';
        if (suggestion.era_or_setting) {
          const li = document.createElement('li');
          li.textContent = suggestion.era_or_setting;
          meta.appendChild(li);
        }
        if (suggestion.discipline_emphasis) {
          const li = document.createElement('li');
          li.textContent = suggestion.discipline_emphasis;
          meta.appendChild(li);
        }
        body.appendChild(meta);
      }

      label.appendChild(input);
      label.appendChild(body);
      aiContainer.appendChild(label);

      existingIds.add(id);
      existingValues.add(input.value);
      added += 1;
    });

    status.textContent =
      added > 0
        ? `Added ${added} exemplar idea${added > 1 ? 's' : ''}. Select any that you want to explore.`
        : 'You already have these exemplar ideas. Try adjusting your interests for new suggestions.';
  };

  if (suggestBtn && status && aiContainer) {
    suggestBtn.addEventListener('click', async () => {
      const { conversation, keywords } = buildConversation();

      status.textContent = 'Asking the AI for exemplar ideas...';
      suggestBtn.disabled = true;

      try {
        const response = await fetch('/api/interest-suggestions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ conversation, keywords }),
        });

        const data = await response.json();
        if (!response.ok || data.error) {
          throw new Error(data.error || 'Unable to fetch exemplar ideas.');
        }
        renderSuggestions(data.suggestions || []);
      } catch (error) {
        status.textContent =
          error instanceof Error ? error.message : 'Unable to fetch exemplar ideas right now.';
      } finally {
        suggestBtn.disabled = false;
      }
    });
  }
});
