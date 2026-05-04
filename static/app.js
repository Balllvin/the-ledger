const statusEl = document.querySelector("#scan-status");
const refreshButton = document.querySelector("#refresh-button");
const emptyTemplate = document.querySelector("#empty-template");
const pageButtons = [...document.querySelectorAll(".tab-button")];
const pages = [...document.querySelectorAll(".page")];
const projectSelect = document.querySelector("#project-select");

let snapshot = null;
let selectedSeries = new Set(["total"]);

const SERIES_COLORS = ["#151515", "#1f6c9f", "#346538", "#956400", "#9f2f2d", "#5f4b8b", "#7a5b2e", "#3f6f72"];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function formatCompact(value) {
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
}

function formatBytes(value) {
  const number = Number(value || 0);
  if (number < 1024) return `${number} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = number / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function compactPath(value, max = 92) {
  const text = String(value || "");
  if (text.length <= max) return text;
  const side = Math.floor((max - 3) / 2);
  return `${text.slice(0, side)}...${text.slice(-side)}`;
}

function workspaceLabel(project) {
  const cwd = String(project?.cwd || "[unknown]");
  const name = String(project?.name || cwd);
  return `${name} - ${cwd}`;
}

function setHtml(selector, html) {
  document.querySelector(selector).innerHTML = html;
}

function emptyHtml(message = "No records found.") {
  const node = emptyTemplate.content.cloneNode(true);
  node.querySelector(".empty").textContent = message;
  const wrapper = document.createElement("div");
  wrapper.appendChild(node);
  return wrapper.innerHTML;
}

function metric(label, value, note = "") {
  return `
    <div class="metric">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${escapeHtml(value)}</div>
      <div class="note">${escapeHtml(note)}</div>
    </div>
  `;
}

function table(columns, rows) {
  if (!rows || !rows.length) return emptyHtml();
  const head = columns.map((column) => `<th class="${column.num ? "num" : ""}">${escapeHtml(column.label)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((column) => {
          const raw = column.value(row);
          const value = column.format ? column.format(raw, row) : raw;
          const klass = [column.num ? "num" : "", column.path ? "path-cell" : ""].filter(Boolean).join(" ");
          return `<td class="${klass}" title="${escapeHtml(raw)}">${escapeHtml(value)}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderRankList(items, valueFormatter = formatCompact) {
  if (!items || !items.length) return emptyHtml();
  return items
    .map(
      (item) => `
        <div class="rank-item">
          <div>
            <strong title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</strong>
            <span title="${escapeHtml(item.note || "")}">${escapeHtml(item.note || "")}</span>
          </div>
          <div class="rank-value">${escapeHtml(valueFormatter(item.value))}</div>
        </div>
      `,
    )
    .join("");
}

function renderKeyValueList(items) {
  if (!items || !items.length) return emptyHtml();
  return items
    .map(
      (item) => `
        <div class="source-item">
          <div>
            <strong title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</strong>
            <span title="${escapeHtml(item.note || "")}">${escapeHtml(item.note || "")}</span>
          </div>
          <div class="rank-value">${escapeHtml(item.value || "")}</div>
        </div>
      `,
    )
    .join("");
}

function seriesData(data) {
  const projects = ((data.codex || {}).state || {}).projects || {};
  const projectList = projects.projects || [];
  const total = { id: "total", name: "Total", cwd: "All projects", tokens: (data.overview || {}).codexStateTokens || 0, threads: (data.overview || {}).codexThreads || 0, days: projects.total || [] };
  return [total, ...projectList].slice(0, 9);
}

function renderLineChart(selector, series, days) {
  const container = document.querySelector(selector);
  if (!series.length || !days.length) {
    container.innerHTML = emptyHtml();
    return;
  }
  const width = 960;
  const height = selector === "#project-chart" ? 260 : 360;
  const pad = { left: 52, right: 18, top: 18, bottom: 38 };
  const dayIndex = new Map(days.map((day, index) => [day, index]));
  const maxValue = Math.max(
    1,
    ...series.flatMap((line) => (line.days || []).map((point) => Number(point.tokens || 0))),
  );
  const x = (day) => pad.left + (dayIndex.get(day) / Math.max(1, days.length - 1)) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (1 - Number(value || 0) / maxValue) * (height - pad.top - pad.bottom);
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const yy = pad.top + ratio * (height - pad.top - pad.bottom);
      const label = formatCompact(maxValue * (1 - ratio));
      return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" class="chart-grid" /><text x="8" y="${yy + 4}" class="chart-label">${label}</text>`;
    })
    .join("");
  const lines = series
    .map((line, index) => {
      const valuesByDay = new Map((line.days || []).map((point) => [point.day, Number(point.tokens || 0)]));
      const points = days.map((day) => `${x(day).toFixed(1)},${y(valuesByDay.get(day) || 0).toFixed(1)}`).join(" ");
      const color = line.color || SERIES_COLORS[index % SERIES_COLORS.length];
      return `<polyline class="chart-line" points="${points}" stroke="${color}" /><circle cx="${x(days[days.length - 1])}" cy="${y(valuesByDay.get(days[days.length - 1]) || 0)}" r="3.5" fill="${color}" />`;
    })
    .join("");
  const ticks = days
    .filter((_, index) => index === 0 || index === days.length - 1 || index % Math.ceil(days.length / 5) === 0)
    .map((day) => `<text x="${x(day)}" y="${height - 10}" class="chart-label" text-anchor="middle">${day.slice(5)}</text>`)
    .join("");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true">${grid}${lines}${ticks}</svg>`;
}

function renderUsagePage(data) {
  const overview = data.overview || {};
  setHtml(
    "#overview-grid",
    [
      metric("Total tokens", formatCompact(overview.codexStateTokens), `${formatNumber(overview.codexThreads)} runs`),
      metric("Projects", formatNumber((((data.codex || {}).state || {}).projects || {}).projects?.length || 0), "Codex workspaces"),
      metric("Lattice AI", formatCompact(overview.latticePipelineRows), `${formatCompact(overview.latticeCodexAuthRows)} Codex-auth`),
      metric("Logs", formatCompact(overview.codexLogRows), `${formatNumber(overview.codexCommandFailures)} command failures`),
    ].join(""),
  );
  const meta = data.meta || {};
  document.querySelector("#generated-at").textContent = `Generated ${formatDate(meta.generatedAt)} in ${meta.scanSeconds ?? "?"}s`;

  const allSeries = seriesData(data).map((line, index) => ({ ...line, color: SERIES_COLORS[index % SERIES_COLORS.length] }));
  if (![...selectedSeries].some((id) => allSeries.some((line) => line.id === id))) selectedSeries = new Set(["total"]);
  const days = (((data.codex || {}).state || {}).projects || {}).days || [];
  const selected = allSeries.filter((line) => selectedSeries.has(line.id));
  renderLineChart("#usage-chart", selected, days);
  setHtml(
    "#usage-legend",
    allSeries
      .map(
        (line) => `
          <label class="legend-item">
            <input type="checkbox" data-series-id="${escapeHtml(line.id)}" ${selectedSeries.has(line.id) ? "checked" : ""} />
            <span class="legend-swatch" style="background:${escapeHtml(line.color)}"></span>
            <span>
              <strong>${escapeHtml(line.name)}</strong>
              <small>${escapeHtml(formatCompact(line.tokens))} tokens</small>
            </span>
          </label>
        `,
      )
      .join(""),
  );
  document.querySelectorAll("[data-series-id]").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const id = event.currentTarget.dataset.seriesId;
      if (event.currentTarget.checked) selectedSeries.add(id);
      else selectedSeries.delete(id);
      if (selectedSeries.size === 0) selectedSeries.add("total");
      renderUsagePage(snapshot);
    });
  });
}

