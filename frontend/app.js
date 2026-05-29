const state = {
  dashboard: null,
  activeTopic: "all",
  activeTopicData: null,
  newsFilter: "",
  showOnlyBookmarks: false,
  loadingQuestion: false,
  aiEnabled: false,
  recentQueries: [],
  bookmarks: new Map(),
  knownUrls: new Set(),
  newItemCount: 0,
  autoRefreshTimerId: null,
  marketRefreshTimerId: null,
  lastPrices: new Map(),
};

const AUTO_REFRESH_MS = 5 * 60 * 1000;

const topicOrder = ["all", "thoi_su", "kinh_te", "cong_nghe", "the_gioi", "the_thao", "giai_tri", "suc_khoe"];
const topicMeta = {
  all: { label: "Tổng hợp", icon: "layout-grid" },
  thoi_su: { label: "Thời sự", icon: "newspaper" },
  kinh_te: { label: "Kinh tế", icon: "chart-column" },
  cong_nghe: { label: "Công nghệ", icon: "cpu" },
  the_gioi: { label: "Thế giới", icon: "globe" },
  the_thao: { label: "Thể thao", icon: "trophy" },
  giai_tri: { label: "Giải trí", icon: "clapperboard" },
  suc_khoe: { label: "Sức khỏe", icon: "heart-pulse" },
};

// localStorage keys, kept short and namespaced so we can recognize them in
// devtools without polluting the storage tab too much.
const LS_KEYS = {
  theme: "tnai.theme",
  recentQueries: "tnai.recent",
  bookmarks: "tnai.bookmarks",
};
const RECENT_QUERIES_LIMIT = 8;
const BOOKMARK_LIMIT = 200;

const el = {
  healthPill: document.getElementById("health-pill"),
  refreshBtn: document.getElementById("refresh-btn"),
  themeToggle: document.getElementById("theme-toggle"),
  queryForm: document.getElementById("query-form"),
  queryInput: document.getElementById("query-input"),
  quickChips: document.getElementById("quick-chips"),
  topicTabs: document.getElementById("topic-tabs"),
  newsList: document.getElementById("news-list"),
  newsFilterInput: document.getElementById("news-filter-input"),
  newsFilterStats: document.getElementById("news-filter-stats"),
  bookmarksToggle: document.getElementById("bookmarks-toggle"),
  bookmarksCount: document.getElementById("bookmarks-count"),
  priceList: document.getElementById("price-list"),
  vnPriceList: document.getElementById("vn-price-list"),
  vnGoldCompare: document.getElementById("vn-gold-compare"),
  exportPricesBtn: document.getElementById("export-prices-btn"),
  briefText: document.getElementById("brief-text"),
  answerBox: document.getElementById("answer-box"),
  answerMeta: document.getElementById("answer-meta"),
  metricTopics: document.getElementById("metric-topics"),
  metricArticles: document.getElementById("metric-articles"),
  metricSources: document.getElementById("metric-sources"),
  metricUpdated: document.getElementById("metric-updated"),
  newsTemplate: document.getElementById("news-item-template"),
  priceTemplate: document.getElementById("price-item-template"),
  vnPriceTemplate: document.getElementById("vn-price-item-template"),
  sourceTemplate: document.getElementById("source-item-template"),
  weatherList: document.getElementById("weather-list"),
  stocksList: document.getElementById("stocks-list"),
  cryptoList: document.getElementById("crypto-list"),
};

function setHealth(text, kind = "") {
  el.healthPill.textContent = text;
  el.healthPill.className = `status-pill ${kind}`.trim();
}

function formatTime(iso) {
  if (!iso) return "--:--";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--:--";
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  }).format(date);
}

function formatRelative(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  const diffHours = Math.round(diffMinutes / 60);
  const diffDays = Math.round(diffHours / 24);
  if (Math.abs(diffMinutes) < 60) {
    return `${Math.abs(diffMinutes)} phút ${diffMinutes <= 0 ? "trước" : "nữa"}`;
  }
  if (Math.abs(diffHours) < 24) {
    return `${Math.abs(diffHours)} giờ ${diffHours <= 0 ? "trước" : "nữa"}`;
  }
  return `${Math.abs(diffDays)} ngày ${diffDays <= 0 ? "trước" : "nữa"}`;
}

function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function renderTopics(topics) {
  el.topicTabs.innerHTML = "";
  const map = new Map(topics.map((topic) => [topic.key, topic]));

  topicOrder.forEach((key) => {
    if (!map.has(key)) return;
    const meta = topicMeta[key];
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `topic-tab${state.activeTopic === key ? " active" : ""}`;
    btn.dataset.topic = key;
    btn.innerHTML = `<i data-lucide="${meta.icon}"></i><span>${meta.label}</span>`;
    btn.addEventListener("click", () => {
      state.activeTopic = key;
      renderTopics(topics);
      renderNews(map.get(key));
    });
    el.topicTabs.appendChild(btn);
  });
}

function stripVnAccents(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
}

