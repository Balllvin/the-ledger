const statusEl = document.querySelector("#scan-status");
const refreshButton = document.querySelector("#refresh-button");
const emptyTemplate = document.querySelector("#empty-template");
const pageButtons = [...document.querySelectorAll(".tab-button")];
const pages = [...document.querySelectorAll(".page")];
const projectSelect = document.querySelector("#project-select");
const systemToggles = [...document.querySelectorAll("[data-system-toggle]")];

let snapshot = null;
let selectedSeries = new Set(["total"]);
let activeSystems = new Set(["codex", "opencode"]);
let swearSeriesVisible = new Set();
let swearLegendInitialized = false;
let snapshotEvents = null;

const SERIES_COLORS = ["#151515", "#1f6c9f", "#346538", "#956400", "#9f2f2d", "#5f4b8b", "#7a5b2e", "#3f6f72"];
const SWEAR_CATEGORY_COLORS = ["#9f2f2d", "#1f6c9f", "#346538", "#956400", "#5f4b8b", "#3f6f72", "#7a5b2e", "#2f3f58", "#8b3f62"];

function swearCategoryColor(category, categories) {
  const index = Math.max(0, categories.findIndex((item) => item.id === category.id));
  return SWEAR_CATEGORY_COLORS[index % SWEAR_CATEGORY_COLORS.length];
}

function selectedSwearCategories(categories) {
  return categories.filter((category) => swearSeriesVisible.has(`category:${category.id}`));
}

function selectedSwearMessages(row, selectedCategories) {
  if (!selectedCategories.length) return Number(row.swearMessages || 0);
  const selectedIds = new Set(selectedCategories.map((category) => category.id));
  if (!(row.categorySets || []).length) {
    const summed = selectedCategories.reduce((total, category) => total + Number(((row.categories || {})[category.id] || {}).messages || 0), 0);
    return Math.min(Number(row.messages || 0), summed);
  }
  return (row.categorySets || []).reduce((total, item) => {
    const categories = item.categories || [];
    return categories.some((category) => selectedIds.has(category)) ? total + Number(item.messages || 0) : total;
  }, 0);
}

function selectedSwearTotals(meter) {
  const categories = meter.categories || [];
  const selectedCategories = selectedSwearCategories(categories);
  const timeline = meter.timeline || [];
  const messages = timeline.reduce((total, row) => total + Number(row.messages || 0), 0) || Number(meter.directUserMessages || 0);
  const selectedMessages = selectedCategories.length
    ? timeline.reduce((total, row) => total + selectedSwearMessages(row, selectedCategories), 0)
    : Number(meter.swearIndexMessages || 0);
  const selectedOccurrences = selectedCategories.length
    ? selectedCategories.reduce((total, category) => total + Number(category.occurrences || 0), 0)
    : Number(meter.swearIndexOccurrences || 0);
  return {
    messages,
    selectedMessages,
    selectedOccurrences,
    rate: messages ? (selectedMessages / messages) * 100 : 0,
  };
}

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

