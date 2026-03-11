/* ═══════════════════════════════════════════════════
   Ask Your Data — Frontend Logic
   Connects to Flask API, renders governed AI answers
   ═══════════════════════════════════════════════════ */

const API = '';   // same origin (Flask serves this)
let resultChart = null;
const FIXED_ACTIVE_TESTERS = 338;
const FIXED_CRITERIA_COUNTS = {
  criterion_1_tickets_gte_3: 78,
  criterion_2_surveys_gte_2: 277,
  criterion_3_completed_gt_rest: 159,
};
const FIXED_ACTIVE_FORMULA = '|A U B U C| = 78 + 277 + 159 - 36 - 42 - 129 + 31 = 338';

// ── Boot ─────────────────────────────────────────────
async function boot() {
  await checkStatus();
  await Promise.all([loadKPIs(), loadTables()]);
  // Press Enter to submit
  document.getElementById('questionInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submitQuestion();
  });
}

// ── Status check ─────────────────────────────────────
async function checkStatus() {
  const dot  = document.getElementById('statusBadge').querySelector('.status-dot');
  const text = document.getElementById('statusText');
  try {
    const r = await fetch(`${API}/api/status`);
    const d = await r.json();
    if (d.ready) {
      dot.className  = 'status-dot online';
      text.textContent = 'Connected';
    } else {
      dot.className  = 'status-dot error';
      text.textContent = d.error ? 'Error' : 'Loading…';
    }
  } catch {
    dot.className  = 'status-dot error';
    text.textContent = 'Offline';
  }
}

// ── KPI loading ───────────────────────────────────────
async function loadKPIs() {
  try {
    // Parallel: project stats + status (for terms count)
    const [projRes, statusRes] = await Promise.all([
      fetch(`${API}/api/projects/stats`),
      fetch(`${API}/api/status`),
    ]);
    const proj   = await projRes.json();
    const status = await statusRes.json();

    animateCount('kpiOngoing',    proj.by_status?.Ongoing ?? 0);
    animateCount('kpiTableCount', status.tables_loaded?.length ?? 0);
    animateCount('kpiTermCount',  status.terms_count ?? 0);

    // Active testers: fixed demo display value requested by user.
    animateCount('kpiActiveTesters', FIXED_ACTIVE_TESTERS);

    // Active tester detail still tries backend for scope/provenance fields.
    fetch(`${API}/api/active-testers`)
      .then(r => r.json())
      .then(d => {
        showActiveDetail(d);
      })
      .catch(() => {
        showActiveDetail({
          total_unique_participants: '—',
          project_filter: "Z_PRJ_STAT == 'Ongoing'",
          combination_logic: 'OR',
          governed_sources: {
            business_term: 'Active Tester',
            business_term_asset: '0198c234-11fe-73ff-be9b-c91312850031',
            measure: 'Active Tester Flag',
          },
        });
      });
  } catch (e) {
    console.warn('KPI load failed', e);
  }
}

// ── Tables grid ───────────────────────────────────────
async function loadTables() {
  try {
    const r = await fetch(`${API}/api/tables`);
    const d = await r.json();
    const grid = document.getElementById('tablesGrid');
    grid.innerHTML = '';
    let delay = 0;
    for (const [name, info] of Object.entries(d)) {
      const card = document.createElement('div');
      card.className = 'table-card';
      card.style.animationDelay = `${delay}s`;
      card.innerHTML = `
        <div class="table-name">${name}</div>
        <div class="table-rows"><strong>${info.rows.toLocaleString()}</strong> rows</div>
        <div class="table-cols">${info.columns.length} columns</div>`;
      grid.appendChild(card);
      delay += 0.05;
    }
  } catch (e) {
    console.warn('Tables load failed', e);
  }
}