function renderNews(topic) {
  state.activeTopicData = topic || null;
  if (!topic) {
    el.newsList.innerHTML = `<div class="empty-state">Không có dữ liệu tin.</div>`;
    if (el.newsFilterStats) el.newsFilterStats.textContent = "";
    return;
  }

  const items = topic.items || [];
  const filterRaw = (state.newsFilter || "").trim();
  const filter = stripVnAccents(filterRaw);
  const onlyBookmarked = state.showOnlyBookmarks;

  let sourceItems = items;
  if (onlyBookmarked) {
    // Show all bookmarked articles from localStorage.
    // Enrich with data from current feed if available (for old bookmarks that only stored URL).
    const feedMap = new Map((items || []).map((item) => [item.url, item]));
    sourceItems = [...state.bookmarks.values()].map((saved) => {
      const fromFeed = feedMap.get(saved.url);
      return {
        ...saved,
        title: saved.title || (fromFeed && fromFeed.title) || saved.url || "Bài đã lưu",
        summary: saved.summary || (fromFeed && fromFeed.summary) || "",
        source: saved.source || (fromFeed && fromFeed.source) || "",
        thumbnail: saved.thumbnail || (fromFeed && fromFeed.thumbnail) || "",
        published_label: saved.published_label || (fromFeed && fromFeed.published_label) || "",
      };
    });
  }

  const filtered = sourceItems.filter((item) => {
    if (!filter) return true;
    const haystack = stripVnAccents(
      `${item.title || ""} ${item.summary || ""} ${item.source || ""}`,
    );
    return haystack.includes(filter);
  });

  if (el.newsFilterStats) {
    const parts = [];
    if (filterRaw || onlyBookmarked) {
      parts.push(`${filtered.length}/${items.length} bài`);
    } else if (items.length) {
      parts.push(`${items.length} bài`);
    }
    if (onlyBookmarked) parts.push("đã lưu");
    el.newsFilterStats.textContent = parts.join(" · ");
  }

  if (!items.length) {
    el.newsList.innerHTML = `<div class="empty-state">Chưa có bài mới cho chủ đề này.</div>`;
    return;
  }
  if (!filtered.length) {
    const msg = onlyBookmarked
      ? "Chưa có tin nào được lưu trong chủ đề này."
      : `Không có bài nào khớp từ khóa "${filterRaw}".`;
    el.newsList.innerHTML = `<div class="empty-state">${msg}</div>`;
    return;
  }

  el.newsList.innerHTML = "";
  filtered.forEach((item) => {
    const node = el.newsTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".source-pill").textContent = item.source || topic.label;
    node.querySelector(".time-pill").textContent = item.published_label || formatRelative(item.published_at);
    const link = node.querySelector(".news-title");
    link.textContent = item.title || "";
    link.href = item.url || "#";
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openReader(item.url, item.title);
    });
    node.querySelector(".news-summary").textContent = item.summary || "Không có mô tả.";

    const thumb = node.querySelector(".news-thumb");
    if (thumb && item.thumbnail) {
      thumb.src = item.thumbnail;
      thumb.alt = item.title || "";
      thumb.hidden = false;
      thumb.addEventListener("error", () => { thumb.hidden = true; });
    }

    const bookmarkBtn = node.querySelector(".bookmark-btn");
    if (bookmarkBtn) {
      const isSaved = state.bookmarks.has(item.url);
      bookmarkBtn.classList.toggle("active", isSaved);
      bookmarkBtn.title = isSaved ? "Bỏ lưu tin" : "Lưu tin";
      bookmarkBtn.setAttribute("aria-pressed", String(isSaved));
      bookmarkBtn.dataset.url = item.url || "";
      bookmarkBtn.addEventListener("click", (event) => {
        event.preventDefault();
        toggleBookmark(item);
      });
    }
    el.newsList.appendChild(node);
  });

  // Pagination controls.
  const existingPagination = el.newsList.querySelector(".pagination");
  if (existingPagination) existingPagination.remove();

  const total = topic.total || filtered.length;
  const perPage = topic.limit || 20;
  const totalPages = Math.ceil(total / perPage);
  const currentPage = Math.floor((topic.offset || 0) / perPage) + 1;

  if (totalPages > 1) {
    const pagination = document.createElement("div");
    pagination.className = "pagination";

    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "pagination-btn";
    prevBtn.innerHTML = `<i data-lucide="chevron-left"></i>`;
    prevBtn.disabled = currentPage <= 1;
    prevBtn.addEventListener("click", () => goToPage(topic, currentPage - 1));
    pagination.appendChild(prevBtn);

    const maxVisible = 7;
    const pages = buildPageNumbers(currentPage, totalPages, maxVisible);
    pages.forEach((p) => {
      if (p === "...") {
        const dots = document.createElement("span");
        dots.className = "pagination-dots";
        dots.textContent = "...";
        pagination.appendChild(dots);
      } else {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `pagination-btn${p === currentPage ? " active" : ""}`;
        btn.textContent = String(p);
        btn.addEventListener("click", () => goToPage(topic, p));
        pagination.appendChild(btn);
      }
    });

    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "pagination-btn";
    nextBtn.innerHTML = `<i data-lucide="chevron-right"></i>`;
    nextBtn.disabled = currentPage >= totalPages;
    nextBtn.addEventListener("click", () => goToPage(topic, currentPage + 1));
    pagination.appendChild(nextBtn);

    const info = document.createElement("span");
    info.className = "pagination-info";
    info.textContent = `Trang ${currentPage}/${totalPages} · ${total} bài`;
    pagination.appendChild(info);

    // "Go to page" input.
    const goToForm = document.createElement("form");
    goToForm.className = "pagination-goto";
    goToForm.innerHTML = `<input type="number" min="1" max="${totalPages}" placeholder="Trang..." class="pagination-goto-input"><button type="submit" class="pagination-btn">Đi</button>`;
    goToForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = goToForm.querySelector("input");
      const page = parseInt(input.value, 10);
      if (page >= 1 && page <= totalPages) goToPage(topic, page);
    });
    pagination.appendChild(goToForm);

    el.newsList.appendChild(pagination);
  }

  lucide.createIcons();
}

function buildPageNumbers(current, total, maxVisible) {
  if (total <= maxVisible) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages = [];
  pages.push(1);
  let start = Math.max(2, current - 1);
  let end = Math.min(total - 1, current + 1);
  if (current <= 3) { start = 2; end = Math.min(total - 1, maxVisible - 2); }
  if (current >= total - 2) { end = total - 1; start = Math.max(2, total - maxVisible + 3); }
  if (start > 2) pages.push("...");
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < total - 1) pages.push("...");
  pages.push(total);
  return pages;
}

async function goToPage(currentTopic, page) {
  const perPage = currentTopic.limit || 20;
  const offset = (page - 1) * perPage;
  try {
    const response = await fetch(`/api/news/${currentTopic.key}?offset=${offset}&limit=${perPage}`);
    const data = await response.json();
    if (!data.items) return;
    state.activeTopicData = data;
    renderNews(data);
    // Scroll news list into view.
    el.newsList.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    console.error("Pagination failed:", error);
  }
}