function formatPercent(value) {
  return `${Number(value || 0).toFixed(Number(value || 0) >= 10 ? 1 : 2)}%`;
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
  const system = project?.system ? `${project.system} - ` : "";
  return `${system}${name} - ${cwd}`;
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

function hasSystem(name) {
  return activeSystems.has(name);
}

function selectedOverview(data) {
  const overview = data.overview || {};
  const codexProjects = (((data.codex || {}).state || {}).projects || {}).projects || [];
  const opencodeProjects = (((data.opencode || {}).database || {}).projects || {}).projects || [];
  const codex = hasSystem("codex")
    ? {
        tokens: overview.codexStateTokens || 0,
        runs: overview.codexThreads || 0,
        projects: codexProjects.length,
        logs: overview.codexLogRows || 0,
        failures: overview.codexCommandFailures || 0,
        automations: overview.codexAutomations || 0,
        automationRuns: overview.codexAutomationRuns || 0,
      }
    : {};
  const opencode = hasSystem("opencode")
    ? {
        tokens: overview.opencodeTokens || 0,
        runs: overview.opencodeSessions || 0,
        projects: overview.opencodeProjects || opencodeProjects.length,
        logs: overview.opencodeLogs || 0,
        failures: 0,
        automations: 0,
        automationRuns: 0,
        messages: overview.opencodeMessages || 0,
        costUsd: overview.opencodeCostUsd || 0,
      }
    : {};
  return {
    tokens: Number(codex.tokens || 0) + Number(opencode.tokens || 0),
    runs: Number(codex.runs || 0) + Number(opencode.runs || 0),
    projects: Number(codex.projects || 0) + Number(opencode.projects || 0),
    logs: Number(codex.logs || 0) + Number(opencode.logs || 0),
    failures: Number(codex.failures || 0),
    automations: Number(codex.automations || 0),
    automationRuns: Number(codex.automationRuns || 0),
    messages: Number(opencode.messages || 0),
    costUsd: Number(opencode.costUsd || 0),
  };
}

function prefixProject(project, system) {
  return { ...project, id: `${system}:${project.id}`, system };
}

function projectData(data) {
  const projects = ((data.codex || {}).state || {}).projects || {};
  const opencodeProjects = (((data.opencode || {}).database || {}).projects || {});
  const result = [];
  if (hasSystem("codex")) result.push(...(projects.projects || []).map((project) => prefixProject(project, "codex")));
  if (hasSystem("opencode")) result.push(...(opencodeProjects.projects || []).map((project) => prefixProject(project, "opencode")));
  return result.sort((a, b) => Number(b.tokens || 0) - Number(a.tokens || 0));
}

function mergedTotalDays(data) {
  const totals = [];
  if (hasSystem("codex")) totals.push(...((((data.codex || {}).state || {}).projects || {}).total || []));
  if (hasSystem("opencode")) totals.push(...(((((data.opencode || {}).database || {}).projects || {}).total) || []));
  const byDay = new Map();
  for (const point of totals) {
    const current = byDay.get(point.day) || { day: point.day, tokens: 0, threads: 0 };
    current.tokens += Number(point.tokens || 0);
    current.threads += Number(point.threads || 0);
    byDay.set(point.day, current);
  }
  return [...byDay.values()].sort((a, b) => String(a.day).localeCompare(String(b.day)));
}

function allDays(data) {
  return [...new Set([...mergedTotalDays(data).map((point) => point.day), ...projectData(data).flatMap((project) => (project.days || []).map((point) => point.day))])].sort();
}

function seriesData(data) {
  const projects = projectData(data);
  const totals = selectedOverview(data);
  const total = { id: "total", name: "Total", cwd: "Selected sources", tokens: totals.tokens, threads: totals.runs, days: mergedTotalDays(data) };
  return [total, ...projects].slice(0, 9);
}

function renderLineChart(selector, series, days) {
  const container = document.querySelector(selector);
  if (!series.length || !days.length) {
    container.innerHTML = emptyHtml();
    return;
  }
  const width = 960;
  const height = selector === "#project-chart" ? 230 : 300;
  const pad = { left: 52, right: 18, top: 18, bottom: 34 };
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
      return `<polyline class="chart-line" points="${points}" stroke="${color}" />`;
    })
    .join("");
  const chartPoints = [];
  const pointsByDay = new Map();
  const hoverPoints = series
    .map((line, index) => {
      const valuesByDay = new Map((line.days || []).map((point) => [point.day, Number(point.tokens || 0)]));
      const color = line.color || SERIES_COLORS[index % SERIES_COLORS.length];
      return days
        .map((day) => {
          const value = valuesByDay.get(day) || 0;
          const cx = x(day).toFixed(1);
          const cy = y(value).toFixed(1);
          const label = `${line.name} - ${day} - ${formatNumber(value)} tokens`;
          const point = { day, name: line.name, value, x: Number(cx), y: Number(cy), color, label };
          chartPoints.push(point);
          if (!pointsByDay.has(day)) pointsByDay.set(day, []);
          pointsByDay.get(day).push(point);
          return `
            <g class="chart-point-group" data-day="${escapeHtml(day)}">
              <circle class="chart-hit-point" cx="${cx}" cy="${cy}" r="11" tabindex="0" aria-label="${escapeHtml(label)}" data-tooltip="${escapeHtml(label)}">
              </circle>
              <circle class="chart-point" cx="${cx}" cy="${cy}" r="3" fill="${escapeHtml(color)}" />
            </g>
          `;
        })
        .join("");
    })
    .join("");
  const ticks = days
    .filter((_, index) => index === 0 || index === days.length - 1 || index % Math.ceil(days.length / 5) === 0)
    .map((day) => `<text x="${x(day)}" y="${height - 10}" class="chart-label" text-anchor="middle">${day.slice(5)}</text>`)
    .join("");
  const activeLine = `<line class="chart-active-line" x1="${pad.left}" x2="${pad.left}" y1="${pad.top}" y2="${height - pad.bottom}" />`;
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true">${grid}${activeLine}${lines}${hoverPoints}${ticks}</svg><div class="chart-tooltip" role="status"></div>`;
  const tooltip = container.querySelector(".chart-tooltip");
  const activeGuide = container.querySelector(".chart-active-line");
  const pointGroups = [...container.querySelectorAll(".chart-point-group")];
  const dayXs = days.map((day) => ({ day, x: x(day) }));
  const placeTooltip = (event) => {
    const rect = container.getBoundingClientRect();
    const left = Math.min(Math.max(event.clientX - rect.left + 12, 8), rect.width - tooltip.offsetWidth - 8);
    const top = Math.min(Math.max(event.clientY - rect.top - 38, 8), rect.height - tooltip.offsetHeight - 8);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };
  const setActiveDay = (day) => {
    const activeX = x(day);
    activeGuide.setAttribute("x1", activeX.toFixed(1));
    activeGuide.setAttribute("x2", activeX.toFixed(1));
    activeGuide.classList.add("visible");
    pointGroups.forEach((group) => group.classList.toggle("active", group.dataset.day === day));
  };
  const showTooltip = (event, html) => {
    tooltip.innerHTML = html;
    tooltip.classList.add("visible");
    if (event.clientX) placeTooltip(event);
  };
  const showColumnTooltip = (event) => {
    const svg = container.querySelector("svg");
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    const svgY = ((event.clientY - rect.top) / rect.height) * height;
    const nearest = dayXs.reduce(
      (best, item) => {
        const distance = Math.abs(item.x - svgX);
        return distance < best.distance ? { item, distance } : best;
      },
      { item: null, distance: Infinity },
    );
    const step = (width - pad.left - pad.right) / Math.max(1, days.length - 1);
    if (!nearest.item || svgX < pad.left - step / 2 || svgX > width - pad.right + step / 2 || svgY < pad.top - 14 || svgY > height - pad.bottom + 22) {
      hideTooltip();
      return;
    }
    const dayPoints = pointsByDay.get(nearest.item.day) || [];
    setActiveDay(nearest.item.day);
    showTooltip(
      event,
      `<strong>${escapeHtml(nearest.item.day)}</strong>${dayPoints
        .map((point) => `<span><i style="background:${escapeHtml(point.color)}"></i>${escapeHtml(point.name)}: ${escapeHtml(formatNumber(point.value))} tokens</span>`)
        .join("")}`,
    );
  };
  const hideTooltip = () => {
    tooltip.classList.remove("visible");
    activeGuide.classList.remove("visible");
    pointGroups.forEach((group) => group.classList.remove("active"));
  };
  container.addEventListener("mousemove", showColumnTooltip);
  container.addEventListener("mouseleave", hideTooltip);
  container.querySelectorAll(".chart-hit-point").forEach((point) => {
    point.addEventListener("focus", (event) => showTooltip(event, escapeHtml(event.currentTarget.dataset.tooltip)));
    point.addEventListener("blur", hideTooltip);
  });
}