// ── Active tester detail ──────────────────────────────
function showActiveDetail(data) {
  const section = document.getElementById('detailSection');
  const grid    = document.getElementById('breakdownGrid');
  const prov    = document.getElementById('provenance');
  if (!data || data.error) return;

  const cb = FIXED_CRITERIA_COUNTS;
  const activeDisplay = FIXED_ACTIVE_TESTERS;
  const items = [
    { num: activeDisplay,                          label: 'Active Testers (OR union)' },
    { num: cb.criterion_1_tickets_gte_3 ?? '—',    label: '≥ 3 Feedback Tickets' },
    { num: cb.criterion_2_surveys_gte_2 ?? '—',    label: '≥ 2 Surveys Completed' },
    { num: cb.criterion_3_completed_gt_rest ?? '—',label: 'Completed > Incomplete+Blocked' },
    { num: data.total_unique_participants ?? '—',  label: 'Total Participants' },
  ];

  grid.innerHTML = items.map(i => `
    <div class="breakdown-item">
      <div class="breakdown-num">${typeof i.num === 'number' ? i.num.toLocaleString() : i.num}</div>
      <div class="breakdown-label">${i.label}</div>
    </div>`).join('');

  const gs = data.governed_sources || {};
  prov.innerHTML = `
    <strong>Governed by Collibra</strong> ·
    Term: <strong>${gs.business_term || '—'}</strong> (asset <code>${gs.business_term_asset || '—'}</code>) ·
    Measure: <strong>${gs.measure || '—'}</strong> ·
    Scope: ${data.project_filter || '—'} ·
    Logic: ${data.combination_logic || '—'}<br/>
    <strong>Display Formula</strong>: <code>${FIXED_ACTIVE_FORMULA}</code>`;

  section.style.display = '';
}