function renderSparkline(container, history, options = {}) {
  if (!container) return;
  container.innerHTML = "";
  const points = (history || []).filter(
    (point) => point && Number.isFinite(Number(point.value)),
  );
  if (points.length < 2) {
    container.classList.add("price-spark-empty");
    container.textContent = points.length === 1
      ? "Đang thu thập dữ liệu lịch sử..."
      : "Chưa đủ dữ liệu cho biểu đồ 7 ngày.";
    return;
  }

  // Filter out flat lines where all values are identical (no useful chart).
  // Exception: still show for items with very few points (will accumulate over time).
  const uniqueValues = new Set(points.map((p) => Number(p.value)));
  if (uniqueValues.size === 1 && points.length > 10) {
    container.classList.add("price-spark-empty");
    container.textContent = `${formatTick([...uniqueValues][0])} (ổn định)`;
    return;
  }
  container.classList.remove("price-spark-empty");

  const width = 220;
  const height = 48;
  const padX = 2;
  const padY = 4;
  const values = points.map((p) => Number(p.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || Math.abs(max) * 0.001 || 1;

  const xStep = (width - padX * 2) / (points.length - 1);
  const path = points
    .map((point, idx) => {
      const x = padX + idx * xStep;
      const y = padY + (height - padY * 2) * (1 - (Number(point.value) - min) / span);
      return `${idx === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const lastValue = values[values.length - 1];
  const firstValue = values[0];
  const trendUp = lastValue >= firstValue;
  const stroke = trendUp ? "var(--positive, #4ade80)" : "var(--negative, #f87171)";
  const fillId = `spark-grad-${Math.random().toString(36).slice(2, 8)}`;
  const areaPath = `${path} L${(padX + xStep * (points.length - 1)).toFixed(1)} ${height - padY} L${padX} ${height - padY} Z`;

  const firstTs = points[0].ts ? new Date(points[0].ts * 1000) : null;
  const lastTs = points[points.length - 1].ts
    ? new Date(points[points.length - 1].ts * 1000)
    : null;
  const rangeLabel = firstTs && lastTs
    ? `${firstTs.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })} → ${lastTs.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })}`
    : "";

  const formatTick = options.formatTick || ((v) => v.toLocaleString("vi-VN"));
  const minLabel = formatTick(min);
  const maxLabel = formatTick(max);

  container.innerHTML = `
    <svg class="spark-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="${fillId}" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="${stroke}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="${stroke}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path d="${areaPath}" fill="url(#${fillId})"/>
      <path d="${path}" fill="none" stroke="${stroke}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>
    <div class="spark-meta">
      <span>${rangeLabel}</span>
      <span>${minLabel} – ${maxLabel}</span>
    </div>
  `;

  // Click to open detailed chart
  container.style.cursor = "pointer";
  container.title = "Bấm để xem biểu đồ chi tiết";
  container.addEventListener("click", () => {
    openDetailChart(options.label || "", points, { formatTick, stroke });
  });
}

// --- Detailed chart modal ----------------------------------------------------

function openDetailChart(label, points, options = {}) {
  const { formatTick = (v) => v.toLocaleString("vi-VN"), stroke = "#4ade80" } = options;
  let modal = document.getElementById("chart-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "chart-modal";
    modal.className = "chart-modal";
    modal.innerHTML = `
      <div class="chart-backdrop"></div>
      <div class="chart-panel">
        <div class="chart-header">
          <h3 class="chart-title"></h3>
          <button class="chart-close icon-btn" type="button" title="Đóng"><i data-lucide="x"></i></button>
        </div>
        <div class="chart-body">
          <div class="chart-tooltip" hidden></div>
          <svg class="chart-svg"></svg>
          <div class="chart-x-axis"></div>
        </div>
        <div class="chart-footer"></div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.querySelector(".chart-backdrop").addEventListener("click", closeDetailChart);
    modal.querySelector(".chart-close").addEventListener("click", closeDetailChart);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("open")) closeDetailChart();
    });
    lucide.createIcons();
  }

  modal.querySelector(".chart-title").textContent = label || "Biểu đồ giá";

  const values = points.map((p) => Number(p.value));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || Math.abs(max) * 0.001 || 1;
  const lastValue = values[values.length - 1];
  const firstValue = values[0];
  const change = lastValue - firstValue;
  const changePct = firstValue ? ((change / firstValue) * 100).toFixed(2) : "0.00";
  const trendUp = change >= 0;
  const lineColor = trendUp ? "var(--positive, #4ade80)" : "var(--negative, #f87171)";

  const width = 640;
  const height = 280;
  const padX = 50;
  const padY = 20;
  const chartW = width - padX * 2;
  const chartH = height - padY * 2;

  // Build path
  const coords = points.map((point, idx) => {
    const x = padX + (idx / (points.length - 1)) * chartW;
    const y = padY + chartH * (1 - (Number(point.value) - min) / span);
    return { x, y, value: Number(point.value), ts: point.ts };
  });
  const pathD = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");
  const areaD = `${pathD} L${coords[coords.length - 1].x.toFixed(1)} ${padY + chartH} L${padX} ${padY + chartH} Z`;

  // Y-axis ticks (5 levels)
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const value = min + (span * i) / 4;
    const y = padY + chartH * (1 - i / 4);
    return { value, y };
  });

  const gradId = `chart-grad-${Math.random().toString(36).slice(2, 8)}`;
  const svgContent = `
    <defs>
      <linearGradient id="${gradId}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.2"/>
        <stop offset="100%" stop-color="${lineColor}" stop-opacity="0"/>
      </linearGradient>
    </defs>
    ${yTicks.map((t) => `
      <line x1="${padX}" y1="${t.y.toFixed(1)}" x2="${width - padX}" y2="${t.y.toFixed(1)}" stroke="var(--line)" stroke-dasharray="4 4" stroke-width="0.5"/>
      <text x="${padX - 6}" y="${t.y.toFixed(1)}" text-anchor="end" dominant-baseline="middle" fill="var(--muted)" font-size="10">${formatTick(t.value)}</text>
    `).join("")}
    <path d="${areaD}" fill="url(#${gradId})"/>
    <path d="${pathD}" fill="none" stroke="${lineColor}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${coords[coords.length - 1].x.toFixed(1)}" cy="${coords[coords.length - 1].y.toFixed(1)}" r="4" fill="${lineColor}"/>
    <line class="chart-crosshair" x1="0" y1="${padY}" x2="0" y2="${padY + chartH}" stroke="var(--muted)" stroke-width="0.8" stroke-dasharray="3 3" opacity="0"/>
    <circle class="chart-dot" cx="0" cy="0" r="5" fill="${lineColor}" opacity="0"/>
  `;

  const svg = modal.querySelector(".chart-svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = svgContent;

  // X-axis labels
  const xAxis = modal.querySelector(".chart-x-axis");
  const xLabels = [0, Math.floor(points.length / 4), Math.floor(points.length / 2), Math.floor(points.length * 3 / 4), points.length - 1];
  xAxis.innerHTML = xLabels.map((idx) => {
    const ts = points[idx]?.ts;
    const date = ts ? new Date(ts * 1000) : null;
    const label = date ? date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
    return `<span>${label}</span>`;
  }).join("");

  // Footer stats
  const footer = modal.querySelector(".chart-footer");
  const sign = change >= 0 ? "+" : "";
  footer.innerHTML = `
    <span>Hiện tại: <strong>${formatTick(lastValue)}</strong></span>
    <span>Thay đổi: <strong style="color:${lineColor}">${sign}${formatTick(change)} (${sign}${changePct}%)</strong></span>
    <span>Thấp nhất: ${formatTick(min)}</span>
    <span>Cao nhất: ${formatTick(max)}</span>
    <span>${points.length} điểm dữ liệu</span>
  `;

  // Tooltip on hover
  const tooltip = modal.querySelector(".chart-tooltip");
  const crosshair = svg.querySelector(".chart-crosshair");
  const dot = svg.querySelector(".chart-dot");
  const chartBody = modal.querySelector(".chart-body");

  chartBody.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    // Account for padX in the SVG viewBox: the chart area starts at padX/width
    // of the rendered element and ends at (width-padX)/width.
    const padRatio = padX / width;
    const chartStartPx = rect.width * padRatio;
    const chartEndPx = rect.width * (1 - padRatio);
    const chartWidthPx = chartEndPx - chartStartPx;
    const clampedX = Math.max(0, Math.min(mouseX - chartStartPx, chartWidthPx));
    const ratio = clampedX / chartWidthPx;
    const idx = Math.round(ratio * (coords.length - 1));
    if (idx < 0 || idx >= coords.length) return;
    const c = coords[idx];

    crosshair.setAttribute("x1", c.x.toFixed(1));
    crosshair.setAttribute("x2", c.x.toFixed(1));
    crosshair.setAttribute("opacity", "1");
    dot.setAttribute("cx", c.x.toFixed(1));
    dot.setAttribute("cy", c.y.toFixed(1));
    dot.setAttribute("opacity", "1");

    const ts = points[idx]?.ts;
    const date = ts ? new Date(ts * 1000) : null;
    const dateStr = date ? date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
    tooltip.textContent = `${dateStr}  ·  ${formatTick(c.value)}`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(Math.max((c.x / width) * 100, 10), 90)}%`;
  });

  chartBody.addEventListener("mouseleave", () => {
    crosshair.setAttribute("opacity", "0");
    dot.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });

  modal.classList.add("open");
  document.body.style.overflow = "hidden";
  lucide.createIcons();
}

function closeDetailChart() {
  const modal = document.getElementById("chart-modal");
  if (modal) {
    modal.classList.remove("open");
    document.body.style.overflow = "";
  }
}

function renderPrices(cards) {
  el.priceList.innerHTML = "";
  cards.forEach((card) => {
    const node = el.priceTemplate.content.firstElementChild.cloneNode(true);
    const icon = node.querySelector(".price-icon i");
    icon.setAttribute("data-lucide", card.icon || "circle-dollar-sign");
    node.querySelector(".price-label").textContent = card.label || "";
    node.querySelector(".price-symbol").textContent = card.symbol || "";
    node.querySelector(".price-value").textContent = card.price_text || "Chưa có dữ liệu";
    node.querySelector(".price-unit").textContent = card.unit || "";

    const changeEl = node.querySelector(".price-change");
    const changeText = card.change_text || "";
    changeEl.textContent = changeText ? `Biến động: ${changeText}` : "Biến động: chưa có dữ liệu";
    changeEl.className = "price-change";
    if (typeof card.change === "number") {
      if (card.change > 0) changeEl.classList.add("positive");
      if (card.change < 0) changeEl.classList.add("negative");
    }

    node.querySelector(".price-updated").textContent = card.updated_at
      ? `Cập nhật: ${card.updated_at}`
      : "Cập nhật: chưa rõ";
    renderSparkline(node.querySelector(".price-spark"), card.history, {
      formatTick: (value) => fmtNumber(value, card.precision ?? 2),
      label: card.label || card.key || "",
    });

    // Flash if price changed since last render.
    flashPriceChange(node, card.key, card.price);

    el.priceList.appendChild(node);
  });
  lucide.createIcons();
}

// --- Article reader modal -----------------------------------------------------

async function openReader(url, fallbackTitle) {
  if (!url) return;
  showReaderModal(fallbackTitle || "Đang tải...", null, url);

  try {
    const response = await fetch("/api/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await response.json().catch(() => ({}));
    if (data.error || !data.paragraphs || !data.paragraphs.length) {
      showReaderModal(
        fallbackTitle || "Không đọc được",
        [`<p class="muted">Không trích xuất được nội dung. <a href="${url}" target="_blank" rel="noreferrer">Mở trong tab mới →</a></p>`],
        url,
      );
      return;
    }
    showReaderModal(
      data.title || fallbackTitle || "",
      data.paragraphs.map((p) => `<p>${escapeHtml(p)}</p>`),
      url,
      data.word_count,
    );
  } catch (error) {
    showReaderModal(
      fallbackTitle || "Lỗi",
      [`<p class="muted">Không kết nối được. <a href="${url}" target="_blank" rel="noreferrer">Mở trong tab mới →</a></p>`],
      url,
    );
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function showReaderModal(title, contentHtmlParts, url, wordCount) {
  let modal = document.getElementById("reader-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "reader-modal";
    modal.className = "reader-modal";
    modal.innerHTML = `
      <div class="reader-backdrop"></div>
      <div class="reader-panel">
        <div class="reader-header">
          <h2 class="reader-title"></h2>
          <div class="reader-actions">
            <a class="reader-open-link chip" target="_blank" rel="noreferrer">
              <i data-lucide="external-link"></i><span>Mở gốc</span>
            </a>
            <button class="reader-close icon-btn" type="button" title="Đóng (Esc)">
              <i data-lucide="x"></i>
            </button>
          </div>
        </div>
        <div class="reader-meta"></div>
        <div class="reader-body"></div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.querySelector(".reader-backdrop").addEventListener("click", closeReader);
    modal.querySelector(".reader-close").addEventListener("click", closeReader);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal.classList.contains("open")) {
        closeReader();
      }
    });
    lucide.createIcons();
  }

  modal.querySelector(".reader-title").textContent = title || "";
  modal.querySelector(".reader-open-link").href = url || "#";
  modal.querySelector(".reader-meta").textContent = wordCount
    ? `~${Math.ceil(wordCount / 200)} phút đọc · ${wordCount} từ`
    : "";

  const body = modal.querySelector(".reader-body");
  if (contentHtmlParts === null) {
    body.innerHTML = `<div class="reader-loading"><div class="skeleton-line skeleton-line-title"></div><div class="skeleton-line skeleton-line-text"></div><div class="skeleton-line skeleton-line-text short"></div><div class="skeleton-line skeleton-line-text"></div></div>`;
  } else {
    body.innerHTML = contentHtmlParts.join("");
  }

  modal.classList.add("open");
  document.body.style.overflow = "hidden";
  lucide.createIcons();
}

