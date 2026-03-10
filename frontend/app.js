/* ═══════════════════════════════════════════════════
   Ask Your Data — Frontend Logic
   Connects to Flask API, renders governed AI answers
   ═══════════════════════════════════════════════════ */

const API = '';   // same origin (Flask serves this)

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

    // Active testers — this may take a few seconds
    fetch(`${API}/api/active-testers`)
      .then(r => r.json())
      .then(d => {
        animateCount('kpiActiveTesters', d.answer ?? 0);
        showActiveDetail(d);
      })
      .catch(() => {});
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

  const cb = data.criteria_breakdown || {};
  const items = [
    { num: data.answer,                            label: 'Active Testers (OR union)' },
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
    Logic: ${data.combination_logic || '—'}`;

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
  } else if (answer) {
    // ── Display as TEXT ──
    document.getElementById('blockTable').style.display = 'none';
    document.getElementById('blockAnswerSimple').style.display = '';
    document.getElementById('bodyAnswer').textContent = answer;
  } else {
    // Fallback
    document.getElementById('blockTable').style.display = 'none';
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

  const obj = data[0];
  const allCols = Object.keys(obj);

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