function renderSwearMeterChart(selector, meter) {
  const container = document.querySelector(selector);
  const timeline = meter.timeline || [];
  const categories = meter.categories || [];
  const rows = [...(timeline || [])].filter((row) => row.day).sort((a, b) => String(a.day).localeCompare(String(b.day)));
  if (!rows.length) {
    container.innerHTML = emptyHtml();
    return;
  }
  const width = 960;
  const height = 300;
  const pad = { left: 46, right: 18, top: 18, bottom: 32 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const visibleCategories = selectedSwearCategories(categories);
  const selectedCounts = rows.map((row) => selectedSwearMessages(row, visibleCategories));
  const selectedRates = rows.map((row, index) => (Number(row.messages || 0) ? (selectedCounts[index] / Number(row.messages || 0)) * 100 : 0));
  const categoryCountMax = Math.max(
    1,
    ...rows.map((row) => visibleCategories.reduce((total, category) => total + Number(((row.categories || {})[category.id] || {}).messages || 0), 0)),
  );
  const maxBarValue = categoryCountMax;
  const maxRate = Math.max(1, ...selectedRates);
  const barStep = innerWidth / Math.max(1, rows.length);
  const barWidth = Math.max(3, Math.min(22, barStep * 0.62));
  const x = (index) => pad.left + index * barStep + barStep / 2;
  const yBar = (value) => pad.top + (1 - Number(value || 0) / maxBarValue) * innerHeight;
  const yRate = (value) => pad.top + (1 - Number(value || 0) / maxRate) * innerHeight;
  const grid = [0, 0.5, 1]
    .map((ratio) => {
      const yy = pad.top + ratio * innerHeight;
      return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" class="chart-grid" />`;
    })
    .join("");
  const bars = rows
    .map((row, index) => {
      let cursor = height - pad.bottom;
      return visibleCategories
        .map((category) => {
          const count = Number(((row.categories || {})[category.id] || {}).messages || 0);
          const barHeight = Math.max(0, height - pad.bottom - yBar(count));
          cursor -= barHeight;
          const xx = x(index) - barWidth / 2;
          const color = swearCategoryColor(category, categories);
          return `<rect class="swear-chart-bar" x="${xx.toFixed(1)}" y="${cursor.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" style="fill:${escapeHtml(color)}" opacity="0.78" />`;
        })
        .join("");
    })
    .join("");
  const linePoints = rows.map((row, index) => `${x(index).toFixed(1)},${yRate(selectedRates[index]).toFixed(1)}`).join(" ");
  const points = rows
    .map(
      (row, index) => `
        <g class="chart-point-group" data-day="${escapeHtml(row.day)}">
          <circle class="chart-hit-point" cx="${x(index).toFixed(1)}" cy="${yRate(selectedRates[index]).toFixed(1)}" r="11" tabindex="0" aria-label="${escapeHtml(`${row.day}: index ${formatPercent(selectedRates[index])} (${formatNumber(selectedCounts[index])})`)}"></circle>
          <circle class="swear-chart-point" cx="${x(index).toFixed(1)}" cy="${yRate(selectedRates[index]).toFixed(1)}" r="3" />
        </g>
      `,
    )
    .join("");
  const ticks = rows
    .map((row, index) => ({ row, index }))
    .filter(({ index }) => index === 0 || index === rows.length - 1 || index % Math.ceil(rows.length / 4) === 0)
    .map(({ row, index }) => `<text x="${x(index)}" y="${height - 8}" class="chart-label" text-anchor="middle">${escapeHtml(String(row.day).slice(5))}</text>`)
    .join("");
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" aria-hidden="true">
      ${grid}
      <text x="8" y="${pad.top + 4}" class="chart-label">${escapeHtml(formatCompact(maxBarValue))}</text>
      <text x="${width - 4}" y="${pad.top + 4}" class="chart-label" text-anchor="end">${escapeHtml(formatPercent(maxRate))}</text>
      <text x="8" y="${height - pad.bottom + 4}" class="chart-label">0</text>
      <line class="chart-active-line" x1="${pad.left}" x2="${pad.left}" y1="${pad.top}" y2="${height - pad.bottom}" />
      ${bars}
      <polyline class="chart-line swear-chart-line" points="${linePoints}" />
      ${points}
      ${ticks}
    </svg>
    <div class="chart-tooltip" role="status"></div>
  `;
  const tooltip = container.querySelector(".chart-tooltip");
  const activeGuide = container.querySelector(".chart-active-line");
  const pointGroups = [...container.querySelectorAll(".chart-point-group")];
  const dayXs = rows.map((row, index) => ({ day: row.day, x: x(index), row, rate: selectedRates[index], selectedCount: selectedCounts[index] }));
  const hideTooltip = () => {
    tooltip.classList.remove("visible");
    activeGuide.classList.remove("visible");
    pointGroups.forEach((group) => group.classList.remove("active"));
  };
  const showTooltip = (event, item) => {
    const parts = [];
    if (visibleCategories.length !== 1) {
      parts.push(`<span><i style="background:var(--red-ink)"></i>Index: ${escapeHtml(formatPercent(item.rate))} (${escapeHtml(formatNumber(item.selectedCount))})</span>`);
    }
    visibleCategories.forEach((category) => {
      const values = (item.row.categories || {})[category.id] || {};
      const messages = Number(values.messages || 0);
      if (messages > 0 || visibleCategories.length === 1) {
        const color = swearCategoryColor(category, categories);
        const percent = Number(item.row.messages || 0) ? (messages / Number(item.row.messages || 0)) * 100 : 0;
        parts.push(`<span><i style="background:${escapeHtml(color)}"></i>${escapeHtml(category.label)}: ${escapeHtml(formatPercent(percent))} (${escapeHtml(formatNumber(messages))})</span>`);
      }
    });
    if (!parts.length) {
      hideTooltip();
      return;
    }
    tooltip.innerHTML = `<strong>${escapeHtml(item.day)}</strong>${parts.join("")}`;
    tooltip.classList.add("visible");
    activeGuide.setAttribute("x1", item.x.toFixed(1));
    activeGuide.setAttribute("x2", item.x.toFixed(1));
    activeGuide.classList.add("visible");
    pointGroups.forEach((group) => group.classList.toggle("active", group.dataset.day === item.day));
    const rect = container.getBoundingClientRect();
    const eventX = event.clientX || rect.left + (item.x / width) * rect.width;
    const eventY = event.clientY || rect.top + pad.top;
    const left = Math.min(Math.max(eventX - rect.left + 12, 8), rect.width - tooltip.offsetWidth - 8);
    const top = Math.min(Math.max(eventY - rect.top - 38, 8), rect.height - tooltip.offsetHeight - 8);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };
  container.addEventListener("mousemove", (event) => {
    const svg = container.querySelector("svg");
    const rect = svg.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    const svgY = ((event.clientY - rect.top) / rect.height) * height;
    const nearest = dayXs.reduce(
      (best, item) => {
        const distance = Math.abs(item.x - svgX);
        return distance < best.distance ? { item, distance } : best;
      },
      { item: null, distance: Infinity },
    );
    const step = innerWidth / Math.max(1, rows.length - 1);
    if (!nearest.item || svgX < pad.left - step / 2 || svgX > width - pad.right + step / 2 || svgY < pad.top - 14 || svgY > height - pad.bottom + 22) {
      hideTooltip();
      return;
    }
    showTooltip(event, nearest.item);
  });
  container.addEventListener("mouseleave", hideTooltip);
  pointGroups.forEach((group) => {
    group.querySelector(".chart-hit-point").addEventListener("focus", (event) => {
      const item = dayXs.find((day) => day.day === group.dataset.day);
      if (item) showTooltip(event, item);
    });
    group.querySelector(".chart-hit-point").addEventListener("blur", hideTooltip);
  });
}

function renderUsagePage(data) {
  const overview = selectedOverview(data);
  setHtml(
    "#overview-grid",
    [
      metric("Total tokens", formatCompact(overview.tokens), `${formatNumber(overview.runs)} sessions`),
      metric("Projects", formatNumber(overview.projects), "Selected workspaces"),
      metric("Automations", formatCompact(overview.automations), `${formatCompact(overview.automationRuns)} Codex runs`),
      metric("Logs", formatCompact(overview.logs), `${formatNumber(overview.failures)} command failures`),
    ].join(""),
  );
  renderSwearMeter(data);
  const meta = data.meta || {};
  document.querySelector("#generated-at").textContent = `Generated ${formatDate(meta.generatedAt)} in ${meta.scanSeconds ?? "?"}s`;

  const allSeries = seriesData(data).map((line, index) => ({ ...line, color: SERIES_COLORS[index % SERIES_COLORS.length] }));
  if (![...selectedSeries].some((id) => allSeries.some((line) => line.id === id))) selectedSeries = new Set(["total"]);
  const days = allDays(data);
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

function renderSwearMeter(data) {
  const meter = (((data.codex || {}).sessions || {}).swearMeter || {});
  const visible = hasSystem("codex") && Number(meter.directUserMessages || 0) > 0;
  if (!visible) {
    setHtml("#swear-meter-summary", emptyHtml("No Codex user messages found."));
    return;
  }
  if (!swearLegendInitialized) {
    (meter.categories || []).slice(0, 3).forEach((category) => swearSeriesVisible.add(`category:${category.id}`));
    swearLegendInitialized = true;
  }
  const selectedTotals = selectedSwearTotals(meter);
  setHtml(
    "#swear-meter-summary",
    `
      <div class="mini-metrics">
        ${metric("Index", formatPercent(selectedTotals.rate), `${formatNumber(selectedTotals.selectedMessages)} of ${formatNumber(selectedTotals.messages)} user messages`)}
        ${metric("Hits", formatCompact(selectedTotals.selectedOccurrences), `${formatCompact(meter.swearIndexOccurrences)} total occurrences`)}
      </div>
      <div id="swear-meter-chart" class="chart swear-chart" role="img" aria-label="Swear index over time"></div>
      <div id="swear-meter-legend" class="legend-list swear-legend"></div>
    `,
  );
  renderSwearMeterChart("#swear-meter-chart", meter);
  renderSwearMeterLegend(meter);
}

function renderSwearMeterLegend(meter) {
  const categories = meter.categories || [];
  const categoryItems = categories.map((category) => ({
    id: `category:${category.id}`,
    label: category.label,
    value: category.messages,
    color: swearCategoryColor(category, categories),
    note: `${formatCompact(category.occurrences)} occurrences, ${formatCompact(category.score)} score`,
  }));
  setHtml(
    "#swear-meter-legend",
    categoryItems
      .map(
        (item) => `
          <label class="legend-item">
            <input type="checkbox" data-swear-series-id="${escapeHtml(item.id)}" ${swearSeriesVisible.has(item.id) ? "checked" : ""} />
            <span class="legend-swatch" style="background:${escapeHtml(item.color)}"></span>
            <span>
              <strong>${escapeHtml(item.label)}</strong>
            </span>
          </label>
        `,
      )
      .join(""),
  );
  document.querySelectorAll("[data-swear-series-id]").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const id = event.currentTarget.dataset.swearSeriesId;
      if (event.currentTarget.checked) swearSeriesVisible.add(id);
      else swearSeriesVisible.delete(id);
      if (snapshot) renderSwearMeter(snapshot);
    });
  });
}

function currentProject(data) {
  const projects = projectData(data);
  if (!projects.length) return null;
  const selected = projectSelect.value || projects[0].id;
  return projects.find((project) => project.id === selected) || projects[0];
}

function renderProjectPage(data) {
  const projects = projectData(data);
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
      metric("Runs", formatNumber(project.threads), `${project.system} sessions`),
      metric("Peak day", formatCompact(Math.max(...project.days.map((day) => Number(day.tokens || 0)), 0)), "Highest daily total"),
      metric("Last active", project.recentThreads[0] ? formatDate(project.recentThreads[0].updated) : "", "Latest thread update"),
    ].join(""),
  );
  renderLineChart("#project-chart", [{ ...project, color: "#151515" }], allDays(data));
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
        {
          label: "Swears",
          value: (row) => threadSwearMeter(data, row).swearIndexMessages || 0,
          format: (value) => formatNumber(value),
          num: true,
        },
        { label: "Tokens", value: (row) => row.tokens, format: formatCompact, num: true },
      ],
      project.recentThreads || [],
    ),
  );
}

function threadSwearMeter(data, thread) {
  if (!thread?.id) return {};
  return ((((data.codex || {}).sessions || {}).swearByThread || {})[thread.id]) || {};
}

function renderSourceHealth(data) {
  const codexFs = ((data.codex || {}).filesystem || {});
  const codexApp = ((data.codex || {}).desktopApp || {});
  const appDb = ((data.codex || {}).appDatabase || {});
  const lattice = data.lattice || {};
  const hermes = data.hermes || {};
  const hermesLocal = hermes.local || {};
  const hermesWsl = hermes.wsl || {};
  const opencode = data.opencode || {};
  const opencodeRoots = opencode.roots || {};
  const opencodeDb = opencode.database || {};
  const discovery = data.discovery || {};
  setHtml(
    "#source-health",
    renderKeyValueList([
      { label: "Codex root", note: codexFs.root?.path || (data.codex || {}).root, value: codexFs.root?.exists ? "present" : "missing" },
      { label: "Discovered Codex roots", note: (discovery.scanRoots || []).join(" | "), value: formatNumber((discovery.codexRoots || []).length) },
      { label: "Codex desktop app", note: codexApp.root?.path || "", value: codexApp.available ? "readable" : "missing" },
      { label: "Codex app database", note: appDb.database?.path || "", value: appDb.available ? "readable" : "missing" },
      { label: "Codex-linked app roots", note: "Local folders with Codex markers", value: formatNumber((discovery.appRoots || []).length) },
      { label: "State SQLite", note: ((data.codex || {}).state || {}).database?.path, value: ((data.codex || {}).state || {}).available ? "readable" : "missing" },
      { label: "Log SQLite", note: ((data.codex || {}).logs || {}).database?.path, value: ((data.codex || {}).logs || {}).available ? "readable" : "missing" },
      { label: "OpenCode data", note: opencodeRoots.data?.path || "", value: opencodeRoots.data?.exists ? "present" : "missing" },
      { label: "OpenCode database", note: opencodeDb.database?.path || "", value: opencodeDb.available ? "readable" : "missing" },
      { label: "OpenCode desktop app", note: opencodeRoots.desktop?.path || "", value: opencodeRoots.desktop?.exists ? "present" : "missing" },
      { label: "OpenCode CLI", note: opencode.cli?.binary?.path || "", value: opencode.cli?.binary?.exists ? opencode.version || "present" : "missing" },
      { label: "Lattice DB", note: lattice.database?.path, value: lattice.databaseStats?.available ? "readable" : "missing" },
      { label: "Hermes local", note: hermesLocal.root?.path || "", value: hermesLocal.available ? "readable" : "missing" },
      { label: "Hermes WSL", note: hermesWsl.root?.path || hermesWsl.error || "", value: hermesWsl.available ? "readable" : "unavailable" },
    ]),
  );
}

function renderSourcesPage(data) {
  renderSourceHealth(data);
  const db = ((data.lattice || {}).databaseStats || {});
  const core = db.core || {};
  const payload = db.codexAuthPayload || {};
  const discovery = data.discovery || {};
  const opencodeDb = ((data.opencode || {}).database || {});
  setHtml(
    "#app-records-summary",
    [
      metric("App roots", formatCompact((discovery.appRoots || []).length), "Codex-linked folders"),
      metric("Codex roots", formatCompact((discovery.codexRoots || []).length), "Local candidates"),
      metric("Codex app roots", formatCompact((discovery.codexAppRoots || []).length), "Desktop app candidates"),
      metric("OpenCode roots", formatCompact((discovery.opencodeRoots || []).length), "CLI + app candidates"),
      metric("Hermes roots", formatCompact((discovery.hermesRoots || []).length), "Local agent candidates"),
      metric("OpenCode sessions", formatCompact((opencodeDb.tables || {}).session), `${formatCompact(((opencodeDb.messages || {}).tokens || {}).total)} tokens`),
      metric("Pipeline rows", formatCompact((db.tables || {}).document_pipeline_results), `${formatCompact(core.documents)} documents`),
      metric("Review suggestions", formatCompact(core.reviewSuggestions), "Codex field review"),
      metric("Parsed payloads", formatCompact(payload.parsedPayloads), `${formatCompact(payload.pagesAnalyzed)} pages analyzed`),
      metric("AI regions", formatCompact(payload.textRegions), `${formatCompact(payload.visualElements)} visual elements`),
    ].join(""),
  );
  const hermes = data.hermes || {};
  const hermesLocal = hermes.local || {};
  const hermesState = hermesLocal.state || hermes.state || {};
  const hermesSessions = hermesState.sessions || {};
  const status = document.querySelector("#hermes-status");
  status.textContent = hermes.available ? "Available" : "Unavailable";
  status.className = `tag ${hermes.available ? "green" : "red"}`;
  setHtml(
    "#hermes-summary",
    renderKeyValueList([
      { label: "Root", note: hermesLocal.root?.path || hermes.root?.path || hermes.error || "", value: hermes.available ? "present" : "missing" },
      { label: "Auth", note: hermesLocal.auth?.path || hermes.auth?.path || "", value: (hermesLocal.auth || hermes.auth)?.exists ? "present" : "missing" },
      { label: "Codex auth", note: hermesLocal.codexAuth?.path || hermes.codexAuth?.path || "", value: (hermesLocal.codexAuth || hermes.codexAuth)?.exists ? "present" : "missing" },
      { label: "State DB", note: hermesState.database?.path || "", value: hermesState.available ? "readable" : "missing" },
      { label: "Sessions", note: `${formatCompact(hermesSessions.inputTokens || 0)} in / ${formatCompact(hermesSessions.outputTokens || 0)} out`, value: formatNumber(hermesSessions.total || 0) },
      { label: "Git", note: hermes.git?.head || hermes.git?.error || "", value: hermes.git?.branch || "" },
      { label: "Session files", note: `${formatNumber((hermesLocal.sessions || hermes.sessions)?.files || 0)} files`, value: hermes.available ? "checked" : "" },
    ]),
  );
  const fs = ((data.codex || {}).filesystem || {});
  const codexApp = ((data.codex || {}).desktopApp || {});
  const appDb = ((data.codex || {}).appDatabase || {});
  const opencode = data.opencode || {};
  const opencodeLogs = opencode.logs || {};
  const opencodeStorage = opencode.storage || {};
  const latticeFs = ((data.lattice || {}).filesystem || {});
  setHtml(
    "#stored-records",
    [
      ["Generated images", fs.generatedImages?.files, formatBytes(fs.generatedImages?.bytes)],
      ["Plugins", fs.plugins?.files, formatBytes(fs.plugins?.bytes)],
      ["Skills", fs.skills?.files, formatBytes(fs.skills?.bytes)],
      ["Automations", appDb.automations?.total, `${formatCompact(appDb.automationRuns?.total)} runs`],
      ["Codex app cache", codexApp.cache?.files, formatBytes(codexApp.cache?.bytes)],
      ["OpenCode logs", Number(opencodeLogs.cli?.files || 0) + Number(opencodeLogs.app?.files || 0), formatBytes(Number(opencodeLogs.cli?.bytes || 0) + Number(opencodeLogs.app?.bytes || 0))],
      ["OpenCode diffs", opencodeStorage.sessionDiffs?.files, formatBytes(opencodeStorage.sessionDiffs?.bytes)],
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

function updateSystemFilters() {
  activeSystems = new Set(systemToggles.filter((input) => input.checked).map((input) => input.dataset.systemToggle));
  if (activeSystems.size === 0) {
    const codexToggle = systemToggles.find((input) => input.dataset.systemToggle === "codex");
    if (codexToggle) codexToggle.checked = true;
    activeSystems = new Set(["codex"]);
  }
  selectedSeries = new Set(["total"]);
  if (snapshot) render(snapshot);
}

function switchPage(pageName) {
  pages.forEach((page) => page.classList.toggle("active", page.id === `page-${pageName}`));
  pageButtons.forEach((button) => button.classList.toggle("active", button.dataset.page === pageName));
}

async function loadSnapshot({ refresh = false } = {}) {
  refreshButton.disabled = true;
  refreshButton.classList.toggle("is-loading", refresh);
  refreshButton.setAttribute("aria-busy", refresh ? "true" : "false");
  const originalLabel = refreshButton.textContent;
  if (refresh) refreshButton.textContent = "Loading";
  if (statusEl) statusEl.textContent = refresh ? "Refreshing records" : "Scanning records";
  try {
    const response = await fetch(`/api/snapshot${refresh ? "?refresh=1" : ""}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
    if (statusEl) statusEl.textContent = `Scan complete in ${snapshot.meta?.scanSeconds ?? "?"}s`;
  } catch (error) {
    if (statusEl) statusEl.textContent = "Scan failed";
    setHtml("#overview-grid", `<p class="error">${escapeHtml(error.message || error)}</p>`);
  } finally {
    refreshButton.textContent = originalLabel;
    refreshButton.classList.remove("is-loading");
    refreshButton.setAttribute("aria-busy", "false");
    refreshButton.disabled = false;
  }
}