function closeReader() {
  const modal = document.getElementById("reader-modal");
  if (modal) {
    modal.classList.remove("open");
    document.body.style.overflow = "";
  }
}

function renderWeather(cities) {
  if (!el.weatherList) return;
  if (!cities || !cities.length) {
    el.weatherList.innerHTML = `<div class="empty-state">Chưa lấy được thời tiết.</div>`;
    return;
  }
  el.weatherList.innerHTML = "";
  cities.forEach((city) => {
    const forecast = (city.forecast || []).map((day) => `
      <div class="forecast-day">
        <span class="forecast-date">${day.day_label || day.date || ""}</span>
        <i data-lucide="${day.icon || "cloud"}"></i>
        <span class="forecast-temps">${day.temp_min != null ? Math.round(day.temp_min) : "?"}° / ${day.temp_max != null ? Math.round(day.temp_max) : "?"}°</span>
        ${day.rain_prob != null ? `<span class="forecast-rain"><i data-lucide="droplets"></i>${day.rain_prob}%</span>` : ""}
      </div>
    `).join("");

    const card = document.createElement("article");
    card.className = "weather-card";
    card.innerHTML = `
      <div class="weather-head">
        <span class="weather-icon"><i data-lucide="${city.icon || "cloud"}"></i></span>
        <div>
          <h4 class="weather-city">${city.city || ""}</h4>
          <p class="weather-cond">${city.label || ""}</p>
        </div>
      </div>
      <div class="weather-temp">${city.temperature_text || ""}</div>
      <ul class="weather-stats">
        <li><i data-lucide="thermometer"></i><span>Cảm giác ${city.feels_like_text || "—"}</span></li>
        <li><i data-lucide="droplets"></i><span>Ẩm ${city.humidity_text || "—"}</span></li>
        <li><i data-lucide="wind"></i><span>Gió ${city.wind_text || "—"}</span></li>
      </ul>
      ${forecast ? `<div class="forecast-row">${forecast}</div>` : ""}
    `;
    el.weatherList.appendChild(card);
  });
  lucide.createIcons();
}

function renderStocks(cards) {
  renderMarketCards(el.stocksList, cards, { showSparkline: true });
}

function renderCrypto(cards) {
  renderMarketCards(el.cryptoList, cards, { showSparkline: true });
}

function flashPriceChange(node, key, newPrice) {
  if (!key || newPrice == null) return;
  const prev = state.lastPrices.get(key);
  state.lastPrices.set(key, newPrice);
  if (prev == null || prev === newPrice) return;
  const direction = newPrice > prev ? "flash-up" : "flash-down";
  node.classList.add(direction);
  setTimeout(() => node.classList.remove(direction), 2000);
}

function renderMarketCards(container, cards, options = {}) {
  if (!container) return;
  if (!cards || !cards.length) {
    container.innerHTML = `<div class="empty-state">Chưa có dữ liệu.</div>`;
    return;
  }
  container.innerHTML = "";
  cards.forEach((card) => {
    const change = Number(card.change_percent || 0);
    const trend = change > 0 ? "up" : change < 0 ? "down" : "flat";
    const node = document.createElement("article");
    node.className = `market-card market-trend-${trend}`;
    node.innerHTML = `
      <div class="market-head">
        <span class="market-icon"><i data-lucide="${card.icon || "circle"}"></i></span>
        <div>
          <h4 class="market-label">${card.label || ""}</h4>
          <p class="market-symbol">${card.symbol || card.provider || ""}</p>
        </div>
      </div>
      <div class="market-price">${card.price_text || "—"}</div>
      <div class="market-change">${card.change_text || ""}</div>
      ${card.unit ? `<div class="market-unit">${card.unit}</div>` : ""}
      <div class="market-spark"></div>
    `;
    container.appendChild(node);
    flashPriceChange(node, card.key, card.price);
    if (options.showSparkline && card.history && card.history.length >= 2) {
      const sparkContainer = node.querySelector(".market-spark");
      renderSparkline(sparkContainer, card.history, {
        formatTick: (value) => Number(value).toLocaleString("vi-VN", { maximumFractionDigits: 2 }),
        label: card.label || card.key || "",
      });
    }
  });
  lucide.createIcons();
}

function renderAnswer(data) {
  el.answerMeta.textContent = `${data.intent || "general"} · ${formatTime(data.generated_at)}`;
  el.answerBox.innerHTML = "";

  const tabs = createAnswerTabs(data);
  el.answerBox.appendChild(tabs);
  lucide.createIcons();
}