function currentProject(data) {
  const projects = (((data.codex || {}).state || {}).projects || {}).projects || [];
  if (!projects.length) return null;
  const selected = projectSelect.value || projects[0].id;
  return projects.find((project) => project.id === selected) || projects[0];
}

function renderProjectPage(data) {
  const projects = (((data.codex || {}).state || {}).projects || {}).projects || [];
  const previous = projectSelect.value;
  projectSelect.innerHTML = projects
    .map(
      (project) =>
        `<option value="${escapeHtml(project.id)}">${escapeHtml(workspaceLabel(project))} - ${escapeHtml(formatCompact(project.tokens))} tokens</option>`,
    )
    .join("");
  if (previous && projects.some((project) => project.id === previous)) projectSelect.value = previous;
  const project = currentProject(data);
  if (!project) {
    setHtml("#project-metrics", emptyHtml());
    return;
  }
  document.querySelector("#project-chart-title").textContent = project.name;
  setHtml(
    "#project-metrics",
    [
      metric("Tokens", formatCompact(project.tokens), project.cwd),
      metric("Runs", formatNumber(project.threads), "Codex threads"),
      metric("Peak day", formatCompact(Math.max(...project.days.map((day) => Number(day.tokens || 0)), 0)), "Highest daily total"),
      metric("Last active", project.recentThreads[0] ? formatDate(project.recentThreads[0].updated) : "", "Latest thread update"),
    ].join(""),
  );
  renderLineChart("#project-chart", [{ ...project, color: "#151515" }], (((data.codex || {}).state || {}).projects || {}).days || []);
  setHtml(
    "#project-top-runs",
    renderRankList(
      (project.topThreads || []).slice(0, 8).map((thread) => ({
        label: thread.title || "[untitled]",
        note: formatDate(thread.updated),
        value: thread.tokens,
      })),
    ),
  );
  setHtml(
    "#project-threads",
    table(
      [
        { label: "Updated", value: (row) => row.updated, format: formatDate },
        { label: "Title", value: (row) => row.title || "[untitled]" },
        { label: "Source", value: (row) => row.source || "" },
        { label: "Tokens", value: (row) => row.tokens, format: formatCompact, num: true },
      ],
      project.recentThreads || [],
    ),
  );
}