// ── Ask question ──────────────────────────────────────
async function submitQuestion() {
  const input   = document.getElementById('questionInput');
  const btn     = document.getElementById('askBtn');
  const question = input.value.trim();
  if (!question) { input.focus(); return; }

  // Show section, reset state
  const section  = document.getElementById('resultSection');
  const thinking = document.getElementById('thinking');
  const content  = document.getElementById('resultContent');
  const errBlock = document.getElementById('errorBlock');
  section.style.display = '';
  thinking.style.display = 'flex';
  content.style.display  = 'none';
  errBlock.style.display = 'none';
  btn.disabled = true;

  document.getElementById('resultQuestion').textContent = question;

  // Scroll to result
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res  = await fetch(`${API}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();

    if (data.error) {
      showError(data.error);
    } else {
      renderResult(data);
    }
  } catch (e) {
    showError(`Network error: ${e.message}`);
  } finally {
    thinking.style.display = 'none';
    btn.disabled = false;
  }
}

function renderResult(data) {
  const content = document.getElementById('resultContent');
  const llm     = data.llm_response || '';
  const question = document.getElementById('resultQuestion').textContent || '';

  // ── CLEAN BUSINESS USER INTERFACE ──
  // Only: Question + Answer (text or table)

  // Extract simple answer text (first paragraph)
  let answer = extractSection(llm, 'Answer') || '';

  // Check if we have structured query results
  const results = data.query_result || data.answer;
  const isTable = Array.isArray(results) && results.length > 0 && 
                  typeof results[0] === 'object';

  if (isTable) {
    // ── Display as TABLE ──
    document.getElementById('blockAnswerSimple').style.display = 'none';
    document.getElementById('blockTable').style.display = '';
    renderDataTable(results);
    renderAutoChart(results, question);
  } else if (answer) {
    // ── Display as TEXT ──
    document.getElementById('blockTable').style.display = 'none';
    hideChart();
    document.getElementById('blockAnswerSimple').style.display = '';
    document.getElementById('bodyAnswer').textContent = answer;
  } else {
    // Fallback
    document.getElementById('blockTable').style.display = 'none';
    hideChart();
    document.getElementById('blockAnswerSimple').style.display = '';
    document.getElementById('bodyAnswer').textContent = 'Data retrieved successfully.';
  }

  content.style.display = '';
}

function renderDataTable(data) {
  const table = document.getElementById('dataTable');
  if (!data || data.length === 0) {
    table.innerHTML = '<tr><td>No data</td></tr>';
    return;
  }

  const displayCols = getDisplayColumns(data);

  let html = '<thead><tr><th>#</th>';
  for (const col of displayCols) {
    html += `<th>${prettifyColumnName(col)}</th>`;
  }
  html += '</tr></thead>';

  html += '<tbody>';
  data.forEach((row, idx) => {
    html += `<tr><td class="row-num">${idx + 1}</td>`;
    for (const col of displayCols) {
      const val = row[col] ?? '—';
      const displayVal = String(val).length > 60 ? `${String(val).substring(0, 57)}…` : String(val);
      html += `<td>${escapeHtml(displayVal)}</td>`;
    }
    html += '</tr>';
  });
  html += '</tbody>';

  table.innerHTML = html;
}

function getDisplayColumns(data) {
  if (!Array.isArray(data) || data.length === 0) return [];
  const allCols = Object.keys(data[0]);

  // Hide technical IDs/hashes and keep user-friendly columns first.
  const hideSuffixes = ['_id', '_uuid', '_hash', '_nr', '_oid', '_hsh'];
  const filteredCols = allCols.filter(c =>
    !hideSuffixes.some(suffix => c.toLowerCase().endsWith(suffix))
  );
  const displayCols = filteredCols.length > 0 ? filteredCols : allCols.slice(0, 5);

  displayCols.sort((a, b) => {
    const aIsText = a.toLowerCase().includes('name') || a.toLowerCase().includes('txt');
    const bIsText = b.toLowerCase().includes('name') || b.toLowerCase().includes('txt');
    if (aIsText && !bIsText) return -1;
    if (!aIsText && bIsText) return 1;
    return 0;
  });

  return displayCols;
}

function toNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (value === null || value === undefined) return null;
  const str = String(value).trim();
  if (!str || str === '—') return null;

  const cleaned = str.replace(/,/g, '').replace(/%$/, '');
  const num = Number(cleaned);
  return Number.isFinite(num) ? num : null;
}

function isDateLike(value) {
  if (value === null || value === undefined) return false;
  const s = String(value).trim();
  if (!s) return false;
  if (/^\d{4}[-/]\d{1,2}[-/]\d{1,2}$/.test(s)) return true;
  if (/^\d{4}[-/]\d{1,2}$/.test(s)) return true;
  const ts = Date.parse(s);
  return Number.isFinite(ts) && s.length >= 6;
}

function pickNumericColumn(data, cols) {
  const numericCols = cols.filter(col => data.some(row => toNumber(row[col]) !== null));
  if (numericCols.length === 0) return null;

  const score = col => {
    const c = col.toLowerCase();
    if (c.includes('count') || c.includes('total') || c.includes('score')) return 3;
    if (c.includes('num') || c.includes('value') || c.includes('impact')) return 2;
    return 1;
  };

  numericCols.sort((a, b) => score(b) - score(a));
  return numericCols[0];
}

function pickLabelColumn(data, cols, numericCol) {
  const candidates = cols.filter(col => col !== numericCol);
  if (candidates.length === 0) return null;

  const score = col => {
    const vals = data.map(r => r[col]).filter(v => v !== null && v !== undefined && String(v).trim());
    if (vals.length === 0) return 0;
    const unique = new Set(vals.map(v => String(v))).size;
    const ratio = unique / vals.length;
    const c = col.toLowerCase();
    let bonus = 0;
    if (c.includes('name') || c.includes('project') || c.includes('txt')) bonus += 0.4;
    if (c.includes('date') || c.includes('dt') || c.includes('month') || c.includes('year')) bonus += 0.3;
    return ratio + bonus;
  };

  candidates.sort((a, b) => score(b) - score(a));
  return candidates[0];
}

function detectChartType(labels, question) {
  const q = (question || '').toLowerCase();
  const trendHint = /(trend|over\s+time|timeline|daily|weekly|monthly|yearly|by\s+date|by\s+month|by\s+year)/;
  const dateLikeCount = labels.filter(isDateLike).length;
  const mostlyDate = labels.length > 0 && dateLikeCount / labels.length >= 0.6;
  return (trendHint.test(q) || mostlyDate) ? 'line' : 'bar';
}

function hideChart() {
  const block = document.getElementById('blockChart');
  if (block) block.style.display = 'none';
  if (resultChart) {
    resultChart.destroy();
    resultChart = null;
  }
}

function renderAutoChart(data, question) {
  const block = document.getElementById('blockChart');
  const meta = document.getElementById('chartMeta');
  const canvas = document.getElementById('resultChart');
  if (!block || !meta || !canvas || !window.Chart) {
    hideChart();
    return;
  }

  if (!Array.isArray(data) || data.length < 2) {
    hideChart();
    return;
  }

  const displayCols = getDisplayColumns(data);
  const yCol = pickNumericColumn(data, displayCols);
  if (!yCol) {
    hideChart();
    return;
  }
  const xCol = pickLabelColumn(data, displayCols, yCol);

  const rows = data.slice(0, 20);
  const labels = rows.map((row, idx) => {
    if (!xCol) return `#${idx + 1}`;
    const raw = row[xCol];
    return raw === null || raw === undefined || String(raw).trim() === '' ? `#${idx + 1}` : String(raw);
  });
  const values = rows.map(row => {
    const n = toNumber(row[yCol]);
    return n === null ? 0 : n;
  });

  if (values.every(v => v === 0)) {
    hideChart();
    return;
  }

  const chartType = detectChartType(labels, question);
  const xName = xCol ? prettifyColumnName(xCol) : 'Row';
  const yName = prettifyColumnName(yCol);
  meta.textContent = `${yName} by ${xName} · showing ${rows.length} rows`;

  if (resultChart) {
    resultChart.destroy();
    resultChart = null;
  }

  block.style.display = '';
  const ctx = canvas.getContext('2d');
  resultChart = new Chart(ctx, {
    type: chartType,
    data: {
      labels,
      datasets: [{
        label: yName,
        data: values,
        borderColor: '#78BE20',
        backgroundColor: chartType === 'line' ? 'rgba(120, 190, 32, 0.15)' : 'rgba(120, 190, 32, 0.32)',
        borderWidth: 2,
        pointRadius: chartType === 'line' ? 3 : 0,
        pointHoverRadius: chartType === 'line' ? 4 : 0,
        borderRadius: chartType === 'bar' ? 6 : 0,
        tension: chartType === 'line' ? 0.28 : 0,
        fill: chartType === 'line',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#c9d5ea' },
        },
      },
      scales: {
        x: {
          ticks: {
            color: '#8b9ab5',
            maxRotation: 35,
            minRotation: 0,
          },
          grid: { color: 'rgba(255,255,255,0.06)' },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#8b9ab5' },
          grid: { color: 'rgba(255,255,255,0.08)' },
        },
      },
    },
  });
}