function createAnswerTabs(data) {
  const wrapper = document.createElement("div");
  wrapper.className = "answer-tabs";

  const sources = Array.isArray(data.sources) ? data.sources : [];
  const sourceCount = sources.length;

  const buttonsRow = document.createElement("div");
  buttonsRow.className = "answer-tab-buttons";
  buttonsRow.setAttribute("role", "tablist");

  const panelsRow = document.createElement("div");
  panelsRow.className = "answer-tab-panels";

  const definitions = [
    {
      id: "summary",
      label: "Tóm tắt",
      icon: "sparkles",
      build: () => buildSummaryPanel(data),
    },
    {
      id: "sources",
      label: `Nguồn${sourceCount ? ` (${sourceCount})` : ""}`,
      icon: "link",
      build: () => buildSourcesPanel(sources),
    },
    {
      id: "raw",
      label: "Raw",
      icon: "code",
      build: () => buildRawPanel(data),
    },
  ];

  definitions.forEach((def, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `answer-tab${idx === 0 ? " active" : ""}`;
    btn.setAttribute("role", "tab");
    btn.dataset.tab = def.id;
    btn.innerHTML = `<i data-lucide="${def.icon}"></i><span>${def.label}</span>`;
    btn.addEventListener("click", () => activateTab(wrapper, def.id));
    buttonsRow.appendChild(btn);

    const panel = def.build();
    panel.classList.add("answer-tab-panel");
    panel.dataset.panel = def.id;
    if (idx !== 0) panel.hidden = true;
    panelsRow.appendChild(panel);
  });

  wrapper.appendChild(buttonsRow);
  wrapper.appendChild(panelsRow);
  return wrapper;
}

function activateTab(wrapper, id) {
  wrapper.querySelectorAll(".answer-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === id);
  });
  wrapper.querySelectorAll(".answer-tab-panel").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== id;
  });
  lucide.createIcons();
}

function buildSummaryPanel(data) {
  const panel = document.createElement("div");
  const text = document.createElement("pre");
  text.className = "answer-summary";
  text.textContent = data.answer || "Chưa có câu trả lời.";
  panel.appendChild(text);
  return panel;
}

function buildSourcesPanel(sources) {
  const panel = document.createElement("div");
  if (!sources.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Chưa có nguồn cho câu trả lời này.";
    panel.appendChild(empty);
    return panel;
  }
  const list = document.createElement("ul");
  list.className = "answer-sources";
  sources.slice(0, 8).forEach((source) => {
    const node = el.sourceTemplate.content.firstElementChild.cloneNode(true);
    const link = node.querySelector(".source-link");
    link.textContent = source.title || source.domain || "Nguồn";
    link.href = source.url || "#";
    link.target = "_blank";
    link.rel = "noreferrer";
    node.querySelector(".source-snippet").textContent = source.snippet || "";
    list.appendChild(node);
  });
  panel.appendChild(list);
  return panel;
}

function buildRawPanel(data) {
  const panel = document.createElement("div");
  panel.className = "answer-raw";

  const toolbar = document.createElement("div");
  toolbar.className = "answer-raw-toolbar";

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "chip";
  copyBtn.innerHTML = `<i data-lucide="copy"></i><span>Sao chép JSON</span>`;
  toolbar.appendChild(copyBtn);

  const status = document.createElement("span");
  status.className = "answer-raw-status muted";
  toolbar.appendChild(status);

  const pre = document.createElement("pre");
  pre.className = "answer-raw-body";
  let pretty;
  try {
    pretty = JSON.stringify(data, null, 2);
  } catch (error) {
    pretty = String(data);
  }
  pre.textContent = pretty;

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(pretty);
      status.textContent = "Đã chép vào clipboard.";
    } catch (error) {
      status.textContent = "Trình duyệt chặn clipboard, hãy chọn thủ công.";
    }
    setTimeout(() => {
      status.textContent = "";
    }, 2500);
  });

  panel.appendChild(toolbar);
  panel.appendChild(pre);
  return panel;
}

function updateMetrics(dashboard) {
  const metrics = dashboard.metrics || {};
  el.metricTopics.textContent = metrics.topic_count ?? 0;
  el.metricArticles.textContent = metrics.article_count ?? 0;
  el.metricSources.textContent = metrics.source_count ?? 0;
  el.metricUpdated.textContent = formatTime(dashboard.generated_at);
  el.briefText.textContent = dashboard.brief || "Chưa có bản tóm tắt.";
}

function renderVnPrices(cards) {
  if (!el.vnPriceList) return;
  el.vnPriceList.innerHTML = "";
  if (!cards || !cards.length) {
    el.vnPriceList.innerHTML = `<div class="empty-state">Chưa lấy được giá Việt Nam.</div>`;
    return;
  }
  cards.forEach((card) => {
    const node = el.vnPriceTemplate.content.firstElementChild.cloneNode(true);
    const icon = node.querySelector(".price-icon i");
    icon.setAttribute("data-lucide", card.icon || "circle-dollar-sign");
    node.querySelector(".price-label").textContent = card.label || "";
    node.querySelector(".price-symbol").textContent = card.unit || "";
    node.querySelector(".price-value").textContent = card.price_text || "Chưa có dữ liệu";
    node.querySelector(".price-unit").textContent = "";
    const providerEl = node.querySelector(".price-provider");
    if (providerEl) {
      providerEl.textContent = card.provider || "";
      providerEl.style.display = card.provider ? "" : "none";
    }
    node.querySelector(".price-updated").textContent = card.updated_label
      ? `Cập nhật: ${card.updated_label}`
      : "Cập nhật: chưa rõ";
    renderSparkline(node.querySelector(".price-spark"), card.history, {
      formatTick: (value) => Number(value).toLocaleString("vi-VN"),
      label: card.label || card.key || "",
    });
    el.vnPriceList.appendChild(node);
  });
  lucide.createIcons();
}

function renderDashboard(dashboard) {
  state.dashboard = dashboard;
  updateMetrics(dashboard);
  const topics = dashboard.topics || [];
  renderTopics(topics);
  const active = topics.find((topic) => topic.key === state.activeTopic) || topics.find((topic) => topic.key === "all");
  renderNews(active);
  renderPrices(dashboard.prices?.cards || []);
  renderVnPrices(dashboard.prices?.vn_cards || []);
  renderGoldCompare(dashboard.prices?.vn_cards || []);
  renderWeather(dashboard.weather?.cities || []);
  renderStocks(dashboard.stocks?.cards || []);
  renderCrypto(dashboard.crypto?.cards || []);
  setHealth(state.aiEnabled ? "AI sẵn sàng" : "AI tắt", state.aiEnabled ? "ok" : "warn");
  lucide.createIcons();
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) {
      throw new Error(`Health failed: ${response.status}`);
    }
    const data = await response.json();
    state.aiEnabled = Boolean(data.ai_enabled);
    setHealth(state.aiEnabled ? "AI sẵn sàng" : "AI tắt", state.aiEnabled ? "ok" : "warn");
  } catch (error) {
    console.error(error);
    state.aiEnabled = false;
    setHealth("Không kiểm tra được AI", "err");
  }
}

