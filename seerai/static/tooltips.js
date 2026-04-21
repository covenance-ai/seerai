/**
 * Rich contextual tooltips for metric cards.
 *
 * Usage: after rendering cards, call  attachMetricTooltips(valuesObj)
 * where valuesObj has the raw metric values.
 *
 * Cards opt in via data-metric="efficiency|value|roi|subscription|api_equivalent".
 */

(function () {
  let overlay = null;
  let hideTimer = null;

  function getOrCreateOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'metric-tooltip';
    overlay.innerHTML = '<div class="tt-content"></div>';
    Object.assign(overlay.style, {
      position: 'absolute',
      zIndex: '50',
      maxWidth: '420px',
      opacity: '0',
      pointerEvents: 'none',
      transition: 'opacity 0.15s ease',
    });
    document.body.appendChild(overlay);

    // Keep overlay alive when hovering over it
    overlay.addEventListener('mouseenter', () => clearTimeout(hideTimer));
    overlay.addEventListener('mouseleave', () => scheduleHide());

    // Inject styles once
    const style = document.createElement('style');
    style.textContent = `
      .metric-tooltip {
        font-size: 0.8125rem;
        line-height: 1.5;
      }
      .metric-tooltip .tt-content {
        border-radius: 0.75rem;
        padding: 1rem 1.25rem;
        border: 1px solid #e5e7eb;
        background: white;
        color: #374151;
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);
      }
      .dark .metric-tooltip .tt-content {
        border-color: rgba(55,65,81,0.6);
        background: #111827;
        color: #d1d5db;
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.4);
      }
      .metric-tooltip h3 {
        font-weight: 600;
        margin: 0 0 0.5rem 0;
        font-size: 0.875rem;
      }
      .dark .metric-tooltip h3 { color: #f9fafb; }
      .metric-tooltip p { margin: 0.4rem 0; }
      .metric-tooltip .tt-verdict {
        margin-top: 0.75rem;
        padding: 0.5rem 0.75rem;
        border-radius: 0.5rem;
        font-weight: 500;
      }
      .metric-tooltip .tt-good {
        background: rgba(16,185,129,0.1);
        color: #059669;
      }
      .dark .metric-tooltip .tt-good {
        background: rgba(16,185,129,0.15);
        color: #34d399;
      }
      .metric-tooltip .tt-neutral {
        background: rgba(59,130,246,0.1);
        color: #2563eb;
      }
      .dark .metric-tooltip .tt-neutral {
        background: rgba(59,130,246,0.15);
        color: #60a5fa;
      }
      .metric-tooltip .tt-warn {
        background: rgba(245,158,11,0.1);
        color: #d97706;
      }
      .dark .metric-tooltip .tt-warn {
        background: rgba(245,158,11,0.15);
        color: #fbbf24;
      }
      .metric-tooltip .tt-formula {
        font-family: ui-monospace, monospace;
        font-size: 0.75rem;
        padding: 0.375rem 0.5rem;
        border-radius: 0.375rem;
        background: #f3f4f6;
        display: inline-block;
        margin: 0.25rem 0;
      }
      .dark .metric-tooltip .tt-formula {
        background: rgba(31,41,55,0.8);
      }
      [data-metric] { cursor: help; }
    `;
    document.head.appendChild(style);
    return overlay;
  }

  function show(cardEl, html) {
    clearTimeout(hideTimer);
    const el = getOrCreateOverlay();
    el.querySelector('.tt-content').innerHTML = html;
    el.style.opacity = '0';
    el.style.pointerEvents = 'auto';

    // Position below the card, aligned left
    const rect = cardEl.getBoundingClientRect();
    el.style.left = Math.max(8, rect.left + window.scrollX) + 'px';
    el.style.top = (rect.bottom + window.scrollY + 8) + 'px';

    // Clamp to viewport right edge
    requestAnimationFrame(() => {
      const ttRect = el.getBoundingClientRect();
      if (ttRect.right > window.innerWidth - 8) {
        el.style.left = Math.max(8, window.innerWidth - ttRect.width - 8) + 'px';
      }
      el.style.opacity = '1';
    });
  }

  function scheduleHide() {
    hideTimer = setTimeout(() => {
      if (overlay) {
        overlay.style.opacity = '0';
        overlay.style.pointerEvents = 'none';
      }
    }, 200);
  }

  function fmt$(n) { return '$' + n.toLocaleString(undefined, {maximumFractionDigits: 0}); }

  // ── Content generators ──

  function efficiencyContent(vals) {
    const r = vals.efficiency_ratio;
    let verdict;
    if (r === null) {
      verdict = `<div class="tt-verdict tt-neutral">${t('No subscription data available to compute efficiency.')}</div>`;
    } else if (r < 0.3) {
      const saving = Math.round((1 - r) * 100);
      verdict = `<div class="tt-verdict tt-warn">${t(`At <strong>${r.toFixed(2)}x</strong>, actual API usage is far below subscription cost. Switching to per-use API billing could save ~${saving}% on AI spend.`)}</div>`;
    } else if (r < 0.8) {
      verdict = `<div class="tt-verdict tt-warn">${t(`At <strong>${r.toFixed(2)}x</strong>, usage is moderate relative to subscription cost. Per-use billing would be cheaper, though subscriptions offer predictable budgeting.`)}</div>`;
    } else if (r <= 1.3) {
      verdict = `<div class="tt-verdict tt-good">${t(`At <strong>${r.toFixed(2)}x</strong>, you're in the healthy zone &mdash; subscription cost closely matches actual usage value.`)}</div>`;
    } else {
      verdict = `<div class="tt-verdict tt-good">${t(`At <strong>${r.toFixed(2)}x</strong>, the subscription is saving money &mdash; equivalent API billing would cost ${r.toFixed(1)}x more.`)}</div>`;
    }

    return `
      <h3>${t('Cost Efficiency')}</h3>
      <p>${t('Compares what your AI usage <strong>over the last 30 days</strong> would cost at per-token API rates versus the flat <strong>monthly subscription</strong> you pay.')}</p>
      <div class="tt-formula">${t('efficiency = API-equivalent cost (last 30d) &divide; subscription cost (per month)')}</div>
      <p>${t('Most AI providers offer two billing models: fixed monthly subscriptions (e.g. Claude Pro at $20/mo) or pay-per-use API access billed by tokens consumed. This ratio tells you which is the better deal for your usage pattern.')}</p>
      ${verdict}
    `;
  }

  function valueContent(vals) {
    const v = vals.estimated_value;
    const sub = vals.subscription;

    let context = '';
    if (sub > 0 && v > 0) {
      const ratio = v / sub;
      if (ratio > 5) {
        context = `<div class="tt-verdict tt-good">${t(`Estimated time savings of <strong>${fmt$(v)}</strong> against <strong>${fmt$(sub)}/mo</strong> in subscriptions &mdash; AI tools appear to be generating strong value.`)}</div>`;
      } else if (ratio > 1) {
        context = `<div class="tt-verdict tt-neutral">${t(`Estimated time savings of <strong>${fmt$(v)}</strong> against <strong>${fmt$(sub)}/mo</strong> in subscriptions &mdash; positive return, with room to grow through higher-utility usage.`)}</div>`;
      } else {
        context = `<div class="tt-verdict tt-warn">${t(`Estimated savings of <strong>${fmt$(v)}</strong> don't yet exceed the <strong>${fmt$(sub)}/mo</strong> subscription cost. Check if sessions are being classified correctly and if users need onboarding support.`)}</div>`;
      }
    }

    return `
      <h3>${t('Value (last 30 days)')}</h3>
      <p>${t("Net <strong>employee time impact</strong> over the trailing 30 days, in dollars at each person's hourly rate. Reported per month so it's apples-to-apples with monthly subscription cost.")}</p>
      <div class="tt-formula">${t('value = hourly_rate &times; log&thinsp;&sup2;(messages) &times; hours_factor &times; discount')}</div>
      <p>${t('<strong>hours_factor:</strong> useful = 0.25, trivial = 0.05, non-work = 0, <span style="color:#ef4444">harmful = &minus;0.30</span>.')}</p>
      <p>
        ${t("<strong>discount = 0.5 on positive contributions only</strong>: saved time isn't 1:1 fungible with paid hourly rate (the alternative might have been faster, or not strictly necessary). Harmful sessions skip the discount &mdash; cleanup time after a hallucination is real wall-clock time spent recovering.")}
      </p>
      <p>
        ${t("<strong>Harmful sessions</strong> aren't tagged at ingest. A post-hoc QA pass (stronger model + user feedback) re-reviews sessions and re-classifies the ones where AI sent the user down the wrong path. This drags total value down on teams where AI is being misused or trusted too readily.")}
      </p>
      <p>${t('This is a directional estimate &mdash; absolute numbers are rough, but <strong>relative comparisons</strong> across users and teams are meaningful.')}</p>
      ${context}
    `;
  }

  function roiContent(vals) {
    const r = vals.roi;
    let verdict;
    if (r === null) {
      verdict = `<div class="tt-verdict tt-neutral">${t('No subscription cost to compute ROI against.')}</div>`;
    } else if (r >= 10) {
      verdict = `<div class="tt-verdict tt-good">${t(`At <strong>${r.toFixed(1)}x</strong>, AI tools are generating exceptional value relative to their cost.`)}</div>`;
    } else if (r >= 2) {
      verdict = `<div class="tt-verdict tt-good">${t(`At <strong>${r.toFixed(1)}x</strong>, solid return &mdash; AI tools are clearly paying for themselves.`)}</div>`;
    } else if (r >= 1) {
      verdict = `<div class="tt-verdict tt-neutral">${t(`At <strong>${r.toFixed(1)}x</strong>, value slightly exceeds cost. Look for opportunities to increase useful-session ratio.`)}</div>`;
    } else {
      verdict = `<div class="tt-verdict tt-warn">${t(`At <strong>${r.toFixed(1)}x</strong>, subscription cost exceeds estimated value. Review whether utility classifications are accurate and whether some users need more onboarding.`)}</div>`;
    }

    return `
      <h3>${t('Return on Investment')}</h3>
      <p>${t('Measures whether AI subscriptions <strong>pay for themselves</strong> in estimated time savings. Both numerator and denominator are per-month figures.')}</p>
      <div class="tt-formula">${t('ROI = value (last 30d) &divide; subscription cost (per month)')}</div>
      <p>${t("Above 1.0 means the company is getting more in time savings than it spends on subscriptions. Below 1.0 suggests the investment isn't yet paying off.")}</p>
      ${verdict}
    `;
  }

  const generators = {
    efficiency: efficiencyContent,
    value: valueContent,
    roi: roiContent,
  };

  /**
   * Attach hover tooltips to all elements with data-metric="..." in the page.
   * @param {Object} vals - {efficiency_ratio, estimated_value, subscription, roi}
   */
  window.attachMetricTooltips = function (vals, container) {
    (container || document).querySelectorAll('[data-metric]').forEach(card => {
      const metric = card.dataset.metric;
      const gen = generators[metric];
      if (!gen) return;

      card.addEventListener('mouseenter', () => show(card, gen(vals)));
      card.addEventListener('mouseleave', () => scheduleHide());
    });
  };
})();