function refreshSnapshotStream() {
  if (!window.EventSource) {
    loadSnapshot({ refresh: true });
    return;
  }
  if (snapshotEvents) snapshotEvents.close();
  refreshButton.disabled = true;
  refreshButton.classList.add("is-loading");
  refreshButton.setAttribute("aria-busy", "true");
  refreshButton.textContent = "Loading";
  document.querySelector("#generated-at").textContent = "Refreshing local records";
  snapshotEvents = new EventSource("/api/snapshot/events?refresh=1");
  snapshotEvents.addEventListener("status", (event) => {
    const payload = JSON.parse(event.data);
    document.querySelector("#generated-at").textContent = payload.message || "Refreshing local records";
  });
  snapshotEvents.addEventListener("complete", (event) => {
    render(JSON.parse(event.data));
    snapshotEvents.close();
    snapshotEvents = null;
    refreshButton.textContent = "Refresh";
    refreshButton.classList.remove("is-loading");
    refreshButton.setAttribute("aria-busy", "false");
    refreshButton.disabled = false;
  });
  snapshotEvents.addEventListener("error", (event) => {
    if (event.data) {
      const payload = JSON.parse(event.data);
      setHtml("#overview-grid", `<p class="error">${escapeHtml(payload.message || "Scan failed")}</p>`);
    }
    snapshotEvents.close();
    snapshotEvents = null;
    refreshButton.textContent = "Refresh";
    refreshButton.classList.remove("is-loading");
    refreshButton.setAttribute("aria-busy", "false");
    refreshButton.disabled = false;
  });
}

pageButtons.forEach((button) => button.addEventListener("click", () => switchPage(button.dataset.page)));
projectSelect.addEventListener("change", () => snapshot && renderProjectPage(snapshot));
systemToggles.forEach((input) => input.addEventListener("change", updateSystemFilters));
refreshButton.addEventListener("click", refreshSnapshotStream);
loadSnapshot();
