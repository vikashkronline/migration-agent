/**
 * Migration Agent Local Control Center - Client Controller
 * Pure Reactive Vanilla/Angular Client with Strict Security Guardrails
 */

(function () {
  'use strict';

  // 1. Session Token Resolution
  const urlParams = new URLSearchParams(window.location.search);
  let sessionToken = urlParams.get('token') || '';
  if (!sessionToken) {
    const match = document.cookie.match(new RegExp('(^| )session_token=([^;]+)'));
    if (match) sessionToken = match[2];
  }

  // 2. State Store
  const state = {
    activeTab: 'runs',
    token: sessionToken,
    runs: [],
    selectedRun: null,
    selectedRunId: null,
    diffData: null,
    planData: null,
    graphData: null,
    learningsData: null,
    doctorData: null,
    events: [],
    wsConnected: false,
    actorName: 'local-developer',
  };

  // 3. API Client
  async function apiRequest(endpoint, options = {}) {
    const headers = options.headers || {};
    if (state.token) {
      headers['X-Session-Token'] = state.token;
      headers['X-CSRF-Token'] = state.token;
    }
    headers['Content-Type'] = 'application/json';

    const resp = await fetch(endpoint, {
      ...options,
      headers,
    });

    if (resp.status === 401) {
      showToast('Authentication Error', 'Session token invalid or expired.', 'danger');
      throw new Error('Unauthorized');
    }
    if (resp.status === 403) {
      showToast('Security Error', 'Origin or CSRF check rejected.', 'danger');
      throw new Error('Forbidden');
    }

    const data = await resp.json();
    if (data.status === 'error') {
      showToast('API Error', data.error ? data.error.message : 'Unknown error', 'danger');
      throw new Error(data.error ? data.error.message : 'API Error');
    }
    return data.data;
  }

  // 4. WebSocket & Event Handling
  function connectWebSocket() {
    if (!state.token) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(state.token)}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        state.wsConnected = true;
        updateWsIndicator();
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          handleLiveEvent(msg);
        } catch (e) {
          console.error('Failed to parse WebSocket message', e);
        }
      };

      ws.onclose = () => {
        state.wsConnected = false;
        updateWsIndicator();
        setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
      connectSseFallback();
    }
  }

  function connectSseFallback() {
    if (!window.EventSource || !state.token) return;
    const sse = new EventSource(`/api/v1/events?token=${encodeURIComponent(state.token)}`);
    sse.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleLiveEvent(msg);
      } catch (e) {}
    };
  }

  function handleLiveEvent(msg) {
    state.events.unshift(msg);
    if (state.events.length > 50) state.events.pop();
    renderEventTimeline();

    if (msg.event_type === 'PLAN_APPROVED') {
      showToast('Plan Approved', `Plan ${msg.payload.plan_id} approved by ${msg.payload.actor}`, 'success');
      if (state.activeTab === 'plan') loadPlan(msg.payload.plan_id);
    } else if (msg.event_type === 'RUN_APPLIED') {
      showToast('Run Applied', `Run ${msg.payload.run_id} applied successfully`, 'success');
      loadRuns();
    }
  }

  function updateWsIndicator() {
    const badge = document.getElementById('ws-badge');
    if (!badge) return;
    if (state.wsConnected) {
      badge.className = 'badge bg-success';
      badge.textContent = 'Live Connected';
    } else {
      badge.className = 'badge bg-secondary';
      badge.textContent = 'Connecting...';
    }
  }

  // 5. Views & Data Loading
  async function loadDoctor() {
    try {
      state.doctorData = await apiRequest('/api/v1/health');
      renderDoctorView();
    } catch (e) {}
  }

  async function loadRuns() {
    try {
      state.runs = await apiRequest('/api/v1/runs');
      renderRunsList();
      if (state.runs.length > 0 && !state.selectedRunId) {
        selectRun(state.runs[0].run_id);
      }
    } catch (e) {}
  }

  async function selectRun(runId) {
    state.selectedRunId = runId;
    try {
      state.selectedRun = await apiRequest(`/api/v1/runs/${runId}`);
      renderRunDetail();
      loadDiff(runId);
      if (state.selectedRun.plan_id) {
        loadPlan(state.selectedRun.plan_id);
      }
    } catch (e) {}
  }

  async function loadDiff(runId) {
    try {
      state.diffData = await apiRequest(`/api/v1/runs/${runId}/diff`);
      renderDiffView();
    } catch (e) {
      state.diffData = null;
      renderDiffView();
    }
  }

  async function loadPlan(planId) {
    try {
      state.planData = await apiRequest(`/api/v1/plans/${planId}`);
      renderPlanView();
    } catch (e) {
      state.planData = null;
      renderPlanView();
    }
  }

  async function loadGraph() {
    try {
      state.graphData = await apiRequest('/api/v1/graph');
      renderGraphView();
    } catch (e) {}
  }

  async function loadLearnings() {
    try {
      state.learningsData = await apiRequest('/api/v1/learnings');
      renderLearningsView();
    } catch (e) {}
  }

  // 6. Mutating Actions
  window.approveCurrentPlan = async function () {
    if (!state.planData) return;
    const planId = state.planData.plan_id;
    const actor = document.getElementById('actor-input')?.value || state.actorName;
    const notes = document.getElementById('approval-notes')?.value || 'Approved via Control Center GUI';
    const requestId = 'req-' + Date.now();

    try {
      await apiRequest(`/api/v1/plans/${planId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ actor, notes, request_id: requestId }),
      });
      showToast('Approval Recorded', `Plan ${planId} cryptographically signed!`, 'success');
      loadPlan(planId);
      loadRuns();
    } catch (e) {
      showToast('Approval Failed', e.message, 'danger');
    }
  };

  window.applyCurrentRun = async function () {
    if (!state.selectedRunId) return;
    const runId = state.selectedRunId;
    const actor = document.getElementById('actor-input')?.value || state.actorName;
    const requestId = 'req-' + Date.now();

    try {
      await apiRequest(`/api/v1/runs/${runId}/apply`, {
        method: 'POST',
        body: JSON.stringify({ actor, request_id: requestId }),
      });
      showToast('Apply Initiated', `Controlled apply executed for ${runId}`, 'success');
      selectRun(runId);
    } catch (e) {
      showToast('Apply Failed', e.message, 'danger');
    }
  };

  // 7. Renderers
  function renderRunsList() {
    const listEl = document.getElementById('runs-table-body');
    if (!listEl) return;
    if (state.runs.length === 0) {
      listEl.innerHTML = '<tr><td colspan="5" class="text-muted text-center py-3">No runs recorded yet.</td></tr>';
      return;
    }

    listEl.innerHTML = state.runs
      .map((r) => {
        let statusBadge = `<span class="badge bg-secondary">${r.status}</span>`;
        if (r.status === 'COMPLETED') statusBadge = '<span class="badge-status badge-completed">COMPLETED</span>';
        if (r.status === 'FAILED') statusBadge = '<span class="badge-status badge-failed">FAILED</span>';
        if (r.has_recovery_required || r.terminal_state === 'RECOVERY_REQUIRED') {
          statusBadge = '<span class="badge-status badge-recovery">RECOVERY REQUIRED</span>';
        }

        const isSelected = r.run_id === state.selectedRunId;
        const rowClass = isSelected ? 'table-active' : '';

        return `
          <tr class="${rowClass}" style="cursor: pointer;" onclick="window.selectRun('${r.run_id}')">
            <td class="fw-semibold text-info">${r.run_id}</td>
            <td>${r.plan_id}</td>
            <td>${statusBadge}</td>
            <td class="text-muted small">${new Date(r.updated_at).toLocaleTimeString()}</td>
          </tr>
        `;
      })
      .join('');
  }

  function renderRunDetail() {
    const detailEl = document.getElementById('run-detail-content');
    if (!detailEl) return;
    if (!state.selectedRun) {
      detailEl.innerHTML = '<p class="text-muted">Select a run to view details.</p>';
      return;
    }

    const r = state.selectedRun;
    let terminalAlert = '';
    if (r.terminal_state === 'RECOVERY_REQUIRED') {
      terminalAlert = `
        <div class="alert alert-warning mb-3">
          <h5 class="alert-heading fw-bold mb-1">⚠️ Recovery Required</h5>
          <p class="mb-2 small">${r.terminal_reason || 'Interrupted apply or uncertain rollback.'}</p>
          <div class="small fw-semibold">Recommended Actions:</div>
          <ul class="mb-0 small ps-3">
            ${r.recovery_actions.map((act) => `<li>${act}</li>`).join('')}
          </ul>
        </div>
      `;
    } else if (r.terminal_state === 'BASE_CHANGED') {
      terminalAlert = `
        <div class="alert alert-danger mb-3">
          <h5 class="alert-heading fw-bold mb-1">🛑 Target Base Drift Detected</h5>
          <p class="mb-0 small">The target repository has moved since planning. Please re-run analysis.</p>
        </div>
      `;
    }

    detailEl.innerHTML = `
      ${terminalAlert}
      <div class="d-flex justify-content-between align-items-center mb-3">
        <div>
          <span class="text-muted small">Run ID:</span>
          <span class="fw-bold ms-1 text-info">${r.run_id}</span>
        </div>
        <div>
          <span class="text-muted small">Plan:</span>
          <span class="badge bg-dark border ms-1">${r.plan_id}</span>
        </div>
      </div>
      <div class="mb-3">
        <label class="form-label small text-muted mb-1">Source Repository:</label>
        <div class="p-2 rounded bg-dark border small text-break">${r.source_root}</div>
      </div>
      <div class="mb-3">
        <div class="fw-semibold small mb-2">Checkpoints (${r.checkpoints.length}):</div>
        <div class="list-group small">
          ${r.checkpoints
            .map(
              (cp) => `
            <div class="list-group-item bg-transparent text-light border-secondary py-2">
              <div class="d-flex justify-content-between">
                <span class="fw-bold text-accent">${cp.type}</span>
                <span class="text-muted small">${new Date(cp.timestamp).toLocaleTimeString()}</span>
              </div>
              <div class="text-muted text-truncate">${JSON.stringify(cp.state_data)}</div>
            </div>
          `
            )
            .join('')}
        </div>
      </div>
    `;
  }

  function renderDiffView() {
    const diffEl = document.getElementById('diff-content');
    if (!diffEl) return;
    if (!state.diffData || !state.diffData.files || state.diffData.files.length === 0) {
      diffEl.innerHTML = `
        <div class="text-center text-muted py-5">
          <div class="mb-2">📄</div>
          <div>No staged file modifications for this run.</div>
        </div>
      `;
      return;
    }

    const d = state.diffData;
    diffEl.innerHTML = `
      <div class="d-flex justify-content-between align-items-center mb-3">
        <div>
          <span class="fw-bold">${d.total_files} file(s) modified</span>
          <span class="badge bg-success ms-2">+${d.total_additions}</span>
          <span class="badge bg-danger ms-1">-${d.total_deletions}</span>
        </div>
        <div class="small text-muted">
          Digest: <code class="text-info">${d.changeset_digest ? d.changeset_digest.slice(0, 16) + '...' : 'none'}</code>
        </div>
      </div>
      ${d.files
        .map(
          (f) => `
        <div class="card mb-3">
          <div class="card-header d-flex justify-content-between align-items-center py-2">
            <div class="d-flex align-items-center gap-2">
              <span class="badge ${f.change_type === 'CREATE' ? 'bg-success' : f.change_type === 'DELETE' ? 'bg-danger' : 'bg-primary'}">${f.change_type}</span>
              <span class="fw-semibold small">${f.path}</span>
            </div>
            <div>
              <span class="badge bg-success small">+${f.additions}</span>
              <span class="badge bg-danger small">-${f.deletions}</span>
            </div>
          </div>
          <div class="card-body p-0">
            <div class="diff-container p-2">
              ${f.patch
                ? f.patch
                    .split('\n')
                    .map((line) => {
                      let cls = '';
                      if (line.startsWith('+') && !line.startsWith('+++')) cls = 'diff-add';
                      else if (line.startsWith('-') && !line.startsWith('---')) cls = 'diff-del';
                      else if (line.startsWith('@@')) cls = 'diff-header';
                      return `<div class="diff-line ${cls}">${escapeHtml(line)}</div>`;
                    })
                    .join('')
                : '<div class="text-muted p-2">No textual diff available.</div>'}
            </div>
          </div>
        </div>
      `
        )
        .join('')}
    `;
  }

  function renderPlanView() {
    const planEl = document.getElementById('plan-content');
    if (!planEl) return;
    if (!state.planData) {
      planEl.innerHTML = '<div class="text-muted text-center py-5">No active plan found for this run.</div>';
      return;
    }

    const p = state.planData;
    const isApproved = p.is_approved;
    const statusBadge = isApproved
      ? '<span class="badge bg-success">APPROVED</span>'
      : '<span class="badge bg-warning text-dark">NEEDS APPROVAL</span>';

    planEl.innerHTML = `
      <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h4 class="mb-1 fw-bold">Plan: ${p.plan_id}</h4>
          <div class="text-muted small">Content Digest: <code class="text-info">${p.plan_digest.slice(0, 24)}...</code></div>
        </div>
        <div class="d-flex align-items-center gap-3">
          ${statusBadge}
          ${
            !isApproved
              ? `<button class="btn btn-success fw-bold px-3" onclick="window.approveCurrentPlan()">Sign & Approve</button>`
              : `<button class="btn btn-primary fw-bold px-3" onclick="window.applyCurrentRun()">Apply to Target</button>`
          }
        </div>
      </div>

      <div class="row mb-4">
        <div class="col-md-8">
          <h5 class="fw-bold mb-3">Migration Steps (${p.steps.length})</h5>
          <div class="d-flex flex-column gap-3">
            ${p.steps
              .map(
                (s, idx) => `
              <div class="card">
                <div class="card-body">
                  <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="fw-bold text-accent">${idx + 1}. ${s.title}</div>
                    <span class="badge ${s.risk === 'HIGH' ? 'bg-danger' : s.risk === 'MEDIUM' ? 'bg-warning text-dark' : 'bg-secondary'}">${s.risk} RISK</span>
                  </div>
                  <p class="small text-muted mb-2">${s.description}</p>
                  <div class="d-flex flex-wrap gap-1">
                    ${s.expected_files.map((f) => `<span class="badge bg-dark border text-light small">${f}</span>`).join('')}
                  </div>
                </div>
              </div>
            `
              )
              .join('')}
          </div>
        </div>
        <div class="col-md-4">
          <div class="card">
            <div class="card-header fw-bold small">Approval Authority (ADR-2)</div>
            <div class="card-body">
              <div class="mb-3">
                <label class="form-label small text-muted">Actor Identity:</label>
                <input type="text" id="actor-input" class="form-control form-control-sm bg-dark text-light border-secondary" value="${state.actorName}">
              </div>
              <div class="mb-3">
                <label class="form-label small text-muted">Approval Notes:</label>
                <textarea id="approval-notes" class="form-control form-control-sm bg-dark text-light border-secondary" rows="2" placeholder="Audit sign-off note..."></textarea>
              </div>
              ${
                p.approval_signature
                  ? `
                <div class="p-2 rounded bg-dark border small">
                  <div class="fw-semibold text-success mb-1">✓ Signature Valid</div>
                  <div class="text-muted">Actor: ${p.approval_signature.actor}</div>
                  <div class="text-muted">Signed: ${new Date(p.approval_signature.timestamp).toLocaleString()}</div>
                </div>
              `
                  : `
                <div class="text-muted small">This plan requires human verification before applying changes to target workspace.</div>
              `
              }
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderGraphView() {
    const graphBox = document.getElementById('mermaid-output');
    if (!graphBox) return;
    if (!state.graphData || !state.graphData.mermaid_source) {
      graphBox.innerHTML = '<div class="text-muted text-center py-5">No cross-domain graph discovered.</div>';
      return;
    }

    const source = state.graphData.mermaid_source;
    if (window.mermaid) {
      try {
        window.mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'dark',
        });
        window.mermaid.render('mermaid-svg-graph', source).then((res) => {
          graphBox.innerHTML = res.svg;
        });
      } catch (e) {
        graphBox.innerHTML = `<pre class="text-light p-3 small">${escapeHtml(source)}</pre>`;
      }
    } else {
      graphBox.innerHTML = `<pre class="text-light p-3 small">${escapeHtml(source)}</pre>`;
    }
  }

  function renderLearningsView() {
    const container = document.getElementById('learnings-content');
    if (!container) return;
    if (!state.learningsData) return;

    const { learnings, challenges } = state.learningsData;
    container.innerHTML = `
      <div class="row">
        <div class="col-md-6 mb-4">
          <h5 class="fw-bold mb-3">Curated Project Learnings (${learnings.length})</h5>
          ${
            learnings.length === 0
              ? '<div class="text-muted small">No approved learnings in .agent/learnings yet.</div>'
              : learnings
                  .map(
                    (l) => `
                <div class="card mb-3">
                  <div class="card-body">
                    <h6 class="fw-bold text-accent mb-2">${l.title}</h6>
                    <pre class="small text-light bg-dark p-2 rounded mb-0" style="white-space: pre-wrap;">${escapeHtml(l.content)}</pre>
                  </div>
                </div>
              `
                  )
                  .join('')
          }
        </div>
        <div class="col-md-6 mb-4">
          <h5 class="fw-bold mb-3">Recorded Diagnostic Challenges (${challenges.length})</h5>
          ${
            challenges.length === 0
              ? '<div class="text-muted small">No challenges in .agent/challenges yet.</div>'
              : challenges
                  .map(
                    (c) => `
                <div class="card mb-3">
                  <div class="card-body">
                    <h6 class="fw-bold text-warning mb-2">${c.title}</h6>
                    <pre class="small text-light bg-dark p-2 rounded mb-0" style="white-space: pre-wrap;">${escapeHtml(c.content)}</pre>
                  </div>
                </div>
              `
                  )
                  .join('')
          }
        </div>
      </div>
    `;
  }

  function renderDoctorView() {
    const container = document.getElementById('doctor-content');
    if (!container || !state.doctorData) return;
    const d = state.doctorData;

    container.innerHTML = `
      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span class="fw-bold">Platform Diagnostics</span>
          <span class="badge ${d.status === 'ok' ? 'bg-success' : 'bg-danger'}">${d.status.toUpperCase()}</span>
        </div>
        <div class="card-body">
          <table class="table table-sm">
            <thead>
              <tr>
                <th>Check</th>
                <th>Status</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              ${d.checks
                .map(
                  (c) => `
                <tr>
                  <td class="fw-semibold">${c.name}</td>
                  <td><span class="badge ${c.status === 'pass' ? 'bg-success' : 'bg-danger'}">${c.status}</span></td>
                  <td class="text-muted small">${JSON.stringify(c.details)}</td>
                </tr>
              `
                )
                .join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderEventTimeline() {
    const timelineEl = document.getElementById('event-timeline');
    if (!timelineEl) return;
    timelineEl.innerHTML = state.events
      .map(
        (ev) => `
        <div class="timeline-item">
          <div class="d-flex justify-content-between">
            <span class="fw-bold text-accent small">${ev.event_type}</span>
            <span class="text-muted small">${new Date(ev.timestamp).toLocaleTimeString()}</span>
          </div>
          <div class="text-muted small">${JSON.stringify(ev.payload)}</div>
        </div>
      `
      )
      .join('');
  }

  // 8. Navigation & Tabs
  window.switchTab = function (tabName) {
    state.activeTab = tabName;
    document.querySelectorAll('.nav-link').forEach((el) => {
      el.classList.toggle('active', el.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-pane').forEach((el) => {
      el.classList.toggle('d-none', el.id !== `tab-${tabName}`);
    });

    if (tabName === 'runs') loadRuns();
    if (tabName === 'diff' && state.selectedRunId) loadDiff(state.selectedRunId);
    if (tabName === 'plan' && state.selectedRun?.plan_id) loadPlan(state.selectedRun.plan_id);
    if (tabName === 'graph') loadGraph();
    if (tabName === 'learnings') loadLearnings();
    if (tabName === 'doctor') loadDoctor();
  };

  window.selectRun = function (runId) {
    selectRun(runId);
  };

  function showToast(title, message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} shadow-lg mb-2`;
    toast.style.minWidth = '250px';
    toast.innerHTML = `<div class="fw-bold">${title}</div><div class="small">${message}</div>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // 9. Startup Initialization
  window.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    loadRuns();
    loadDoctor();
  });
})();