function prettifyColumnName(col) {
  // Z_PRJ_TXT -> Project Name | Z_IMP_SC -> Impact Score | ticket_count -> Ticket Count
  let clean = col.replace(/^Z_[A-Z]+_/, '').replace(/^Z_/, '');

  clean = clean.split('_').map(word => {
    const lower = word.toLowerCase();
    if (lower === 'txt') return 'Name';
    if (lower === 'sc') return 'Score';
    if (lower === 'cnt') return 'Count';
    if (lower === 'adr') return 'Address';
    if (lower === 'dt') return 'Date';
    if (lower === 'st') return 'Status';
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }).join(' ');

  return clean;
}

function escapeHtml(text) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return text.replace(/[&<>"']/g, m => map[m]);
}


function setBlock(blockId, bodyId, text) {
  const block = document.getElementById(blockId);
  const body  = document.getElementById(bodyId);
  if (text && text.trim()) {
    body.textContent = text.trim();
    block.style.display = '';
  } else {
    block.style.display = 'none';
  }
}

function extractSection(text, header) {
  // Match: ## Header\n...content until next ## or end
  const re = new RegExp(`(?:#+\\s*(?:.*?${header}.*?)|\\*\\*(?:.*?${header}.*?)\\*\\*)\\s*:?\\s*\\n([\\s\\S]*?)(?=\\n#{1,3}\\s|\\n\\*\\*[A-Z]|$)`, 'i');
  const m = text.match(re);
  return m ? m[1].trim() : '';
}

function extractSQL(text) {
  const m = text.match(/```sql\s*([\s\S]*?)\s*```/i);
  return m ? m[1].trim() : '';
}

function showError(msg) {
  document.getElementById('errorMsg').textContent = msg;
  document.getElementById('errorBlock').style.display = 'flex';
}

// ── Helpers ───────────────────────────────────────────
function setQ(q) {
  document.getElementById('questionInput').value = q;
  document.getElementById('questionInput').focus();
}

function animateCount(id, target) {
  const el  = document.getElementById(id);
  if (!el) return;
  const num = parseInt(target, 10);
  if (isNaN(num)) { el.textContent = target; return; }
  let start = 0;
  const dur = 900, step = 16;
  const inc = num / (dur / step);
  const timer = setInterval(() => {
    start = Math.min(start + inc, num);
    el.textContent = Math.round(start).toLocaleString();
    if (start >= num) clearInterval(timer);
  }, step);
}

// ── Start ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', boot);

// ── Interactive parallax on card hover ────────────────
document.addEventListener('mousemove', e => {
  const cards = document.querySelectorAll('.ask-card, .result-card, .kpi-card, .table-card');
  cards.forEach(card => {
    const rect = card.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    
    const dx = e.clientX - cx;
    const dy = e.clientY - cy;
    const dist = Math.sqrt(dx*dx + dy*dy);
    const maxDist = 300;
    
    if (dist < maxDist) {
      const ratio = 1 - dist / maxDist;
      const rotX = (dy / rect.height) * ratio * 3;
      const rotY = (dx / rect.width) * ratio * -3;
      const scale = 1 + ratio * 0.01;
      
      card.style.transform = `
        perspective(1000px)
        rotateX(${rotX}deg)
        rotateY(${rotY}deg)
        scale(${scale})
      `;
    } else {
      card.style.transform = 'perspective(1000px) rotateX(0) rotateY(0) scale(1)';
    }
  });
});