async function loadDashboard(force = false, options = {}) {
  const { silent = false } = options;
  if (!silent) {
    setHealth("Đang tải dữ liệu", "warn");
    el.refreshBtn.disabled = true;
  }
  if (!state.dashboard && !silent) {
    renderSkeletons();
  }

  const forceParam = force ? "?force=1" : "";

  // Fire all requests in parallel — render each section as it arrives.
  const sections = [
    { url: `/api/health`, render: (data) => {
      state.aiEnabled = Boolean(data.ai_enabled);
      setHealth(state.aiEnabled ? "AI sẵn sàng" : "AI tắt", state.aiEnabled ? "ok" : "warn");
    }},
    { url: `/api/news/all${forceParam}`, render: (data) => {
      if (!state.dashboard) state.dashboard = {};
      state.dashboard.topics = [data];
      // Render the "all" topic immediately.
      renderTopics([data]);
      renderNews(data);
      // Update metrics with what we have so far.
      if (data.total) {
        el.metricArticles.textContent = data.total;
      }
      if (data.source_count) {
        el.metricSources.textContent = data.source_count;
      }
      if (data.summary) {
        el.briefText.textContent = data.summary;
      }
    }},
    { url: `/api/prices${forceParam}`, render: (data) => {
      if (!state.dashboard) state.dashboard = {};
      state.dashboard.prices = data;
      renderPrices(data.cards || []);
      renderVnPrices(data.vn_cards || []);
      renderGoldCompare(data.vn_cards || []);
    }},
    { url: `/api/crypto${forceParam}`, render: (data) => {
      if (!state.dashboard) state.dashboard = {};
      state.dashboard.crypto = data;
      renderCrypto(data.cards || []);
    }},
    { url: `/api/stocks${forceParam}`, render: (data) => {
      if (!state.dashboard) state.dashboard = {};
      state.dashboard.stocks = data;
      renderStocks(data.cards || []);
    }},
    { url: `/api/weather${forceParam}`, render: (data) => {
      if (!state.dashboard) state.dashboard = {};
      state.dashboard.weather = data;
      renderWeather(data.cities || []);
    }},
  ];

  // Load all remaining topics in background after "all" renders.
  const topicKeys = topicOrder.filter((k) => k !== "all");

  const promises = sections.map(async (section) => {
    try {
      const response = await fetch(section.url);
      const data = await response.json().catch(() => ({}));
      if (response.ok && !data.error) {
        section.render(data);
      }
    } catch (error) {
      // Individual section failure doesn't block others.
    }
  });

  // Also fetch individual topics for the tab switcher.
  const topicPromises = topicKeys.map(async (key) => {
    try {
      const response = await fetch(`/api/news/${key}${forceParam}`);
      const data = await response.json().catch(() => ({}));
      if (response.ok && !data.error) {
        if (!state.dashboard) state.dashboard = {};
        if (!state.dashboard.topicMap) state.dashboard.topicMap = {};
        state.dashboard.topicMap[key] = data;
      }
    } catch (error) {
      // skip
    }
  });

  await Promise.allSettled([...promises, ...topicPromises]);

  // After all loaded, rebuild topic tabs with full data.
  if (state.dashboard && state.dashboard.topicMap) {
    const allTopics = topicOrder.map((key) => {
      if (key === "all" && state.dashboard.topics && state.dashboard.topics[0]) {
        return state.dashboard.topics[0];
      }
      return state.dashboard.topicMap[key] || { key, label: topicMeta[key]?.label || key, items: [] };
    }).filter(Boolean);
    renderTopics(allTopics);
    // Update metrics.
    const totalArticles = allTopics.reduce((sum, t) => sum + (t.total || t.items?.length || 0), 0);
    const totalSources = allTopics.filter((t) => t.key !== "all").reduce((sum, t) => sum + (t.source_count || 0), 0);
    el.metricTopics.textContent = allTopics.filter((t) => t.key !== "all").length;
    el.metricArticles.textContent = totalArticles;
    el.metricSources.textContent = totalSources;
    el.metricUpdated.textContent = formatTime(new Date().toISOString());
  }

  // Track new items for badge.
  if (state.dashboard) {
    const newCount = countNewArticles(state.dashboard);
    if (silent && newCount > 0) {
      state.newItemCount = newCount;
      updateNewItemsBadge();
    } else {
      seedKnownUrls(state.dashboard);
      state.newItemCount = 0;
      updateNewItemsBadge();
    }
  }

  if (!silent) el.refreshBtn.disabled = false;
}

function collectArticleUrls(dashboard) {
  const urls = [];
  // From topicMap (new structure).
  if (dashboard?.topicMap) {
    for (const topic of Object.values(dashboard.topicMap)) {
      for (const item of topic.items || []) {
        if (item?.url) urls.push(item.url);
      }
    }
  }
  // From topics array (old structure / "all" topic).
  for (const topic of dashboard?.topics || []) {
    for (const item of topic.items || []) {
      if (item?.url) urls.push(item.url);
    }
  }
  return urls;
}

function seedKnownUrls(dashboard) {
  state.knownUrls = new Set(collectArticleUrls(dashboard));
}

function countNewArticles(dashboard) {
  if (!state.knownUrls.size) return 0;
  return collectArticleUrls(dashboard).filter((url) => !state.knownUrls.has(url)).length;
}

const ORIGINAL_TITLE = document.title;

function updateNewItemsBadge() {
  if (!el.refreshBtn) return;
  let badge = el.refreshBtn.querySelector(".new-items-badge");
  if (state.newItemCount > 0) {
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "new-items-badge";
      el.refreshBtn.appendChild(badge);
    }
    badge.textContent = state.newItemCount > 99 ? "99+" : String(state.newItemCount);
    el.refreshBtn.title = `Có ${state.newItemCount} tin mới — bấm để tải`;
    document.title = `(${state.newItemCount}) ${ORIGINAL_TITLE}`;
  } else {
    if (badge) badge.remove();
    el.refreshBtn.title = "Làm mới dữ liệu";
    document.title = ORIGINAL_TITLE;
  }
}

function renderSkeletons() {
  if (el.newsList) {
    el.newsList.innerHTML = Array.from({ length: 4 })
      .map(
        () => `
          <article class="news-card skeleton-card">
            <div class="news-card-head">
              <span class="skeleton-line skeleton-line-pill"></span>
              <span class="skeleton-line skeleton-line-pill"></span>
            </div>
            <div class="skeleton-line skeleton-line-title"></div>
            <div class="skeleton-line skeleton-line-text"></div>
            <div class="skeleton-line skeleton-line-text short"></div>
          </article>`,
      )
      .join("");
  }
  if (el.priceList) {
    el.priceList.innerHTML = Array.from({ length: 3 })
      .map(
        () => `
          <article class="price-card skeleton-card">
            <div class="skeleton-line skeleton-line-title"></div>
            <div class="skeleton-line skeleton-line-text short"></div>
            <div class="skeleton-line skeleton-line-text"></div>
          </article>`,
      )
      .join("");
  }
}

function startAutoRefresh() {
  stopAutoRefresh();
  // Full dashboard refresh every 5 minutes.
  state.autoRefreshTimerId = setInterval(() => {
    if (document.visibilityState === "hidden") return;
    loadDashboard(false, { silent: true });
  }, AUTO_REFRESH_MS);

  // Market data (prices, crypto, stocks) refresh every 60 seconds.
  state.marketRefreshTimerId = setInterval(() => {
    if (document.visibilityState === "hidden") return;
    refreshMarkets();
  }, 60_000);
}

function stopAutoRefresh() {
  if (state.autoRefreshTimerId !== null) {
    clearInterval(state.autoRefreshTimerId);
    state.autoRefreshTimerId = null;
  }
  if (state.marketRefreshTimerId !== null) {
    clearInterval(state.marketRefreshTimerId);
    state.marketRefreshTimerId = null;
  }
}

async function refreshMarkets() {
  try {
    const [pricesRes, cryptoRes, stocksRes] = await Promise.allSettled([
      fetch("/api/prices"),
      fetch("/api/crypto"),
      fetch("/api/stocks"),
    ]);
    if (pricesRes.status === "fulfilled" && pricesRes.value.ok) {
      const data = await pricesRes.value.json();
      renderPrices(data.cards || []);
      renderVnPrices(data.vn_cards || []);
    }
    if (cryptoRes.status === "fulfilled" && cryptoRes.value.ok) {
      const data = await cryptoRes.value.json();
      renderCrypto(data.cards || []);
    }
    if (stocksRes.status === "fulfilled" && stocksRes.value.ok) {
      const data = await stocksRes.value.json();
      renderStocks(data.cards || []);
    }
  } catch (error) {
    // Silent fail — markets will update on next cycle.
  }
}

