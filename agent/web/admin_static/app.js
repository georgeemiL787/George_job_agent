async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 503) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
      return;
    }
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? "";
}

function roleLink(role) {
  return `<a href="/admin/role?slug=${encodeURIComponent(role.slug)}">${role.title}</a>`;
}

// UI Helpers
function renderTierBadge(tier) {
  if (!tier) return '';
  const map = { elite: 'elite', strong: 'strong', medium: 'medium', adjacent: 'adjacent' };
  const type = map[tier.toLowerCase()] || 'adjacent';
  return `<span class="badge badge--${type}">${tier}</span>`;
}

function renderStatusPill(status) {
  if (!status) return '';
  const type = status.toLowerCase().replace(/\s+/g, '-');
  return `<span class="status-pill ${type}">${status}</span>`;
}

function renderScoreBar(score) {
  const num = parseInt(score) || 0;
  let color = 'var(--tier-adjacent)';
  if (num >= 80) color = 'var(--tier-elite)';
  else if (num >= 60) color = 'var(--tier-strong)';
  else if (num >= 40) color = 'var(--tier-medium)';

  return `
    <div class="score-bar-wrapper">
      <span class="score-number" style="color: ${color}">${num}</span>
      <div class="score-bar">
        <div class="score-bar__fill" style="width: ${num}%; background-color: ${color};"></div>
      </div>
    </div>
  `;
}

function renderRolesTable(target, roles) {
  if (!roles || roles.length === 0) {
    target.innerHTML = `<tr><td colspan="7" class="text-muted text-center" style="padding: 24px; text-align: center;">No roles found.</td></tr>`;
    return;
  }
  
  target.innerHTML = roles.map(role => `
    <tr>
      <td class="text-muted" style="font-weight: 600;">#${role.rank || "-"}</td>
      <td style="font-weight: 600; color: var(--text-main);">${role.company || ""}</td>
      <td>${roleLink(role)}</td>
      <td>${renderScoreBar(role.score)}</td>
      <td>${renderTierBadge(role.tier)}</td>
      <td>${renderStatusPill(role.status)}</td>
      ${target.id === 'roles-table' ? `<td><span class="text-muted" style="font-size: 0.85rem;">${role.source || ""}</span></td>` : ''}
    </tr>
  `).join("");
}

// Timer for runs
let runTimerInterval = null;
let runStartTime = null;

function updateRunTimer() {
  const timerEl = document.getElementById('job-timer');
  if (!timerEl || !runStartTime) return;
  
  const now = new Date();
  const diff = Math.floor((now - runStartTime) / 1000);
  const m = Math.floor(diff / 60).toString().padStart(2, '0');
  const s = (diff % 60).toString().padStart(2, '0');
  timerEl.textContent = `(${m}:${s})`;
}

async function loadDashboard() {
  const [status, job, schedule] = await Promise.all([
    api("/api/status"),
    api("/api/jobs/current"),
    api("/api/schedule")
  ]);

  // Run Panel
  const statusEl = document.getElementById("job-status");
  const containerEl = document.getElementById("run-status-container");
  const timerEl = document.getElementById("job-timer");
  const fullBtn = document.getElementById("run-full-btn");
  const dryBtn = document.getElementById("run-dry-btn");

  if (job.status === "running") {
    statusEl.innerHTML = `<span style="color: var(--accent-primary);">Running...</span>`;
    containerEl.innerHTML = `<div class="pulse-dot"></div> <span style="color: var(--accent-primary); font-weight: 600;">Running</span> <span id="job-timer" style="font-family: monospace; font-size: 0.9rem; margin-left: 8px;"></span>`;
    fullBtn.disabled = true;
    dryBtn.disabled = true;
    
    if (job.started_at && !runStartTime) {
      runStartTime = new Date(job.started_at);
      if (!runTimerInterval) runTimerInterval = setInterval(updateRunTimer, 1000);
    }
  } else {
    containerEl.innerHTML = `<span id="job-status" class="text-muted" style="font-weight: 500;">Idle</span>`;
    fullBtn.disabled = false;
    dryBtn.disabled = false;
    
    if (runTimerInterval) {
      clearInterval(runTimerInterval);
      runTimerInterval = null;
      runStartTime = null;
    }
    
    if (job.status === "error") {
      containerEl.innerHTML = `<span style="color: var(--status-error); font-weight: 600;">Error</span>`;
    }
  }

  // Scrapers
  const latest = status.latest_run;
  const scraperTarget = document.getElementById("scrapers");
  if (latest?.scrapers) {
    scraperTarget.innerHTML = Object.entries(latest.scrapers)
      .map(([name, stat]) => {
        let color = 'var(--status-success)';
        let icon = '<circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline>';
        if (stat.error) {
          color = 'var(--status-error)';
          icon = '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>';
        } else if (!stat.count) {
          color = 'var(--status-warning)';
          icon = '<circle cx="12" cy="12" r="10"></circle><line x1="8" y1="12" x2="16" y2="12"></line>';
        }
        
        return `
          <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px; background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border-left: 3px solid ${color};">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-weight: 600;">${name}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 16px;">
              <span class="badge" style="background: rgba(255,255,255,0.05);">${stat.count || 0} listings</span>
              <span style="color: ${color}; font-size: 0.85rem;">${stat.error ? stat.error : (stat.message || stat.status || "ok")}</span>
            </div>
          </div>
        `;
      })
      .join("");
  } else {
    scraperTarget.innerHTML = `<div class="text-muted" style="padding: 12px;">No run report yet.</div>`;
  }

  // Scheduler
  document.getElementById("schedule-enabled").value = schedule.enabled ? "on" : "off";
  document.getElementById("schedule-interval").value = String(schedule.interval_hours || 4);
  setText("next-run", schedule.next_run_time || "Not scheduled");
  
  // Stats
  const roles = status.roles || [];
  setText("stat-total", roles.length);
  setText("stat-drafts", roles.filter(r => r.status === 'Draft').length);
  setText("stat-ready", roles.filter(r => r.status === 'Ready').length);
  setText("stat-applied", roles.filter(r => r.status === 'Applied').length);

  // Top Roles Table
  renderRolesTable(document.getElementById("top-roles"), roles.slice(0, 5));
}

