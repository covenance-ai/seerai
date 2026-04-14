/* Activity calendar — GitHub-style heatmap adapted from gleaner */

(function () {
  const css = `
.activity-months{display:flex;flex-wrap:wrap;gap:20px;margin-top:12px;user-select:none}
.activity-month{flex:0 0 auto}
.activity-month-title{font-size:11px;font-weight:600;color:var(--cal-text2,#9ca3af);margin-bottom:4px}
.activity-month-grid{display:grid;grid-template-columns:repeat(7,14px);grid-auto-rows:14px;gap:2px}
.activity-day-header{font-size:8px;color:var(--cal-text2,#9ca3af);text-align:center;line-height:14px}
.activity-day{width:14px;height:14px;border-radius:2px;background:rgba(128,128,128,.12);position:relative}
.activity-day:hover{outline:1px solid var(--cal-text2,#9ca3af)}
.activity-day:hover::after{content:attr(data-tip);position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:#1f2937;color:#f9fafb;padding:3px 8px;border-radius:4px;font-size:11px;white-space:nowrap;pointer-events:none;z-index:10}
.activity-day.empty{background:transparent;pointer-events:none}
.activity-day.l1{background:rgba(59,130,246,.25)}
.activity-day.l2{background:rgba(59,130,246,.45)}
.activity-day.l3{background:rgba(59,130,246,.65)}
.activity-day.l4{background:rgb(59,130,246)}
html.dark .activity-day:hover::after{background:#f9fafb;color:#1f2937}
html.dark .activity-day.l1{background:rgba(96,165,250,.3)}
html.dark .activity-day.l2{background:rgba(96,165,250,.5)}
html.dark .activity-day.l3{background:rgba(96,165,250,.7)}
html.dark .activity-day.l4{background:rgb(96,165,250)}
`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
})();

/**
 * Render a GitHub-style activity heatmap.
 * @param {Array<{date:string, count:number}>} days
 * @param {HTMLElement} el - container to render into
 * @param {function(string)|null} onDayClick - called with ISO date string on click
 */
function renderActivityCalendar(days, el, onDayClick) {
  if (!days || !days.length) { el.innerHTML = ''; return; }

  const max = Math.max(...days.map(d => d.count), 1);
  const t1 = Math.ceil(max * 0.25);
  const t2 = Math.ceil(max * 0.5);
  const t3 = Math.ceil(max * 0.75);
  function lvl(c) { return c === 0 ? '' : c <= t1 ? 'l1' : c <= t2 ? 'l2' : c <= t3 ? 'l3' : 'l4'; }

  const lookup = {};
  days.forEach(d => { lookup[d.date] = d.count; });

  const firstDate = new Date(days[0].date + 'T12:00:00');
  const lastDate = new Date(days[days.length - 1].date + 'T12:00:00');
  const lastIso = days[days.length - 1].date;

  let html = '';
  let y = firstDate.getFullYear(), m = firstDate.getMonth();
  const endY = lastDate.getFullYear(), endM = lastDate.getMonth();

  while (y < endY || (y === endY && m <= endM)) {
    const dim = new Date(y, m + 1, 0).getDate();
    const dow1 = (new Date(y, m, 1).getDay() + 6) % 7; // Mon=0
    const title = new Date(y, m, 15).toLocaleDateString(undefined, { month: 'short', year: 'numeric' });

    html += '<div class="activity-month"><div class="activity-month-title">' + title + '</div><div class="activity-month-grid">';
    ['Mo','Tu','We','Th','Fr','Sa','Su'].forEach(h => {
      html += '<div class="activity-day-header">' + h + '</div>';
    });

    for (let i = 0; i < dow1; i++) html += '<div class="activity-day empty"></div>';

    for (let d = 1; d <= dim; d++) {
      const iso = y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
      if (iso > lastIso) break;
      const count = lookup[iso] || 0;
      const clickAttr = count > 0 && onDayClick
        ? ' style="cursor:pointer" data-date="' + iso + '"'
        : '';
      html += '<div class="activity-day ' + lvl(count) + '" data-tip="' + iso + ': ' + count + '"' + clickAttr + '></div>';
    }
    html += '</div></div>';
    if (++m > 11) { m = 0; y++; }
  }

  el.innerHTML = '<div class="activity-months">' + html + '</div>';

  if (onDayClick) {
    el.addEventListener('click', function (e) {
      const day = e.target.closest('.activity-day[data-date]');
      if (day) onDayClick(day.dataset.date);
    });
  }
}