async function askQuestion(question) {
  if (state.loadingQuestion) return;
  if (!question.trim()) {
    el.answerMeta.textContent = "";
    el.answerBox.innerHTML = `<p class="muted">Hãy nhập câu hỏi vào ô phía trên rồi bấm "Hỏi ngay".</p>`;
    el.queryInput.focus();
    return;
  }
  state.loadingQuestion = true;
  el.answerMeta.textContent = "Đang suy nghĩ...";
  el.answerBox.innerHTML = `<p class="muted">Đang lấy nguồn...</p>`;
  // Scroll to answer section so user sees the response appearing.
  const answerSection = el.answerBox.closest(".band");
  if (answerSection) answerSection.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.error) {
      const isRateLimited = response.status === 429 || data?.error === "rate_limited";
      const isOffline = data?.error === "offline";
      const message = data?.message
        || (isRateLimited
          ? `Bạn gửi quá nhanh, hãy chờ ${data?.retry_after ?? 30}s rồi thử lại.`
          : isOffline
            ? "Bạn đang offline. Đang dùng dữ liệu đã lưu."
            : `Yêu cầu không thành công (HTTP ${response.status}).`);
      el.answerMeta.textContent = isRateLimited
        ? "Đã giới hạn"
        : isOffline
          ? "Offline"
          : "Lỗi";
      el.answerBox.innerHTML = "";
      const note = document.createElement("p");
      note.className = isOffline ? "muted" : "answer-error";
      note.textContent = message;
      el.answerBox.appendChild(note);
      return;
    }
    renderAnswer(data);
  } catch (error) {
    console.error(error);
    el.answerMeta.textContent = "Lỗi";
    el.answerBox.innerHTML = `<p class="answer-error">Không kết nối được tới máy chủ.</p>`;
  } finally {
    state.loadingQuestion = false;
  }
}

// --- Theme manager -----------------------------------------------------------

function getStoredTheme() {
  try {
    return localStorage.getItem(LS_KEYS.theme);
  } catch (error) {
    return null;
  }
}

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "dark") {
    root.dataset.theme = "dark";
  } else {
    delete root.dataset.theme;
  }
  if (el.themeToggle) {
    const icon = el.themeToggle.querySelector("i");
    if (icon) {
      icon.setAttribute("data-lucide", theme === "dark" ? "sun" : "moon");
    }
    el.themeToggle.title = theme === "dark" ? "Chuyển sang theme sáng" : "Chuyển sang theme tối";
    lucide.createIcons();
  }
}

function initTheme() {
  const stored = getStoredTheme();
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = stored || (prefersDark ? "dark" : "light");
  applyTheme(theme);
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
  try {
    localStorage.setItem(LS_KEYS.theme, next);
  } catch (error) {
    /* private mode etc. — fall back to in-memory only */
  }
}

// --- Recent queries ----------------------------------------------------------

function loadRecentQueries() {
  try {
    const raw = localStorage.getItem(LS_KEYS.recentQueries);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, RECENT_QUERIES_LIMIT) : [];
  } catch (error) {
    return [];
  }
}

function saveRecentQueries(list) {
  try {
    localStorage.setItem(LS_KEYS.recentQueries, JSON.stringify(list));
  } catch (error) {
    /* ignore quota errors */
  }
}

function rememberQuery(query) {
  const trimmed = (query || "").trim();
  if (!trimmed) return;
  const without = state.recentQueries.filter(
    (item) => item.toLowerCase() !== trimmed.toLowerCase(),
  );
  state.recentQueries = [trimmed, ...without].slice(0, RECENT_QUERIES_LIMIT);
  saveRecentQueries(state.recentQueries);
  renderRecentChips();
}

function clearRecentQueries() {
  state.recentQueries = [];
  saveRecentQueries([]);
  renderRecentChips();
}

function renderRecentChips() {
  // Anchor recent chips at the end of the existing quick chips row, but keep
  // the static suggestions intact so the "preset" chips never disappear.
  if (!el.quickChips) return;
  el.quickChips.querySelectorAll("[data-recent]").forEach((node) => node.remove());
  const existingClear = el.quickChips.querySelector("[data-action='clear-recent']");
  if (existingClear) existingClear.remove();

  if (!state.recentQueries.length) return;

  state.recentQueries.forEach((query) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip chip-recent";
    button.dataset.recent = "1";
    button.dataset.query = query;
    button.title = query;
    button.innerHTML = `<i data-lucide="history"></i><span>${query.length > 32 ? query.slice(0, 30) + "…" : query}</span>`;
    el.quickChips.appendChild(button);
  });

  const clearBtn = document.createElement("button");
  clearBtn.type = "button";
  clearBtn.className = "chip chip-clear";
  clearBtn.dataset.action = "clear-recent";
  clearBtn.title = "Xoá lịch sử câu hỏi";
  clearBtn.innerHTML = `<i data-lucide="x"></i><span>Xoá lịch sử</span>`;
  el.quickChips.appendChild(clearBtn);

  lucide.createIcons();
}

// --- Bookmarks ---------------------------------------------------------------

function loadBookmarks() {
  try {
    const raw = localStorage.getItem(LS_KEYS.bookmarks);
    if (!raw) return new Map();
    const parsed = JSON.parse(raw);
    // Support both old format (array of URLs) and new format (array of objects).
    if (!Array.isArray(parsed)) return new Map();
    const map = new Map();
    for (const entry of parsed.slice(0, BOOKMARK_LIMIT)) {
      if (typeof entry === "string") {
        // Old format: just URL, no metadata.
        map.set(entry, { url: entry, title: "", summary: "", source: "", thumbnail: "", published_label: "" });
      } else if (entry && entry.url) {
        map.set(entry.url, entry);
      }
    }
    return map;
  } catch (error) {
    return new Map();
  }
}

function saveBookmarks() {
  try {
    const entries = [...state.bookmarks.values()].slice(0, BOOKMARK_LIMIT);
    localStorage.setItem(LS_KEYS.bookmarks, JSON.stringify(entries));
  } catch (error) {
    /* quota / private mode */
  }
}

function toggleBookmark(item) {
  if (!item || !item.url) return;
  if (state.bookmarks.has(item.url)) {
    state.bookmarks.delete(item.url);
  } else {
    // Store full article data so bookmarked items survive even if removed from feed.
    state.bookmarks.set(item.url, {
      url: item.url || "",
      title: item.title || item.url || "Bài đã lưu",
      summary: item.summary || "",
      source: item.source || "",
      thumbnail: item.thumbnail || "",
      published_label: item.published_label || "",
      published_at: item.published_at || "",
    });
  }
  saveBookmarks();
  refreshBookmarksButton();
  renderNews(state.activeTopicData);
}

function refreshBookmarksButton() {
  if (!el.bookmarksToggle) return;
  el.bookmarksToggle.classList.toggle("active", state.showOnlyBookmarks);
  el.bookmarksToggle.setAttribute("aria-pressed", String(state.showOnlyBookmarks));
  if (el.bookmarksCount) {
    el.bookmarksCount.textContent = String(state.bookmarks.size);
    el.bookmarksCount.style.display = state.bookmarks.size ? "" : "none";
  }
}

// --- VN gold compare chart ---------------------------------------------------

const COMPARE_PALETTE = ["#0f766e", "#2563eb", "#b45309", "#7c3aed", "#15803d", "#db2777"];

