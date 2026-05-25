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

function renderRolesTable(target, roles) {
  target.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Rank</th><th>Score</th><th>Tier</th><th>Status</th>
          <th>Company</th><th>Role</th><th>Source</th>
        </tr>
      </thead>
      <tbody>
        ${roles.map(role => `
          <tr>
            <td>${role.rank || ""}</td>
            <td>${role.score || 0}</td>
            <td>${role.tier || ""}</td>
            <td>${role.status || ""}</td>
            <td>${role.company || ""}</td>
            <td>${roleLink(role)}</td>
            <td>${role.source || ""}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

async function loadDashboard() {
  const [status, job, schedule] = await Promise.all([
    api("/api/status"),
    api("/api/jobs/current"),
    api("/api/schedule")
  ]);

  setText("job-status", `${job.status}${job.started_at ? ` since ${job.started_at}` : ""}`);
  const latest = status.latest_run;
  const scraperTarget = document.getElementById("scrapers");
  if (latest?.scrapers) {
    scraperTarget.innerHTML = Object.entries(latest.scrapers)
      .map(([name, stat]) => `<div>${name}: ${stat.count || 0} listings [${stat.status || "unknown"}] ${stat.message || stat.error || ""}</div>`)
      .join("");
  } else {
    scraperTarget.textContent = "No run report yet.";
  }

  document.getElementById("schedule-enabled").value = schedule.enabled ? "on" : "off";
  document.getElementById("schedule-interval").value = String(schedule.interval_hours || 4);
  setText("next-run", schedule.next_run_time || "Not scheduled");
  renderRolesTable(document.getElementById("top-roles"), status.roles || []);
}

async function runAgent(dryRun) {
  await api(`/api/run?dry_run=${dryRun ? "true" : "false"}`, { method: "POST" });
  await loadDashboard();
}

async function saveSchedule() {
  const enabled = document.getElementById("schedule-enabled").value === "on";
  const interval_hours = Number(document.getElementById("schedule-interval").value);
  await api("/api/schedule", {
    method: "PUT",
    body: JSON.stringify({ enabled, interval_hours })
  });
  await loadDashboard();
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
  setText("role-title", `${role.company} -- ${role.title}`);
  setText("role-meta", `${role.score}/100 ${role.tier} | ${role.status} | ${role.source}`);
  setText("role-fit", role.fit_summary || "");
  const apply = document.getElementById("apply-link");
  apply.href = role.apply_url;
  apply.textContent = role.apply_url;
  document.getElementById("downloads").innerHTML = ["cv.pdf", "letter.pdf", "cv.tex", "letter.tex"]
    .map(name => `<a class="button secondary" href="/api/files/${encodeURIComponent(slug)}/${name}">${name}</a>`)
    .join(" ");
}

async function roleAction(action) {
  const slug = qs("slug");
  const body = action === "mark-applied"
    ? JSON.stringify({ date: document.getElementById("applied-date").value })
    : undefined;
  await api(`/api/roles/${encodeURIComponent(slug)}/${action}`, { method: "POST", body });
  await loadRoleDetail();
}

async function addRole(event) {
  event.preventDefault();
  const form = event.target;
  const body = Object.fromEntries(new FormData(form).entries());
  const result = await api("/api/roles", { method: "POST", body: JSON.stringify(body) });
  const slug = result.role?.slug;
  if (slug) {
    window.location.href = `/admin/role?slug=${encodeURIComponent(slug)}`;
  }
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" });
  window.location.href = "/";
}