function renderSourceHealth(data) {
  const codexFs = ((data.codex || {}).filesystem || {});
  const lattice = data.lattice || {};
  const hermes = data.hermes || {};
  const discovery = data.discovery || {};
  setHtml(
    "#source-health",
    renderKeyValueList([
      { label: "Codex root", note: codexFs.root?.path || (data.codex || {}).root, value: codexFs.root?.exists ? "present" : "missing" },
      { label: "Discovered Codex roots", note: (discovery.scanRoots || []).join(" | "), value: formatNumber((discovery.codexRoots || []).length) },
      { label: "Codex-linked app roots", note: "Local folders with Codex markers", value: formatNumber((discovery.appRoots || []).length) },
      { label: "State SQLite", note: ((data.codex || {}).state || {}).database?.path, value: ((data.codex || {}).state || {}).available ? "readable" : "missing" },
      { label: "Log SQLite", note: ((data.codex || {}).logs || {}).database?.path, value: ((data.codex || {}).logs || {}).available ? "readable" : "missing" },
      { label: "Lattice DB", note: lattice.database?.path, value: lattice.databaseStats?.available ? "readable" : "missing" },
      { label: "Hermes WSL", note: hermes.root?.path || hermes.error || "", value: hermes.available ? "readable" : "unavailable" },
    ]),
  );
}

function renderSourcesPage(data) {
  renderSourceHealth(data);
  const db = ((data.lattice || {}).databaseStats || {});
  const core = db.core || {};
  const payload = db.codexAuthPayload || {};
  const discovery = data.discovery || {};
  setHtml(
    "#app-records-summary",
    [
      metric("App roots", formatCompact((discovery.appRoots || []).length), "Codex-linked folders"),
      metric("Codex roots", formatCompact((discovery.codexRoots || []).length), "Local candidates"),
      metric("Pipeline rows", formatCompact((db.tables || {}).document_pipeline_results), `${formatCompact(core.documents)} documents`),
      metric("Review suggestions", formatCompact(core.reviewSuggestions), "Codex field review"),
      metric("Parsed payloads", formatCompact(payload.parsedPayloads), `${formatCompact(payload.pagesAnalyzed)} pages analyzed`),
      metric("AI regions", formatCompact(payload.textRegions), `${formatCompact(payload.visualElements)} visual elements`),
    ].join(""),
  );
  const hermes = data.hermes || {};
  const status = document.querySelector("#hermes-status");
  status.textContent = hermes.available ? "Available" : "Unavailable";
  status.className = `tag ${hermes.available ? "green" : "red"}`;
  setHtml(
    "#hermes-summary",
    renderKeyValueList([
      { label: "Root", note: hermes.root?.path || hermes.error || "", value: hermes.root?.exists ? "present" : "missing" },
      { label: "Agent repo", note: hermes.agent?.path || "", value: hermes.agent?.exists ? "present" : "missing" },
      { label: "Git", note: hermes.git?.head || hermes.git?.error || "", value: hermes.git?.branch || "" },
      { label: "Cron output", note: `${formatNumber(hermes.cronOutput?.files || 0)} files`, value: hermes.available ? "checked" : "" },
    ]),
  );
  const fs = ((data.codex || {}).filesystem || {});
  const latticeFs = ((data.lattice || {}).filesystem || {});
  setHtml(
    "#stored-records",
    [
      ["Generated images", fs.generatedImages?.files, formatBytes(fs.generatedImages?.bytes)],
      ["Plugins", fs.plugins?.files, formatBytes(fs.plugins?.bytes)],
      ["Skills", fs.skills?.files, formatBytes(fs.skills?.bytes)],
      ["Lattice logs", latticeFs.dataLogs?.files, formatBytes(latticeFs.dataLogs?.bytes)],
    ]
      .map(([label, value, note]) => `<div class="record-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(formatCompact(value))}</strong><span>${escapeHtml(note)}</span></div>`)
      .join(""),
  );
}

function render(data) {
  snapshot = data;
  renderUsagePage(data);
  renderProjectPage(data);
  renderSourcesPage(data);
}

function switchPage(pageName) {
  pages.forEach((page) => page.classList.toggle("active", page.id === `page-${pageName}`));
  pageButtons.forEach((button) => button.classList.toggle("active", button.dataset.page === pageName));
}

async function loadSnapshot({ refresh = false } = {}) {
  refreshButton.disabled = true;
  statusEl.textContent = refresh ? "Refreshing records" : "Scanning records";
  try {
    const response = await fetch(`/api/snapshot${refresh ? "?refresh=1" : ""}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
    statusEl.textContent = `Scan complete in ${snapshot.meta?.scanSeconds ?? "?"}s`;
  } catch (error) {
    statusEl.textContent = "Scan failed";
    setHtml("#overview-grid", `<p class="error">${escapeHtml(error.message || error)}</p>`);
  } finally {
    refreshButton.disabled = false;
  }
}

pageButtons.forEach((button) => button.addEventListener("click", () => switchPage(button.dataset.page)));
projectSelect.addEventListener("change", () => snapshot && renderProjectPage(snapshot));
refreshButton.addEventListener("click", () => loadSnapshot({ refresh: true }));
loadSnapshot();
