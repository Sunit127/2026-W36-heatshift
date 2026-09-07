import { buildPlan, safeParsePlans } from './logic.js';

const $ = (selector) => document.querySelector(selector);
const form = $('#shift-form');
const STORAGE_KEY = 'heatshift-plans-v1';
const API_BASE = globalThis.HEATSHIFT_API_BASE || '';
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
let currentPlan = null;

function values() {
  const formData = new FormData(form);

  return {
    shiftName: formData.get('shiftName'),
    startTime: formData.get('startTime'),
    duration: formData.get('duration'),
    temperature: formData.get('temperature'),
    humidity: formData.get('humidity'),
    intensity: formData.get('intensity'),
    sun: formData.get('sun'),
    ppe: formData.get('ppe'),
    acclimatized: formData.get('acclimatized') === 'on',
  };
}

function setDefaults() {
  const now = new Date();
  now.setMinutes(Math.ceil(now.getMinutes() / 15) * 15);

  form.elements.startTime.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes() % 60).padStart(2, '0')}`;
  form.elements.duration.value = '8';
  form.elements.temperature.value = '30';
  form.elements.humidity.value = '55';
}

function renderPlan(plan) {
  currentPlan = plan;
  $('#empty-result').hidden = true;
  $('#result').hidden = false;

  $('#result-title').textContent = plan.shiftName;

  const badge = $('#tier-badge');
  badge.textContent = plan.label;
  badge.className = `tier-badge tier-${plan.tier}`;

  $('#result-summary').textContent = plan.summary;
  $('#heat-index').textContent = `${plan.heatIndex}°C`;
  $('#check-in').textContent = `Every ${plan.check} min`;
  $('#review-time').textContent = `Every ${plan.review} min`;
  $('#callout').textContent = plan.callout;

  $('#checklist').replaceChildren(
    ...plan.checklist.map((item) => {
      const label = document.createElement('label');
      label.className = 'check-item';

      const box = document.createElement('input');
      box.type = 'checkbox';
      box.setAttribute('aria-label', item);

      const span = document.createElement('span');
      span.textContent = item;

      label.append(box, span);
      return label;
    }),
  );

  $('#timeline').replaceChildren(
    ...plan.timeline.map((step) => {
      const item = document.createElement('div');
      item.className = 'timeline-item';

      const time = document.createElement('strong');
      time.textContent = step.time;

      const label = document.createElement('span');
      label.textContent = step.label;

      item.append(time, label);
      return item;
    }),
  );
}

function loadPlans() {
  const saved = localStorage.getItem(STORAGE_KEY) || '[]';
  return safeParsePlans(saved);
}

function persistPlans(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  $('#save-status').textContent = 'Saved on this device';
  renderSavedPlans();
}

function initTiltForElement(element) {
  if (element.dataset.tiltBound === '1') {
    return;
  }

  element.dataset.tiltBound = '1';
  const depth = Number.parseFloat(element.dataset.depth || '1');

  let raf = null;

  const reset = () => {
    if (raf) {
      cancelAnimationFrame(raf);
      raf = null;
    }

    element.style.removeProperty('--tilt-rotate-x');
    element.style.removeProperty('--tilt-rotate-y');
    element.style.removeProperty('--tilt-scale');
    element.style.removeProperty('--tilt-translate-z');
  };

  const move = (event) => {
    if (prefersReducedMotion.matches) {
      return;
    }

    if (raf) {
      cancelAnimationFrame(raf);
    }

    raf = requestAnimationFrame(() => {
      const rect = element.getBoundingClientRect();
      const progressX = (event.clientX - rect.left) / rect.width;
      const progressY = (event.clientY - rect.top) / rect.height;

      const rotateX = (progressY - 0.5) * -9 * depth;
      const rotateY = (progressX - 0.5) * 11 * depth;
      const distance = Math.hypot(progressX - 0.5, progressY - 0.5);
      const translateZ = Math.max(6, 20 * (1 - distance) * depth);
      const scale = 1 + Math.min(0.02, distance * 0.03);

      element.style.setProperty('--tilt-rotate-x', `${rotateX.toFixed(2)}deg`);
      element.style.setProperty('--tilt-rotate-y', `${rotateY.toFixed(2)}deg`);
      element.style.setProperty('--tilt-translate-z', `${translateZ.toFixed(2)}px`);
      element.style.setProperty('--tilt-scale', scale.toFixed(3));
    });
  };

  element.addEventListener('pointermove', move, { passive: true });
  element.addEventListener('pointerleave', reset, { passive: true });
  element.addEventListener('pointerup', reset, { passive: true });
  element.addEventListener('pointercancel', reset, { passive: true });
}

function initTiltScenes(root = document) {
  root.querySelectorAll('[data-tilt]').forEach(initTiltForElement);
}

function renderSavedPlans() {
  const plans = loadPlans();
  const wrapper = $('#saved-plans');

  if (!plans.length) {
    wrapper.innerHTML = '<div class="saved-empty">No saved plans yet. Build one above, then save it for the next briefing.</div>';
    return;
  }

  wrapper.replaceChildren(
    ...plans.map((plan, index) => {
      const card = document.createElement('article');
      card.className = 'saved-card';
      card.setAttribute('data-tilt', '');
      card.dataset.depth = '0.7';

      const title = document.createElement('h3');
      title.textContent = plan.shiftName;

      const summary = document.createElement('p');
      summary.textContent = `${plan.startTime} · ${plan.duration}h · ${plan.heatIndex}°C estimated heat index · ${plan.label}`;

      const open = document.createElement('button');
      open.className = 'button secondary small';
      open.textContent = 'Open';
      open.onclick = () => {
        renderPlan(plan);
        location.hash = 'planner';
      };

      const remove = document.createElement('button');
      remove.className = 'text-button danger';
      remove.textContent = 'Delete';
      remove.onclick = () => {
        const next = loadPlans();
        next.splice(index, 1);
        persistPlans(next);
      };

      card.append(title, summary, open, remove);
      initTiltForElement(card);
      return card;
    }),
  );
}

async function sharePlan() {
  if (!currentPlan) {
    return;
  }

  if (!API_BASE) {
    $('#save-status').textContent = 'Sharing unavailable in offline mode';
    return;
  }

  const button = $('#share-plan');
  button.disabled = true;

  try {
    const endpoint = `${API_BASE.replace(/\/$/, '')}/api/v1/plans`;
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentPlan),
    });

    if (!response.ok) {
      throw new Error('Server rejected the plan');
    }

    const data = await response.json();
    $('#save-status').textContent = `Shared for team: ${data.shareToken}`;
  } catch (error) {
    $('#save-status').textContent = 'Could not share; plan remains on this device';
  } finally {
    button.disabled = false;
  }
}

function wireUpForm() {
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const error = $('#form-error');
    error.hidden = true;

    try {
      renderPlan(buildPlan(values()));
    } catch (error) {
      error.textContent = error.message;
      error.hidden = false;
      error.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  });

  form.addEventListener('reset', () => {
    setTimeout(() => {
      setDefaults();
      currentPlan = null;
      $('#result').hidden = true;
      $('#empty-result').hidden = false;
      $('#form-error').hidden = true;
    }, 0);
  });

  $('#load-sample').onclick = () => {
    Object.assign(form.elements.shiftName, { value: 'Community garden — afternoon setup' });
    form.elements.startTime.value = '13:00';
    form.elements.duration.value = '4';
    form.elements.temperature.value = '34';
    form.elements.humidity.value = '68';
    form.elements.intensity.value = 'moderate';
    form.elements.sun.value = 'direct';
    form.elements.ppe.value = 'standard';
    form.elements.acclimatized.checked = false;
    renderPlan(buildPlan(values()));
    location.hash = 'planner';
  };
}

function wireUpActions() {
  $('#save-plan').onclick = () => {
    if (!currentPlan) {
      return;
    }

    const items = loadPlans();
    items.unshift({ ...currentPlan, id: crypto.randomUUID() });
    persistPlans(items.slice(0, 25));
  };

  $('#print-plan').onclick = () => window.print();

  $('#share-plan').onclick = sharePlan;

  $('#export-data').onclick = () => {
    const blob = new Blob(
      [JSON.stringify({ exportedAt: new Date().toISOString(), plans: loadPlans() }, null, 2)],
      { type: 'application/json' },
    );
    const anchor = document.createElement('a');
    anchor.href = URL.createObjectURL(blob);
    anchor.download = 'heatshift-plans.json';
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  };

  $('#clear-data').onclick = () => {
    if (confirm('Delete every HeatShift plan stored in this browser?')) {
      localStorage.removeItem(STORAGE_KEY);
      renderSavedPlans();
    }
  };
}

function wireUpInstallPrompt() {
  let installPrompt;

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    installPrompt = event;
    $('#install-button').hidden = false;
  });

  $('#install-button').onclick = async () => {
    if (!installPrompt) {
      return;
    }

    await installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    $('#install-button').hidden = true;
  };
}

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    return;
  }

  navigator.serviceWorker.register('./sw.js').catch(() => {
    $('#save-status').textContent = 'Offline setup unavailable';
  });
}

function bootstrap() {
  // Keep motion respectful for users requesting reduced motion.
  if (!prefersReducedMotion.matches) {
    initTiltScenes();
  }

  setDefaults();
  renderSavedPlans();
  wireUpForm();
  wireUpActions();
  wireUpInstallPrompt();
  registerServiceWorker();
}

prefersReducedMotion.addEventListener('change', () => {
  // Reinitialize only when motion preference changes while the app is open.
  if (!prefersReducedMotion.matches) {
    initTiltScenes();
  }
});

bootstrap();