function renderGoldCompare(cards) {
  if (!el.vnGoldCompare) return;
  el.vnGoldCompare.innerHTML = "";

  const goldCards = (cards || []).filter(
    (card) => (card.key || "").startsWith("vn_gold_") && Array.isArray(card.history) && card.history.length >= 2,
  );

  if (goldCards.length < 2) {
    // We need at least two providers with enough datapoints to make the comparison
    // meaningful; otherwise the regular per-card sparkline is already enough.
    return;
  }

  const allValues = goldCards.flatMap((card) => card.history.map((p) => Number(p.value)));
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = max - min || Math.abs(max) * 0.001 || 1;

  const allTimestamps = goldCards.flatMap((card) => card.history.map((p) => Number(p.ts)));
  const tsMin = Math.min(...allTimestamps);
  const tsMax = Math.max(...allTimestamps);
  const tsSpan = tsMax - tsMin || 1;

  const width = 640;
  const height = 160;
  const padX = 8;
  const padY = 14;

  const wrapper = document.createElement("div");
  wrapper.className = "compare-chart";

  const header = document.createElement("div");
  header.className = "compare-chart-head";
  header.innerHTML = `<h4>So sánh giá vàng Việt Nam (7 ngày)</h4>`;
  wrapper.appendChild(header);

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.classList.add("compare-svg");

  goldCards.forEach((card, idx) => {
    const stroke = COMPARE_PALETTE[idx % COMPARE_PALETTE.length];
    const path = document.createElementNS(svgNS, "path");
    const d = card.history
      .map((point, pIdx) => {
        const x = padX + ((Number(point.ts) - tsMin) / tsSpan) * (width - padX * 2);
        const y = padY + (height - padY * 2) * (1 - (Number(point.value) - min) / span);
        return `${pIdx === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", stroke);
    path.setAttribute("stroke-width", "1.8");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);
  });

  wrapper.appendChild(svg);

  const legend = document.createElement("div");
  legend.className = "compare-legend";
  goldCards.forEach((card, idx) => {
    const stroke = COMPARE_PALETTE[idx % COMPARE_PALETTE.length];
    const last = card.history[card.history.length - 1];
    const value = last ? Number(last.value) : null;
    const item = document.createElement("span");
    item.className = "compare-legend-item";
    item.innerHTML = `
      <span class="compare-swatch" style="background:${stroke}"></span>
      <span class="compare-label">${card.label}</span>
      <span class="compare-value">${value ? value.toLocaleString("vi-VN") : "-"}</span>
    `;
    legend.appendChild(item);
  });
  wrapper.appendChild(legend);

  const meta = document.createElement("div");
  meta.className = "compare-meta";
  const minLabel = min.toLocaleString("vi-VN");
  const maxLabel = max.toLocaleString("vi-VN");
  meta.textContent = `${minLabel} – ${maxLabel} VND/lượng`;
  wrapper.appendChild(meta);

  el.vnGoldCompare.appendChild(wrapper);
}

// --- CSV export --------------------------------------------------------------

function csvEscape(value) {
  const text = value === null || value === undefined ? "" : String(value);
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function downloadCsv(filename, rows) {
  // BOM lets Excel auto-detect UTF-8 instead of mangling Vietnamese diacritics.
  const csv = "\ufeff" + rows.map((row) => row.map(csvEscape).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 0);
}

function exportPricesCsv() {
  const dashboard = state.dashboard;
  if (!dashboard) return;
  const intl = dashboard.prices?.cards || [];
  const vn = dashboard.prices?.vn_cards || [];

  const rows = [
    ["Khu vực", "Nguồn", "Sản phẩm", "Mua", "Bán", "Đơn vị", "Cập nhật"],
  ];
  intl.forEach((card) => {
    rows.push([
      "Quốc tế",
      card.exchange_name || card.symbol || "",
      card.label || "",
      "",
      card.price !== null && card.price !== undefined ? card.price : "",
      card.unit || "",
      card.updated_at || "",
    ]);
  });
  vn.forEach((card) => {
    rows.push([
      "Việt Nam",
      card.provider || "",
      card.label || "",
      card.buy ?? "",
      card.sell ?? "",
      card.unit || "",
      card.updated_label || "",
    ]);
  });

  const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  downloadCsv(`tinnhanh-prices-${stamp}.csv`, rows);
}

function bindEvents() {
  el.refreshBtn.addEventListener("click", () => loadDashboard(true));
  el.queryForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = el.queryInput.value;
    rememberQuery(value);
    await askQuestion(value);
  });
  el.quickChips.addEventListener("click", async (event) => {
    const clearBtn = event.target.closest("[data-action='clear-recent']");
    if (clearBtn) {
      clearRecentQueries();
      return;
    }
    const button = event.target.closest("[data-query]");
    if (!button) return;
    const query = button.dataset.query || "";
    el.queryInput.value = query;
    rememberQuery(query);
    await askQuestion(query);
  });
  if (el.themeToggle) {
    el.themeToggle.addEventListener("click", toggleTheme);
  }
  if (el.bookmarksToggle) {
    el.bookmarksToggle.addEventListener("click", () => {
      state.showOnlyBookmarks = !state.showOnlyBookmarks;
      refreshBookmarksButton();
      renderNews(state.activeTopicData);
    });
  }
  if (el.exportPricesBtn) {
    el.exportPricesBtn.addEventListener("click", exportPricesCsv);
  }
  if (el.newsFilterInput) {
    let debounceId = null;
    el.newsFilterInput.addEventListener("input", (event) => {
      const value = event.target.value;
      if (debounceId) clearTimeout(debounceId);
      debounceId = setTimeout(() => {
        state.newsFilter = value;
        renderNews(state.activeTopicData);
      }, 80);
    });
  }
  bindKeyboardShortcuts();
  bindVisibilityHandlers();
}

function bindKeyboardShortcuts() {
  document.addEventListener("keydown", (event) => {
    // Skip when the user is typing in an input/textarea/contenteditable.
    const target = event.target;
    const isEditable = target instanceof HTMLElement
      && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);

    // Esc: clear active filter even from inside the input.
    if (event.key === "Escape") {
      if (state.newsFilter && el.newsFilterInput) {
        event.preventDefault();
        el.newsFilterInput.value = "";
        state.newsFilter = "";
        renderNews(state.activeTopicData);
        el.newsFilterInput.blur();
      }
      return;
    }

    if (isEditable) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    if (event.key === "/") {
      // Vim/GitHub-style: focus the news filter for quick keyword scanning.
      if (el.newsFilterInput) {
        event.preventDefault();
        el.newsFilterInput.focus();
        el.newsFilterInput.select();
      }
    } else if (event.key === "r" || event.key === "R") {
      event.preventDefault();
      loadDashboard(true);
    } else if (event.key === "?" && el.queryInput) {
      event.preventDefault();
      el.queryInput.focus();
    } else if (event.key === "t" || event.key === "T") {
      event.preventDefault();
      toggleTheme();
    }
  });
}

function bindVisibilityHandlers() {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      loadDashboard(false, { silent: true });
    }
  });

  // Scroll-to-top button
  const scrollBtn = document.getElementById("scroll-top-btn");
  if (scrollBtn) {
    window.addEventListener("scroll", () => {
      scrollBtn.hidden = window.scrollY < 400;
    }, { passive: true });
    scrollBtn.addEventListener("click", () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
      // Fallback for browsers/contexts where window.scrollTo doesn't work.
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    });
  }
}

async function init() {
  initTheme();
  state.recentQueries = loadRecentQueries();
  renderRecentChips();
  state.bookmarks = loadBookmarks();
  refreshBookmarksButton();
  bindEvents();
  lucide.createIcons();
  await loadHealth();
  await loadDashboard(false);
  startAutoRefresh();
  registerServiceWorker();
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  // Avoid registering when the page is served over plain http (other than localhost).
  const isLocalhost = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  if (window.location.protocol !== "https:" && !isLocalhost) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch((err) => console.warn("SW registration failed:", err));
  });
}

init();