async function runAgent(dryRun) {
  try {
    await api(`/api/run?dry_run=${dryRun ? "true" : "false"}`, { method: "POST" });
    if (typeof showToast === 'function') showToast(dryRun ? 'Dry run started' : 'Full cycle started');
    // Start polling dashboard
    loadDashboard();
    const pollInterval = setInterval(async () => {
      const job = await api("/api/jobs/current");
      if (job.status !== 'running') {
        clearInterval(pollInterval);
        if (typeof showToast === 'function') {
          if (job.status === 'error') showToast('Run failed', 'error');
          else showToast('Run completed successfully');
        }
      }
      loadDashboard();
    }, 2000);
  } catch (e) {
    if (typeof showToast === 'function') showToast(e.message, 'error');
  }
}

async function saveSchedule() {
  const enabled = document.getElementById("schedule-enabled").value === "on";
  const interval_hours = Number(document.getElementById("schedule-interval").value);
  try {
    await api("/api/schedule", {
      method: "PUT",
      body: JSON.stringify({ enabled, interval_hours })
    });
    if (typeof showToast === 'function') showToast('Schedule updated');
    await loadDashboard();
  } catch (e) {
    if (typeof showToast === 'function') showToast(e.message, 'error');
  }
}

async function loadRoles() {
  const drafts = document.getElementById("drafts-only")?.checked;
  const applied = document.getElementById("include-applied")?.checked;
  const data = await api(`/api/roles?drafts_only=${drafts ? "true" : "false"}&include_applied=${applied ? "true" : "false"}`);
  renderRolesTable(document.getElementById("roles-table"), data.roles || []);
}

async function loadRoleDetail() {
  const slug = qs("slug");
  if (!slug) return;
  const role = await api(`/api/roles/${encodeURIComponent(slug)}`);
  
  setText("role-title", role.title);
  
  const metaContainer = document.getElementById("role-meta");
  metaContainer.innerHTML = `
    <div style="font-size: 1.1rem; font-weight: 600; color: var(--text-main); margin-right: auto;">${role.company}</div>
    ${renderScoreBar(role.score)}
    ${renderTierBadge(role.tier)}
    ${renderStatusPill(role.status)}
    <span class="badge" style="background: rgba(255,255,255,0.05); margin-left: 8px;">${role.source}</span>
  `;
  
  setText("role-fit", role.fit_summary || "No fit summary generated yet.");
  
  const apply = document.getElementById("apply-link");
  apply.href = role.apply_url;
  apply.querySelector('span').textContent = role.apply_url;
  
  document.getElementById("downloads").innerHTML = ["cv.pdf", "letter.pdf", "cv.tex", "letter.tex"]
    .map(name => {
      const isPdf = name.endsWith('.pdf');
      const icon = isPdf 
        ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>'
        : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>';
      return `
        <a class="status-pill" href="/api/files/${encodeURIComponent(slug)}/${name}" style="text-decoration: none; color: var(--text-main); cursor: pointer;" download>
          ${icon}
          ${name}
        </a>
      `;
    }).join("");
}

async function roleAction(action) {
  const slug = qs("slug");
  const body = action === "mark-applied"
    ? JSON.stringify({ date: document.getElementById("applied-date").value })
    : undefined;
    
  try {
    await api(`/api/roles/${encodeURIComponent(slug)}/${action}`, { method: "POST", body });
    if (typeof showToast === 'function') {
      const messages = {
        'tailor': 'CV tailored successfully',
        'approve': 'Role approved for application',
        'package': 'Artifacts packaged successfully',
        'mark-applied': 'Role marked as applied'
      };
      showToast(messages[action] || 'Action completed');
    }
    await loadRoleDetail();
  } catch (e) {
    if (typeof showToast === 'function') showToast(e.message, 'error');
  }
}

async function addRole(event) {
  event.preventDefault();
  const form = event.target;
  const body = Object.fromEntries(new FormData(form).entries());
  try {
    const result = await api("/api/roles", { method: "POST", body: JSON.stringify(body) });
    const slug = result.role?.slug;
    if (slug) {
      if (typeof showToast === 'function') showToast('Role added successfully');
      setTimeout(() => {
        window.location.href = `/admin/role?slug=${encodeURIComponent(slug)}`;
      }, 500);
    }
  } catch (e) {
    throw e;
  }
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" });
  window.location.href = "/";
}
