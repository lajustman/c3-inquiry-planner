document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('learning-content');
  const status = document.getElementById('learning-status');
  const errorBox = document.getElementById('learning-error');
  const nextButton = document.getElementById('learning-next');
  const refreshButton = document.getElementById('learning-refresh');

  if (!container || !status || !errorBox || !nextButton) {
    return;
  }

  const stageProgress = {};
  const stageStates = {};
  let isLoading = false;

  const showError = (message) => {
    status.hidden = true;
    container.hidden = true;
    nextButton.hidden = true;
    errorBox.textContent = message;
    errorBox.hidden = false;
    if (refreshButton) {
      refreshButton.hidden = false;
      refreshButton.disabled = false;
    }
  };

  const checkCompletion = () => {
    const ids = Object.keys(stageProgress);
    if (!ids.length) {
      nextButton.hidden = true;
      return;
    }
    const allComplete = ids.every((id) => stageProgress[id]);
    nextButton.hidden = !allComplete;
  };

  const markStageComplete = (stageId) => {
    stageProgress[stageId] = true;
    checkCompletion();
  };

  const createSummary = (summary) => {
    if (!summary) {
      return null;
    }
    const summaryBlock = document.createElement('div');
    summaryBlock.className = 'learning-summary';
    summaryBlock.textContent = summary;
    return summaryBlock;
  };

  const renderResources = (resources, stageEl) => {
    if (!Array.isArray(resources) || !resources.length) {
      return false;
    }
    const filtered = resources.filter((resource) => resource && resource.url);
    if (!filtered.length) {
      return false;
    }

    const resourcesHeading = document.createElement('h4');
    resourcesHeading.textContent = 'Resources';
    stageEl.appendChild(resourcesHeading);

    const resourcesList = document.createElement('ul');
    resourcesList.className = 'learning-stage__resources';
    filtered.forEach((resource) => {
      const item = document.createElement('li');
      const titleRow = document.createElement('div');
      const link = document.createElement('a');
      link.href = resource.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = resource.title || resource.url;
      titleRow.appendChild(link);
      const format = (resource.format || 'article').toUpperCase();
      const formatBadge = document.createElement('span');
      formatBadge.className = `resource-format resource-format--${(resource.format || 'article').toLowerCase()}`;
      formatBadge.textContent = format;
      titleRow.appendChild(formatBadge);
      item.appendChild(titleRow);
      if (resource.description) {
        const desc = document.createElement('span');
        desc.textContent = resource.description;
        item.appendChild(desc);
      }
      resourcesList.appendChild(item);
    });
    stageEl.appendChild(resourcesList);
    return true;
  };

  const formatPercent = (value) => `${Math.round(value * 100)}%`;

  const submitFeedback = async (stage, attempt, content, file) => {
    let response;
    if (file) {
      const formData = new FormData();
      formData.append('stage_id', stage.id);
      formData.append('attempt', attempt);
      formData.append('content', content);
      formData.append('artifact', file);
      response = await fetch('/api/learning-feedback', {
        method: 'POST',
        body: formData,
      });
    } else {
      response = await fetch('/api/learning-feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage_id: stage.id, attempt, content }),
      });
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || 'Unable to score this entry right now.');
    }
    return response.json();
  };

  const createFeedbackWorkflow = (stage, options = {}) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'learning-interaction';

    if (options.contextList && options.contextList.length) {
      const contextHeading = document.createElement('h4');
      contextHeading.textContent = options.contextTitle || 'Your questions';
      wrapper.appendChild(contextHeading);
      const list = document.createElement('ul');
      list.className = 'learning-interaction__context';
      options.contextList.forEach((item) => {
        const li = document.createElement('li');
        li.textContent = item;
        list.appendChild(li);
      });
      wrapper.appendChild(list);
    }

    const promptText = document.createElement('p');
    promptText.textContent = options.prompt || stage.prompt || 'Share your thinking below.';
    wrapper.appendChild(promptText);

    const form = document.createElement('div');
    form.className = 'learning-interaction__form';

    const draftArea = document.createElement('textarea');
    draftArea.rows = options.rows || 5;
    draftArea.placeholder = options.placeholder || 'Type your response here...';
    form.appendChild(draftArea);

    let fileInput = null;
    if (options.allowUpload) {
      const fileLabel = document.createElement('label');
      fileLabel.className = 'learning-interaction__upload';
      fileLabel.textContent = options.uploadLabel || 'Upload image or audio (optional):';
      fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = options.uploadAccept || 'image/*,audio/*';
      fileLabel.appendChild(fileInput);
      form.appendChild(fileLabel);
      if (options.uploadHelp) {
        const helpText = document.createElement('p');
        helpText.className = 'learning-interaction__upload-help';
        helpText.textContent = options.uploadHelp;
        form.appendChild(helpText);
      }
    }

    const draftActions = document.createElement('div');
    draftActions.className = 'learning-actions';
    const draftBtn = document.createElement('button');
    draftBtn.type = 'button';
    draftBtn.textContent = options.draftLabel || 'Get feedback';
    draftActions.appendChild(draftBtn);
    form.appendChild(draftActions);

    const feedbackBox = document.createElement('div');
    feedbackBox.className = 'feedback-box';
    feedbackBox.hidden = true;
    wrapper.appendChild(form);
    wrapper.appendChild(feedbackBox);

    const revisionWrapper = document.createElement('div');
    revisionWrapper.className = 'learning-interaction__revision';
    revisionWrapper.hidden = true;

    const revisionLabel = document.createElement('label');
    revisionLabel.textContent = options.revisionPrompt || 'Revise your response using the feedback:';
    revisionWrapper.appendChild(revisionLabel);

    const revisionArea = document.createElement('textarea');
    revisionArea.rows = options.rows || 5;
    revisionWrapper.appendChild(revisionArea);

    let linkInput = null;
    if (options.allowLink) {
      const linkLabel = document.createElement('label');
      linkLabel.textContent = 'Optional link to your product:';
      linkLabel.className = 'learning-interaction__link-label';
      linkInput = document.createElement('input');
      linkInput.type = 'url';
      linkInput.placeholder = 'https://example.com/your-product';
      linkLabel.appendChild(linkInput);
      revisionWrapper.appendChild(linkLabel);
    }

    const revisionActions = document.createElement('div');
    revisionActions.className = 'learning-actions';
    const revisionBtn = document.createElement('button');
    revisionBtn.type = 'button';
    revisionBtn.textContent = options.revisionLabel || 'Check revision';
    revisionBtn.disabled = true;
    revisionActions.appendChild(revisionBtn);
    revisionWrapper.appendChild(revisionActions);
    wrapper.appendChild(revisionWrapper);

    const state = stageStates[stage.id] || (stageStates[stage.id] = { mastery: false });

    const handleResult = (res, attempt) => {
      feedbackBox.hidden = false;
      feedbackBox.classList.toggle('success', Boolean(res.mastery));
      feedbackBox.innerHTML = `
        <p>${res.feedback}</p>
        <p class="feedback-score">Progress: ${formatPercent(res.score)}</p>
      `;
      if (res.artifact_summary) {
        const artifactPara = document.createElement('p');
        artifactPara.className = 'feedback-artifact';
        artifactPara.textContent = `Upload insight: ${res.artifact_summary}`;
        feedbackBox.appendChild(artifactPara);
      }

      if (res.mastery) {
        stageProgress[stage.id] = true;
        state.mastery = true;
        draftBtn.disabled = true;
        draftArea.disabled = true;
        revisionBtn.disabled = true;
        revisionArea.disabled = true;
        if (linkInput) {
          linkInput.disabled = true;
        }
        if (fileInput) {
          fileInput.disabled = true;
        }
        revisionWrapper.hidden = true;
        markStageComplete(stage.id);
      } else {
        stageProgress[stage.id] = false;
        revisionWrapper.hidden = false;
        revisionBtn.disabled = false;
        state.mastery = false;
        checkCompletion();
      }
    };

    draftBtn.addEventListener('click', async () => {
      const content = draftArea.value.trim();
      const file = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
      if (!content && !file) {
        feedbackBox.hidden = false;
        feedbackBox.classList.remove('success');
        feedbackBox.textContent = 'Add your response or upload a supported file before requesting feedback.';
        return;
      }
      draftBtn.disabled = true;
      feedbackBox.hidden = true;
      try {
        const res = await submitFeedback(stage, 'draft', content, file);
        handleResult(res, 'draft');
        if (!res.mastery) {
          revisionArea.value = content;
        }
      } catch (error) {
        draftBtn.disabled = false;
        feedbackBox.hidden = false;
        feedbackBox.classList.remove('success');
        feedbackBox.textContent = error instanceof Error ? error.message : 'Unable to score this entry right now.';
      } finally {
        if (fileInput) {
          fileInput.value = '';
        }
      }
    });

    revisionBtn.addEventListener('click', async () => {
      let content = revisionArea.value.trim();
      const file = fileInput && fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
      if (!content && !file) {
        feedbackBox.hidden = false;
        feedbackBox.classList.remove('success');
        feedbackBox.textContent = 'Add your revision or upload a supported file before checking again.';
        return;
      }
      if (linkInput && linkInput.value.trim()) {
        content += `\nLink: ${linkInput.value.trim()}`;
      }
      revisionBtn.disabled = true;
      feedbackBox.hidden = true;
      try {
        const res = await submitFeedback(stage, 'revision', content, file);
        handleResult(res, 'revision');
        if (!res.mastery) {
          revisionBtn.disabled = false;
        }
      } catch (error) {
        revisionBtn.disabled = false;
        feedbackBox.hidden = false;
        feedbackBox.classList.remove('success');
        feedbackBox.textContent = error instanceof Error ? error.message : 'Unable to score this entry right now.';
      } finally {
        if (fileInput) {
          fileInput.value = '';
        }
      }
    });

    return wrapper;
  };

  const createStage = (stage, displayIndex) => {
    const stageEl = document.createElement('article');
    stageEl.className = 'learning-stage';

    const header = document.createElement('div');
    header.className = 'learning-stage__header';

    const title = document.createElement('h3');
    title.textContent = displayIndex ? `${displayIndex}. ${stage.title || 'Learning Step'}` : stage.title || 'Learning Step';
    header.appendChild(title);

    stageEl.appendChild(header);

    if (stage.purpose) {
      const purpose = document.createElement('p');
      purpose.textContent = stage.purpose;
      stageEl.appendChild(purpose);
    }

    if (Array.isArray(stage.activities) && stage.activities.length) {
      const activities = document.createElement('ul');
      activities.className = 'learning-stage__activities';
      stage.activities.forEach((activity) => {
        const item = document.createElement('li');
        item.textContent = activity;
        activities.appendChild(item);
      });
      stageEl.appendChild(activities);
    }

    const hasResources = renderResources(stage.resources, stageEl);
    if (!hasResources) {
      const placeholder = document.createElement('div');
      placeholder.className = 'learning-resource-placeholder';
      placeholder.textContent = 'Resources will appear here once your teacher or the research agent adds verified sources.';
      stageEl.appendChild(placeholder);
    }

    if (stage.type === 'create' && Array.isArray(stage.product_suggestions) && stage.product_suggestions.length) {
      const suggestionHeading = document.createElement('h4');
      suggestionHeading.textContent = 'Product ideas';
      stageEl.appendChild(suggestionHeading);
      const suggestionList = document.createElement('ul');
      suggestionList.className = 'learning-stage__activities';
      stage.product_suggestions.forEach((suggestion) => {
        const li = document.createElement('li');
        li.textContent = suggestion;
        suggestionList.appendChild(li);
      });
      stageEl.appendChild(suggestionList);
    }

    if (stage.checkpoint) {
      const checkpoint = document.createElement('div');
      checkpoint.className = 'learning-stage__checkpoint';
      checkpoint.textContent = stage.checkpoint;
      stageEl.appendChild(checkpoint);
    }

    let interaction = null;
    const stageType = (stage.type || '').toLowerCase();
    if (stageType === 'launch_connect') {
      interaction = createFeedbackWorkflow(stage, {
        prompt: stage.prompt || 'Choose one of your questions and explain what you notice right now.',
        contextTitle: 'Your questions',
        contextList: stage.student_questions || [],
        placeholder: 'Explain what you think or wonder right now…',
        revisionPrompt: 'Revise your response using the feedback:',
      });
      stageProgress[stage.id] = false;
    } else if (stageType === 'investigate') {
      interaction = createFeedbackWorkflow(stage, {
        prompt: stage.prompt || 'Write your claim + evidence statement below.',
        placeholder: 'Write your claim and cite the evidence that supports it…',
        revisionPrompt: 'Revise your claim + evidence using the feedback:',
      });
      stageProgress[stage.id] = false;
    } else if (stageType === 'create') {
      interaction = createFeedbackWorkflow(stage, {
        prompt: stage.prompt || 'Describe or paste your product below. Add a link if you published it elsewhere.',
        placeholder: 'Summarise your product or paste the main text here…',
        revisionPrompt: 'Revise your product entry using the feedback:',
        allowLink: true,
        allowUpload: true,
        uploadLabel: 'Upload an image or audio clip of your product (optional):',
        uploadHelp: 'Images (.png, .jpg) or audio (.mp3, .m4a, .wav) up to 6 MB are supported.',
      });
      stageProgress[stage.id] = false;
    } else if (stageType === 'primer') {
      stageProgress[stage.id] = true;
    } else {
      stageProgress[stage.id] = true;
    }

    if (interaction) {
      stageEl.appendChild(interaction);
    }

    return stageEl;
  };

  const createNextFocus = (items) => {
    if (!Array.isArray(items) || !items.length) {
      return null;
    }
    const wrapper = document.createElement('div');
    wrapper.className = 'learning-next-focus';

    const heading = document.createElement('strong');
    heading.textContent = 'Next, focus on:';
    wrapper.appendChild(heading);

    const list = document.createElement('ul');
    items.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      list.appendChild(li);
    });
    wrapper.appendChild(list);

    return wrapper;
  };

  const renderLearningPath = (path) => {
    container.innerHTML = '';
    Object.keys(stageProgress).forEach((key) => {
      delete stageProgress[key];
    });
    Object.keys(stageStates).forEach((key) => {
      delete stageStates[key];
    });

    const summaryBlock = createSummary(path.summary);
    if (summaryBlock) {
      container.appendChild(summaryBlock);
    }

    if (Array.isArray(path.stages) && path.stages.length) {
      const stagesWrapper = document.createElement('div');
      stagesWrapper.className = 'learning-stages';
      let displayIndex = 0;
      path.stages.forEach((stage, index) => {
        if (!stage.id) {
          stage.id = `stage-${index + 1}`;
        }
        const isPrimer = (stage.type || '').toLowerCase() === 'primer';
        const stageNumber = isPrimer ? null : ++displayIndex;
        stagesWrapper.appendChild(createStage(stage, stageNumber));
      });
      container.appendChild(stagesWrapper);
    }

    if (path.mastery_tip) {
      const tip = document.createElement('div');
      tip.className = 'learning-summary learning-summary--tip';
      const tipHeading = document.createElement('strong');
      tipHeading.textContent = 'Mastery tip';
      tip.appendChild(tipHeading);
      const tipText = document.createElement('p');
      tipText.textContent = path.mastery_tip;
      tip.appendChild(tipText);
      container.appendChild(tip);
    }

    const nextFocus = createNextFocus(path.next_focus);
    if (nextFocus) {
      container.appendChild(nextFocus);
    }

    checkCompletion();
    if (refreshButton) {
      refreshButton.hidden = false;
      refreshButton.disabled = false;
    }
  };

  const loadLearningPath = async ({ force = false } = {}) => {
    if (isLoading) {
      return;
    }
    isLoading = true;
    if (refreshButton) {
      refreshButton.disabled = true;
    }
    if (force || container.hidden) {
      status.hidden = false;
    }
    errorBox.hidden = true;
    if (force) {
      container.hidden = true;
      nextButton.hidden = true;
    }

    try {
      const payload = force ? { force_regenerate: true } : {};
      const response = await fetch('/api/learning-path', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || 'Unable to build a learning path right now.');
      }

      const data = await response.json();
      if (!data || !data.path) {
        throw new Error('Learning path data was missing.');
      }

      renderLearningPath(data.path);
      status.hidden = true;
      errorBox.hidden = true;
      container.hidden = false;
    } catch (error) {
      showError(error instanceof Error ? error.message : 'Unable to build a learning path right now.');
    } finally {
      isLoading = false;
      if (refreshButton) {
        refreshButton.disabled = false;
      }
    }
  };

  if (refreshButton) {
    refreshButton.addEventListener('click', () => {
      loadLearningPath({ force: true });
    });
  }

  loadLearningPath();
});
