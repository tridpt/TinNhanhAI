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
  customStocks: "tnai.watchlist.stocks",
  customCrypto: "tnai.watchlist.crypto",
  customCities: "tnai.watchlist.cities",
  customForex: "tnai.watchlist.forex",
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
  forexList: document.getElementById("forex-list"),
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

// Format a number for display, keeping enough significant decimals for very
// small values (e.g. SHIB at 0.000005) instead of rounding them to "0".
function formatSmartNumber(value, maxFrac = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  const av = Math.abs(n);
  if (av === 0) return "0";
  if (av >= 0.01) {
    return n.toLocaleString("vi-VN", { maximumFractionDigits: maxFrac });
  }
  // Show ~4 significant digits below 0.01, then trim trailing zeros.
  const decimals = Math.min(12, Math.floor(-Math.log10(av)) + 4);
  return n.toFixed(decimals).replace(/0+$/, "").replace(/\.$/, "");
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
  if (uniqueValues.size === 1 && points.length > 50) {
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
        <div class="chart-range-bar"></div>
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

  // Store full data for range switching.
  modal._chartData = { label, allPoints: points, options };

  // Render range buttons.
  const rangeBar = modal.querySelector(".chart-range-bar");
  const ranges = getAvailableRanges(points);
  rangeBar.innerHTML = "";
  ranges.forEach((range) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chart-range-btn";
    btn.textContent = range.label;
    btn.dataset.range = range.key;
    btn.addEventListener("click", () => {
      rangeBar.querySelectorAll(".chart-range-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const filtered = filterPointsByRange(points, range.hours);
      renderChartContent(modal, label, filtered, options);
    });
    rangeBar.appendChild(btn);
  });

  // Default: select best range based on data available.
  const defaultRange = selectDefaultRange(points, ranges);
  const defaultBtn = rangeBar.querySelector(`[data-range="${defaultRange.key}"]`);
  if (defaultBtn) defaultBtn.classList.add("active");

  const filtered = filterPointsByRange(points, defaultRange.hours);
  renderChartContent(modal, label, filtered, options);

  modal.classList.add("open");
  document.body.style.overflow = "hidden";
  lucide.createIcons();
}

function filterPointsByRange(points, hours) {
  if (!hours || !points.length) return points;
  const now = Math.max(...points.map((p) => p.ts));
  const cutoff = now - hours * 3600;
  const filtered = points.filter((p) => p.ts >= cutoff);
  return filtered.length >= 2 ? filtered : points;
}

function selectDefaultRange(points, ranges) {
  if (!points.length) return ranges[ranges.length - 1];
  const oldest = Math.min(...points.map((p) => p.ts));
  const newest = Math.max(...points.map((p) => p.ts));
  const spanHours = (newest - oldest) / 3600;
  // Pick the smallest range that covers most of the data.
  if (spanHours <= 80) return ranges.find((r) => r.key === "3d") || ranges[0];
  if (spanHours <= 200) return ranges.find((r) => r.key === "7d") || ranges[1];
  if (spanHours <= 800) return ranges.find((r) => r.key === "1m") || ranges[2];
  return ranges.find((r) => r.key === "3m") || ranges[3];
}

function getAvailableRanges(points) {
  const allRanges = [
    { key: "1d", label: "24h", hours: 24 },
    { key: "3d", label: "3 ngày", hours: 72 },
    { key: "7d", label: "7 ngày", hours: 168 },
    { key: "1m", label: "1 tháng", hours: 720 },
    { key: "3m", label: "3 tháng", hours: 2160 },
    { key: "all", label: "Tất cả", hours: 0 },
  ];
  if (points.length < 3) return allRanges;
  const avgGap = (points[points.length - 1].ts - points[0].ts) / (points.length - 1);
  // If average gap > 12h, data is daily — hide 24h option (useless).
  if (avgGap > 12 * 3600) {
    return allRanges.filter((r) => r.key !== "1d");
  }
  return allRanges;
}

function renderChartContent(modal, label, points, options) {
  const { formatTick = (v) => v.toLocaleString("vi-VN") } = options;

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

  // Footer stats — richer grid: current, change, open, high, low, average.
  const footer = modal.querySelector(".chart-footer");
  const sign = change >= 0 ? "+" : "";
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const volatilityPct = firstValue ? ((max - min) / firstValue * 100) : 0;
  footer.innerHTML = `
    <div class="chart-stat">
      <span class="chart-stat-label">Hiện tại</span>
      <span class="chart-stat-value">${formatTick(lastValue)}</span>
    </div>
    <div class="chart-stat">
      <span class="chart-stat-label">Thay đổi</span>
      <span class="chart-stat-value" style="color:${lineColor}">${sign}${formatTick(change)} (${sign}${changePct}%)</span>
    </div>
    <div class="chart-stat">
      <span class="chart-stat-label">Mở đầu kỳ</span>
      <span class="chart-stat-value">${formatTick(firstValue)}</span>
    </div>
    <div class="chart-stat">
      <span class="chart-stat-label">Cao nhất</span>
      <span class="chart-stat-value">${formatTick(max)}</span>
    </div>
    <div class="chart-stat">
      <span class="chart-stat-label">Thấp nhất</span>
      <span class="chart-stat-value">${formatTick(min)}</span>
    </div>
    <div class="chart-stat">
      <span class="chart-stat-label">Trung bình</span>
      <span class="chart-stat-value">${formatTick(avg)}</span>
    </div>
    <div class="chart-stat">
      <span class="chart-stat-label">Biên độ</span>
      <span class="chart-stat-value">${volatilityPct.toFixed(1)}%</span>
    </div>
    <div class="chart-stat">
      <span class="chart-stat-label">Số điểm</span>
      <span class="chart-stat-value">${points.length}</span>
    </div>
  `;

  // Tooltip on hover
  const tooltip = modal.querySelector(".chart-tooltip");
  const crosshair = svg.querySelector(".chart-crosshair");
  const dot = svg.querySelector(".chart-dot");
  const chartBody = modal.querySelector(".chart-body");

  chartBody.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    // Clamp crosshair within the chart area (padX to width-padX in viewBox).
    const svgX = (mouseX / rect.width) * width;
    const clampedSvgX = Math.max(padX, Math.min(svgX, width - padX));

    // Find the closest data point.
    let closestIdx = 0;
    let closestDist = Infinity;
    for (let i = 0; i < coords.length; i++) {
      const dist = Math.abs(coords[i].x - clampedSvgX);
      if (dist < closestDist) {
        closestDist = dist;
        closestIdx = i;
      }
    }
    const c = coords[closestIdx];

    // Crosshair snaps to the data point X (stays within chart bounds).
    crosshair.setAttribute("x1", c.x.toFixed(1));
    crosshair.setAttribute("x2", c.x.toFixed(1));
    crosshair.setAttribute("opacity", "1");
    dot.setAttribute("cx", c.x.toFixed(1));
    dot.setAttribute("cy", c.y.toFixed(1));
    dot.setAttribute("opacity", "1");

    const ts = points[closestIdx]?.ts;
    const date = ts ? new Date(ts * 1000) : null;
    const dateStr = date ? date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
    tooltip.textContent = `${dateStr}  ·  ${formatTick(c.value)}`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(Math.max((mouseX / rect.width) * 100, 10), 90)}%`;
  });

  chartBody.addEventListener("mouseleave", () => {
    crosshair.setAttribute("opacity", "0");
    dot.setAttribute("opacity", "0");
    tooltip.hidden = true;
  });

  modal.querySelector(".chart-title").textContent = label || "Biểu đồ giá";
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

// Render a friendly error inside the summary box with a "Thử lại" button.
function renderSummaryError(container, message, onRetry) {
  container.hidden = false;
  container.innerHTML = `
    <div class="reader-summary-error">
      <i data-lucide="alert-circle"></i>
      <span>${escapeHtml(message)}</span>
      <button type="button" class="reader-summary-retry">
        <i data-lucide="rotate-cw"></i> Thử lại
      </button>
    </div>
  `;
  const retryBtn = container.querySelector(".reader-summary-retry");
  if (retryBtn && typeof onRetry === "function") {
    retryBtn.addEventListener("click", onRetry);
  }
  lucide.createIcons();
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
            <button class="reader-summarize chip" type="button" title="Tóm tắt bằng AI">
              <i data-lucide="sparkles"></i><span>Tóm tắt AI</span>
            </button>
            <a class="reader-open-link chip" target="_blank" rel="noreferrer">
              <i data-lucide="external-link"></i><span>Mở gốc</span>
            </a>
            <button class="reader-close icon-btn" type="button" title="Đóng (Esc)">
              <i data-lucide="x"></i>
            </button>
          </div>
        </div>
        <div class="reader-meta"></div>
        <div class="reader-summary" hidden></div>
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

  // Wire summarize button (re-bind each time with current article).
  const summarizeBtn = modal.querySelector(".reader-summarize");
  const summaryDiv = modal.querySelector(".reader-summary");
  if (summaryDiv) summaryDiv.hidden = true;
  if (summarizeBtn) {
    const runSummarize = async () => {
      const plainText = (contentHtmlParts || [])
        .map((p) => p.replace(/<[^>]+>/g, ""))
        .join("\n");
      if (!plainText.trim()) return;
      summaryDiv.hidden = false;
      summarizeBtn.disabled = true;
      summaryDiv.innerHTML = `<div class="reader-summary-loading"><i data-lucide="loader" class="spin"></i> Đang tóm tắt...</div>`;
      lucide.createIcons();
      try {
        const res = await fetch("/api/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, content: plainText }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.error) {
          const isRate = res.status === 429 || data.error === "rate_limited";
          const msg = data.message
            || (isRate
              ? `Bạn tóm tắt hơi nhanh, chờ ${data.retry_after ?? 15}s rồi thử lại.`
              : "Chưa tóm tắt được, thử lại nhé.");
          renderSummaryError(summaryDiv, msg, runSummarize);
          summarizeBtn.disabled = false;
          return;
        }
        summaryDiv.innerHTML = `
          <div class="reader-summary-head"><i data-lucide="sparkles"></i> Tóm tắt AI${data.cached ? ' <span class="reader-summary-tag">đã lưu</span>' : ""}</div>
          <pre class="reader-summary-text">${escapeHtml(data.summary)}</pre>
        `;
        lucide.createIcons();
      } catch (e) {
        renderSummaryError(summaryDiv, "Lỗi kết nối mạng. Kiểm tra rồi thử lại.", runSummarize);
      } finally {
        summarizeBtn.disabled = false;
      }
    };
    summarizeBtn.onclick = runSummarize;
  }
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
  // Only clear default cards, preserve custom (user-added) cards.
  el.weatherList.querySelectorAll(".weather-card:not(.custom-card)").forEach((el) => el.remove());
  el.weatherList.querySelectorAll(".empty-state").forEach((el) => el.remove());

  // Filter out cities the user has hidden.
  const hidden = getHiddenCities();
  const visibleCities = (cities || []).filter((c) => !hidden.includes(c.key || c.city || ""));

  if (!visibleCities.length) {
    if (!el.weatherList.querySelector(".custom-card")) {
      el.weatherList.insertAdjacentHTML("afterbegin", `<div class="empty-state">Chưa lấy được thời tiết.</div>`);
    }
    return;
  }
  visibleCities.forEach((city) => {
    const forecast = (city.forecast || []).map((day, idx) => `
      <div class="forecast-day" data-day-idx="${idx}" style="cursor:pointer" title="Bấm xem theo giờ">
        <span class="forecast-date">${day.day_label || day.date || ""}</span>
        <i data-lucide="${day.icon || "cloud"}"></i>
        <span class="forecast-temps">${day.temp_min != null ? Math.round(day.temp_min) : "?"}° / ${day.temp_max != null ? Math.round(day.temp_max) : "?"}°</span>
        ${day.rain_prob != null ? `<span class="forecast-rain"><i data-lucide="droplets"></i>${day.rain_prob}%</span>` : ""}
      </div>
    `).join("");

    const card = document.createElement("article");
    card.className = "weather-card";
    card.dataset.cityKey = city.key || city.city || "";
    card.innerHTML = `
      <button class="remove-watchlist-btn" type="button" title="Ẩn thành phố này">
        <i data-lucide="x"></i>
      </button>
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
      <div class="hourly-detail" hidden></div>
    `;

    // Click forecast day → show hourly.
    card.querySelectorAll(".forecast-day").forEach((dayEl) => {
      dayEl.addEventListener("click", () => {
        const idx = parseInt(dayEl.dataset.dayIdx, 10);
        const day = (city.forecast || [])[idx];
        if (!day || !day.hours || !day.hours.length) return;
        const hourlyDiv = card.querySelector(".hourly-detail");
        const isOpen = !hourlyDiv.hidden && hourlyDiv.dataset.idx === String(idx);
        if (isOpen) {
          hourlyDiv.hidden = true;
          return;
        }
        hourlyDiv.dataset.idx = String(idx);
        hourlyDiv.hidden = false;
        hourlyDiv.innerHTML = `
          <div class="hourly-header">${day.day_label} — Dự báo theo giờ</div>
          <div class="hourly-grid">
            ${day.hours.filter((_, i) => i % 3 === 0).map((h) => `
              <div class="hourly-item">
                <span class="hourly-time">${h.time}</span>
                <span class="hourly-temp">${h.temp != null ? Math.round(h.temp) + "°" : ""}</span>
                <span class="hourly-rain">${h.rain != null ? h.rain + "%" : ""}</span>
              </div>
            `).join("")}
          </div>
        `;
      });
    });

    // Remove button handler.
    card.querySelector(".remove-watchlist-btn").addEventListener("click", () => {
      const key = city.key || city.city || "";
      hideDefaultCity(key);
      card.remove();
    });

    // Insert before custom cards.
    const firstCustom = el.weatherList.querySelector(".custom-card");
    if (firstCustom) {
      el.weatherList.insertBefore(card, firstCustom);
    } else {
      el.weatherList.appendChild(card);
    }
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

// Let the card header (icon + label) open the same detail chart as the
// sparkline, so users discover the rich view more easily.
function makeMarketHeadClickable(node, card) {
  const head = node.querySelector(".market-head");
  if (!head) return;
  const points = (card.history || []).filter(
    (p) => p && Number.isFinite(Number(p.value)),
  );
  if (points.length < 2) return;
  head.classList.add("market-head-clickable");
  head.title = "Bấm để xem biểu đồ chi tiết";
  head.addEventListener("click", () => {
    const lastValue = Number(points[points.length - 1].value);
    const firstValue = Number(points[0].value);
    const stroke = lastValue >= firstValue ? "var(--positive, #4ade80)" : "var(--negative, #f87171)";
    openDetailChart(card.label || card.symbol || "", points, {
      formatTick: (v) => formatSmartNumber(v, 2),
      stroke,
    });
  });
}

function renderMarketCards(container, cards, options = {}) {
  if (!container) return;
  if (!cards || !cards.length) {
    // Only clear non-custom cards; keep user's watchlist.
    container.querySelectorAll(".market-card:not(.custom-card)").forEach((el) => el.remove());
    container.querySelectorAll(".empty-state").forEach((el) => el.remove());
    if (!container.querySelector(".custom-card")) {
      container.insertAdjacentHTML("afterbegin", `<div class="empty-state">Chưa có dữ liệu.</div>`);
    }
    return;
  }
  // Remove only default cards (not custom watchlist cards).
  container.querySelectorAll(".market-card:not(.custom-card)").forEach((el) => el.remove());
  container.querySelectorAll(".empty-state").forEach((el) => el.remove());
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
    // Insert before custom cards so they stay at the bottom.
    const firstCustom = container.querySelector(".custom-card");
    if (firstCustom) {
      container.insertBefore(node, firstCustom);
    } else {
      container.appendChild(node);
    }
    flashPriceChange(node, card.key, card.price);
    if (options.showSparkline && card.history && card.history.length >= 2) {
      const sparkContainer = node.querySelector(".market-spark");
      renderSparkline(sparkContainer, card.history, {
        formatTick: (value) => formatSmartNumber(value, 2),
        label: card.label || card.key || "",
      });
      // Make the whole card header open the detail chart too (better discovery).
      makeMarketHeadClickable(node, card);
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

function renderForex(cards) {
  if (!el.forexList) return;
  // Only clear default cards, preserve custom watchlist cards.
  el.forexList.querySelectorAll(".price-card:not(.custom-card)").forEach((el) => el.remove());
  el.forexList.querySelectorAll(".empty-state").forEach((el) => el.remove());
  if (!cards || !cards.length) {
    if (!el.forexList.querySelector(".custom-card")) {
      el.forexList.insertAdjacentHTML("afterbegin", `<div class="empty-state">Chưa lấy được tỷ giá.</div>`);
    }
    return;
  }
  cards.forEach((card) => {
    const node = el.vnPriceTemplate.content.firstElementChild.cloneNode(true);
    const icon = node.querySelector(".price-icon i");
    icon.setAttribute("data-lucide", card.icon || "banknote");
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
    el.forexList.appendChild(node);
    // Insert before custom cards.
    const firstCustom = el.forexList.querySelector(".custom-card");
    if (firstCustom) {
      el.forexList.insertBefore(node, firstCustom);
    }
  });
  lucide.createIcons();
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
  renderForex(dashboard.prices?.forex_cards || []);
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
      renderForex(data.forex_cards || []);
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
      renderForex(data.forex_cards || []);
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
  el.answerBox.innerHTML = `<div class="answer-loading"><i data-lucide="loader" class="spin"></i> Đang lấy nguồn và tổng hợp...</div>`;
  lucide.createIcons();
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
      // Offer a retry button (except when offline, where a retry won't help).
      if (!isOffline) {
        const retryBtn = document.createElement("button");
        retryBtn.type = "button";
        retryBtn.className = "answer-retry-btn";
        retryBtn.innerHTML = `<i data-lucide="rotate-cw"></i> Thử lại`;
        retryBtn.addEventListener("click", () => askQuestion(question));
        el.answerBox.appendChild(retryBtn);
        lucide.createIcons();
      }
      return;
    }
    renderAnswer(data);
  } catch (error) {
    console.error(error);
    el.answerMeta.textContent = "Lỗi";
    el.answerBox.innerHTML = "";
    const note = document.createElement("p");
    note.className = "answer-error";
    note.textContent = "Không kết nối được tới máy chủ.";
    el.answerBox.appendChild(note);
    const retryBtn = document.createElement("button");
    retryBtn.type = "button";
    retryBtn.className = "answer-retry-btn";
    retryBtn.innerHTML = `<i data-lucide="rotate-cw"></i> Thử lại`;
    retryBtn.addEventListener("click", () => askQuestion(question));
    el.answerBox.appendChild(retryBtn);
    lucide.createIcons();
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

// --- Currency converter -------------------------------------------------------

function initConverter() {
  const form = document.getElementById("converter-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const amount = document.getElementById("converter-amount").value || "1";
    const from = document.getElementById("converter-from").value.trim().toUpperCase() || "USD";
    const to = document.getElementById("converter-to").value.trim().toUpperCase() || "VND";
    const resultDiv = document.getElementById("converter-result");
    resultDiv.textContent = "Đang quy đổi...";
    try {
      const r = await fetch(`/api/forex/convert?from=${from}&to=${to}&amount=${amount}`);
      const data = await r.json();
      if (data.error) {
        resultDiv.textContent = `Lỗi: ${data.error}`;
        return;
      }
      resultDiv.innerHTML = `<strong>${data.result_text}</strong><br><span class="muted">Tỷ giá: 1 ${data.from} = ${data.rate.toLocaleString("vi-VN", {maximumFractionDigits: 4})} ${data.to}</span>`;
      // Populate datalist with available currencies.
      if (data.available) populateCurrencyList(data.available);
    } catch (err) {
      resultDiv.textContent = "Không kết nối được.";
    }
  });
  // Pre-load currency list.
  fetch("/api/forex/convert?from=USD&to=VND&amount=1")
    .then((r) => r.json())
    .then((data) => { if (data.available) populateCurrencyList(data.available); })
    .catch(() => {});
}

function populateCurrencyList(codes) {
  const datalist = document.getElementById("currency-list");
  if (!datalist || datalist.children.length > 0) return;
  codes.forEach((code) => {
    const opt = document.createElement("option");
    opt.value = code;
    datalist.appendChild(opt);
  });
}

// --- Custom forex ------------------------------------------------------------

let _availableForexCodes = null;
// Monotonic counter so overlapping fetchCustomForex() calls don't clobber
// each other — only the newest invocation is allowed to paint the cards.
let _forexFetchSeq = 0;
let _cryptoFetchSeq = 0;
let _stocksFetchSeq = 0;

async function fetchAvailableForex() {
  if (_availableForexCodes) return _availableForexCodes;
  try {
    const r = await fetch("/api/forex/custom?codes=USD");
    const data = await r.json();
    _availableForexCodes = data.available || [];
    return _availableForexCodes;
  } catch (e) {
    return [];
  }
}

async function fetchCustomForex() {
  const codes = JSON.parse(localStorage.getItem(LS_KEYS.customForex) || "[]");
  if (!codes.length) {
    // List emptied — clear any leftover custom cards immediately.
    _forexFetchSeq += 1;
    if (el.forexList) el.forexList.querySelectorAll(".custom-card").forEach((c) => c.remove());
    return;
  }
  // Guard against overlapping calls: only the latest invocation may paint.
  _forexFetchSeq += 1;
  const mySeq = _forexFetchSeq;
  // Try Vietcombank first, then fallback to open.er-api for non-VCB currencies.
  try {
    const response = await fetch(`/api/forex/custom?codes=${encodeURIComponent(codes.join(","))}`);
    const data = await response.json();
    const vcbCards = data.cards || [];
    const vcbCodes = new Set(vcbCards.map((c) => c.symbol));

    // Fetch history for VCB cards from our store.
    for (const card of vcbCards) {
      try {
        const hRes = await fetch(`/api/prices/history?key=${card.key}&days=30`);
        const hData = await hRes.json();
        card.history = hData.points || [];
      } catch (e) { card.history = []; }
    }

    // For codes not in Vietcombank, use convert endpoint + history.
    const missingCodes = codes.filter((c) => !vcbCodes.has(c));
    const extraCards = [];
    for (const code of missingCodes) {
      try {
        const r = await fetch(`/api/forex/convert?from=${code}&to=VND&amount=1`);
        const d = await r.json();
        if (!d.error && d.rate) {
          // Fetch history from our own store (accumulates over time).
          let history = [];
          try {
            const hRes = await fetch(`/api/prices/history?key=forex_${code.toLowerCase()}_vnd&days=30`);
            const hData = await hRes.json();
            history = hData.points || [];
          } catch (e) { /* no history yet */ }
          extraCards.push({
            key: `forex_${code.toLowerCase()}_vnd`,
            label: `${code}/VND`,
            provider: "open.er-api",
            icon: "banknote",
            symbol: code,
            price: d.rate,
            price_text: `${d.rate.toLocaleString("vi-VN", {maximumFractionDigits: 2})}`,
            unit: `VND/${code}`,
            updated_label: new Date().toLocaleTimeString("vi-VN", {hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit"}),
            history: history,
          });
        }
      } catch (e) { /* skip */ }
    }
    // A newer fetch started while we were awaiting — discard this stale result
    // so we don't overwrite freshly added currencies.
    if (mySeq !== _forexFetchSeq) return;
    appendCustomForexCards([...vcbCards, ...extraCards]);
  } catch (e) { /* silent */ }
}

function appendCustomForexCards(cards) {
  if (!el.forexList) return;
  el.forexList.querySelectorAll(".custom-card").forEach((c) => c.remove());
  cards.forEach((card) => {
    const node = el.vnPriceTemplate.content.firstElementChild.cloneNode(true);
    node.classList.add("custom-card");
    const icon = node.querySelector(".price-icon i");
    icon.setAttribute("data-lucide", card.icon || "banknote");
    node.querySelector(".price-label").textContent = card.label || "";
    node.querySelector(".price-symbol").textContent = card.unit || "";
    node.querySelector(".price-value").textContent = card.price_text || "";
    node.querySelector(".price-unit").textContent = "";
    const providerEl = node.querySelector(".price-provider");
    if (providerEl) providerEl.textContent = card.provider || "";
    node.querySelector(".price-updated").textContent = `Cập nhật: ${card.updated_label || ""}`;

    const removeBtn = document.createElement("button");
    removeBtn.className = "remove-watchlist-btn";
    removeBtn.type = "button";
    removeBtn.innerHTML = `<i data-lucide="x"></i>`;
    removeBtn.title = "Xóa";
    removeBtn.addEventListener("click", () => {
      const list = JSON.parse(localStorage.getItem(LS_KEYS.customForex) || "[]");
      const filtered = list.filter((c) => c !== card.symbol);
      localStorage.setItem(LS_KEYS.customForex, JSON.stringify(filtered));
      node.remove();
    });
    node.appendChild(removeBtn);
    // Render sparkline if history available.
    const sparkContainer = node.querySelector(".price-spark");
    if (sparkContainer && card.history && card.history.length >= 2) {
      renderSparkline(sparkContainer, card.history, {
        formatTick: (v) => Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 }),
        label: card.label || "",
      });
    }
    el.forexList.appendChild(node);
  });
  lucide.createIcons();
}

async function promptAddForex() {
  // Fetch all 166 available currencies.
  let allCodes = [];
  try {
    const r = await fetch("/api/forex/convert?from=USD&to=VND&amount=1");
    const data = await r.json();
    allCodes = data.available || [];
  } catch (e) { /* fallback empty */ }

  const saved = JSON.parse(localStorage.getItem(LS_KEYS.customForex) || "[]");
  const defaults = ["USD", "EUR", "JPY", "GBP", "AUD", "SGD", "CNY", "KRW"];
  const alreadyShown = [...defaults, ...saved];

  let overlay = document.getElementById("forex-modal");
  if (overlay) overlay.remove();

  overlay = document.createElement("div");
  overlay.id = "forex-modal";
  overlay.className = "watchlist-modal";
  overlay.innerHTML = `
    <div class="watchlist-backdrop"></div>
    <div class="watchlist-dialog">
      <h3>Thêm tỷ giá ngoại tệ</h3>
      <p class="muted">Tìm và thêm bất kỳ loại tiền nào (166 loại). Gõ mã tiền hoặc chọn từ danh sách.</p>
      <form class="watchlist-form">
        <input type="text" class="watchlist-input" placeholder="Gõ mã tiền: THB, CAD, CHF, BRL..." list="forex-add-list" autocomplete="off" autofocus>
        <datalist id="forex-add-list">
          ${allCodes.filter((c) => !alreadyShown.includes(c)).map((c) => `<option value="${c}">`).join("")}
        </datalist>
        <div class="watchlist-actions">
          <button type="submit" class="primary-btn">Thêm</button>
          <button type="button" class="watchlist-cancel chip">Đóng</button>
        </div>
      </form>
      <div class="forex-popular">
        <p class="muted" style="margin:10px 0 6px;font-size:0.78rem">Phổ biến:</p>
        <div class="forex-options">
          ${["THB", "CAD", "CHF", "HKD", "INR", "MYR", "NOK", "SEK", "BRL", "TWD", "NZD", "ZAR"]
            .filter((c) => !alreadyShown.includes(c) && allCodes.includes(c))
            .map((c) => `<button type="button" class="forex-option" data-code="${c}">${c}</button>`)
            .join("")}
        </div>
      </div>
      <div class="watchlist-current"></div>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = overlay.querySelector(".watchlist-input");
  const form = overlay.querySelector(".watchlist-form");
  const cancel = overlay.querySelector(".watchlist-cancel");
  const backdrop = overlay.querySelector(".watchlist-backdrop");
  const currentDiv = overlay.querySelector(".watchlist-current");

  function close() { overlay.remove(); }
  cancel.addEventListener("click", close);
  backdrop.addEventListener("click", close);

  function renderSaved() {
    const list = JSON.parse(localStorage.getItem(LS_KEYS.customForex) || "[]");
    if (!list.length) { currentDiv.innerHTML = ""; return; }
    currentDiv.innerHTML = `
      <p class="watchlist-current-title">Đang theo dõi:</p>
      <div class="watchlist-chips">
        ${list.map((c) => `<span class="watchlist-chip">${c}<button type="button" data-code="${c}" class="watchlist-chip-remove">×</button></span>`).join("")}
      </div>
    `;
    currentDiv.querySelectorAll(".watchlist-chip-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.dataset.code;
        const updated = JSON.parse(localStorage.getItem(LS_KEYS.customForex) || "[]").filter((c) => c !== code);
        localStorage.setItem(LS_KEYS.customForex, JSON.stringify(updated));
        renderSaved();
        fetchCustomForex();
      });
    });
  }
  renderSaved();

  function addCode(code) {
    code = code.trim().toUpperCase();
    if (!code) return;
    const list = JSON.parse(localStorage.getItem(LS_KEYS.customForex) || "[]");
    if (list.includes(code) || defaults.includes(code)) return;
    list.push(code);
    localStorage.setItem(LS_KEYS.customForex, JSON.stringify(list));
    renderSaved();
    fetchCustomForex();
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    addCode(input.value);
    input.value = "";
  });

  overlay.querySelectorAll(".forex-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      addCode(btn.dataset.code);
      btn.disabled = true;
      btn.textContent = `${btn.dataset.code} ✓`;
    });
  });

  setTimeout(() => input.focus(), 50);
}

// --- Custom watchlist (stocks/crypto) ----------------------------------------

function loadWatchlist(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

function saveWatchlist(key, list) {
  try {
    localStorage.setItem(key, JSON.stringify(list));
  } catch (e) { /* ignore */ }
}

function promptAddSymbol(type) {
  const isStock = type === "stock";
  const placeholder = isStock
    ? "STB, ACB, FPT, VNM"
    : "DOGEUSDT, TRXUSDT, SHIBUSDT";
  const title = isStock ? "Thêm mã chứng khoán" : "Thêm coin crypto";

  // Create inline modal instead of browser prompt.
  let overlay = document.getElementById("watchlist-modal");
  if (overlay) overlay.remove();

  overlay = document.createElement("div");
  overlay.id = "watchlist-modal";
  overlay.className = "watchlist-modal";
  overlay.innerHTML = `
    <div class="watchlist-backdrop"></div>
    <div class="watchlist-dialog">
      <h3>${title}</h3>
      <p class="muted">Nhập symbol rồi bấm Thêm. Ví dụ: ${placeholder}</p>
      <form class="watchlist-form">
        <input type="text" class="watchlist-input" placeholder="${placeholder}" autocomplete="off" autofocus>
        <div class="watchlist-actions">
          <button type="submit" class="primary-btn">Thêm</button>
          <button type="button" class="watchlist-cancel chip">Huỷ</button>
        </div>
      </form>
      <div class="watchlist-current"></div>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = overlay.querySelector(".watchlist-input");
  const form = overlay.querySelector(".watchlist-form");
  const cancel = overlay.querySelector(".watchlist-cancel");
  const backdrop = overlay.querySelector(".watchlist-backdrop");
  const currentList = overlay.querySelector(".watchlist-current");

  function close() { overlay.remove(); }
  cancel.addEventListener("click", close);
  backdrop.addEventListener("click", close);
  document.addEventListener("keydown", function escHandler(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", escHandler); }
  });

  // Show current watchlist.
  function renderCurrent() {
    const key = isStock ? LS_KEYS.customStocks : LS_KEYS.customCrypto;
    const list = loadWatchlist(key);
    if (!list.length) {
      currentList.innerHTML = `<p class="muted">Chưa có symbol nào.</p>`;
      return;
    }
    currentList.innerHTML = `
      <p class="watchlist-current-title">Đang theo dõi:</p>
      <div class="watchlist-chips">
        ${list.map((s) => `<span class="watchlist-chip">${s}<button type="button" data-symbol="${s}" class="watchlist-chip-remove">×</button></span>`).join("")}
      </div>
    `;
    currentList.querySelectorAll(".watchlist-chip-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        removeFromWatchlist(type, btn.dataset.symbol);
        renderCurrent();
      });
    });
  }
  renderCurrent();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const value = input.value.trim();
    if (!value) return;

    const key = isStock ? LS_KEYS.customStocks : LS_KEYS.customCrypto;
    const list = loadWatchlist(key);

    // Support comma-separated input. For crypto, normalise to Binance pairs
    // (e.g. "btc" → "BTCUSDT", "Tether Gold (XAUT)" → "XAUTUSDT").
    const rawSymbols = value.split(",").map((s) => s.trim()).filter(Boolean);
    const symbols = isStock
      ? rawSymbols.map((s) => s.toUpperCase())
      : rawSymbols.map(normalizeCryptoSymbol).filter(Boolean);

    if (!symbols.length) {
      input.value = "";
      input.placeholder = "Symbol không hợp lệ!";
      return;
    }

    // Validate the symbols actually return data before saving, so we never
    // store a dead entry that shows no card/chart.
    const submitBtn = form.querySelector(".primary-btn");
    const prevLabel = submitBtn ? submitBtn.textContent : "";
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Đang kiểm tra..."; }
    let validSymbols = symbols;
    try {
      const endpoint = isStock ? "/api/stocks/custom" : "/api/crypto/custom";
      const checkRes = await fetch(`${endpoint}?symbols=${encodeURIComponent(symbols.join(","))}`);
      const checkData = await checkRes.json();
      const returned = new Set((checkData.cards || []).map((c) => c.symbol));
      validSymbols = symbols.filter((s) => returned.has(s));
    } catch (err) { /* network issue — fall back to optimistic add */ }
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = prevLabel; }

    if (!validSymbols.length) {
      input.value = "";
      input.placeholder = isStock ? "Không tìm thấy mã này!" : "Không tìm thấy coin này!";
      return;
    }

    let added = 0;
    validSymbols.forEach((symbol) => {
      if (!list.includes(symbol)) {
        list.push(symbol);
        added++;
      }
    });

    if (added === 0) {
      input.value = "";
      input.placeholder = "Đã có trong danh sách!";
      return;
    }

    saveWatchlist(key, list);
    input.value = "";
    renderCurrent();

    if (isStock) fetchCustomStocks();
    else fetchCustomCrypto();
  });

  setTimeout(() => input.focus(), 50);
}

function removeFromWatchlist(type, symbol) {
  const key = type === "stock" ? LS_KEYS.customStocks : LS_KEYS.customCrypto;
  const list = loadWatchlist(key).filter((s) => s !== symbol);
  saveWatchlist(key, list);
  if (type === "stock") fetchCustomStocks();
  else fetchCustomCrypto();
}

async function fetchCustomStocks() {
  const symbols = loadWatchlist(LS_KEYS.customStocks);
  if (!symbols.length) {
    _stocksFetchSeq += 1;
    if (el.stocksList) el.stocksList.querySelectorAll(".custom-card").forEach((c) => c.remove());
    return;
  }
  _stocksFetchSeq += 1;
  const mySeq = _stocksFetchSeq;
  try {
    const response = await fetch(`/api/stocks/custom?symbols=${encodeURIComponent(symbols.join(","))}`);
    if (!response.ok) return;
    const data = await response.json();
    if (mySeq !== _stocksFetchSeq) return;
    appendCustomCards(el.stocksList, data.cards || [], "stock");
  } catch (e) { /* silent */ }
}

// Normalise a user-typed crypto symbol to a Binance trading pair.
// Accepts messy input like "tether gold (xaut)" or "btc" → "BTCUSDT".
function normalizeCryptoSymbol(raw) {
  if (!raw) return "";
  let s = String(raw).toUpperCase().trim();
  // If there is a parenthesised ticker like "TETHER GOLD (XAUT)", use it.
  const paren = s.match(/\(([A-Z0-9]{2,15})\)/);
  if (paren) s = paren[1];
  // Drop anything that isn't a letter or digit (spaces, slashes, dashes...).
  s = s.replace(/[^A-Z0-9]/g, "");
  if (!s) return "";
  // Already quoted against a known fiat/stable pair → leave as-is.
  if (/(USDT|USDC|BUSD|FDUSD|TUSD|BTC|ETH|BNB)$/.test(s)) return s;
  // Bare coin name → default to the USDT pair.
  return `${s}USDT`;
}

async function fetchCustomCrypto() {
  const symbols = loadWatchlist(LS_KEYS.customCrypto);
  if (!symbols.length) {
    _cryptoFetchSeq += 1;
    if (el.cryptoList) el.cryptoList.querySelectorAll(".custom-card").forEach((c) => c.remove());
    return;
  }
  _cryptoFetchSeq += 1;
  const mySeq = _cryptoFetchSeq;
  try {
    const response = await fetch(`/api/crypto/custom?symbols=${encodeURIComponent(symbols.join(","))}`);
    if (!response.ok) return;
    const data = await response.json();
    if (mySeq !== _cryptoFetchSeq) return;
    appendCustomCards(el.cryptoList, data.cards || [], "crypto");
  } catch (e) { /* silent */ }
}

function appendCustomCards(container, cards, type) {
  if (!container) return;
  // Remove old custom cards.
  container.querySelectorAll(".custom-card").forEach((el) => el.remove());
  cards.forEach((card) => {
    const change = Number(card.change_percent || 0);
    const trend = change > 0 ? "up" : change < 0 ? "down" : "flat";
    const node = document.createElement("article");
    node.className = `market-card market-trend-${trend} custom-card`;
    node.innerHTML = `
      <button class="remove-watchlist-btn" type="button" title="Xóa khỏi danh sách" data-symbol="${card.symbol}" data-type="${type}">
        <i data-lucide="x"></i>
      </button>
      <div class="market-head">
        <span class="market-icon"><i data-lucide="${card.icon || "circle"}"></i></span>
        <div>
          <h4 class="market-label">${card.label || card.symbol}</h4>
          <p class="market-symbol">${card.symbol || ""}</p>
        </div>
      </div>
      <div class="market-price">${card.price_text || "—"}</div>
      <div class="market-change">${card.change_text || ""}</div>
      ${card.unit ? `<div class="market-unit">${card.unit}</div>` : ""}
      <div class="market-spark"></div>
    `;
    node.querySelector(".remove-watchlist-btn").addEventListener("click", () => {
      removeFromWatchlist(type, card.symbol);
    });
    container.appendChild(node);
    if (card.history && card.history.length >= 2) {
      renderSparkline(node.querySelector(".market-spark"), card.history, {
        formatTick: (v) => formatSmartNumber(v, 2),
        label: card.label || card.symbol,
      });
      makeMarketHeadClickable(node, card);
    }
  });
  lucide.createIcons();
}

// --- Custom weather locations ------------------------------------------------

function getHiddenCities() {
  try {
    return JSON.parse(localStorage.getItem("tnai.weather.hidden") || "[]");
  } catch (e) { return []; }
}

function hideDefaultCity(key) {
  try {
    const list = getHiddenCities();
    if (!list.includes(key)) list.push(key);
    localStorage.setItem("tnai.weather.hidden", JSON.stringify(list));
  } catch (e) { /* ignore */ }
}

function locateAndAddWeather() {
  if (!navigator.geolocation) {
    alert("Trình duyệt không hỗ trợ định vị.");
    return;
  }
  const btn = document.getElementById("locate-weather-btn");
  if (btn) btn.textContent = "Đang định vị...";

  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      const { latitude, longitude } = pos.coords;
      try {
        // Reverse geocode to get actual city name.
        const geoRes = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=&latitude=${latitude}&longitude=${longitude}&count=1&language=vi`);
        let cityName = "Vị trí của tôi";
        try {
          // Use a reverse geocoding approach: find nearest city.
          const revRes = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${latitude}&longitude=${longitude}&localityLanguage=vi`);
          const revData = await revRes.json();
          cityName = revData.city || revData.locality || revData.principalSubdivision || "Vị trí của tôi";
        } catch (e) { /* fallback to generic name */ }

        // Remove existing "my location" card to avoid duplicates.
        const existing = el.weatherList.querySelector('.custom-card[data-is-my-location="true"]');
        if (existing) existing.remove();

        const response = await fetch(`/api/weather/location?lat=${latitude}&lon=${longitude}&name=${encodeURIComponent(cityName)}`);
        const data = await response.json();
        if (data.error) throw new Error(data.error);
        data._isMyLocation = true;
        saveCustomCity({ lat: latitude, lon: longitude, name: cityName, isMyLocation: true });
        appendWeatherCard(data);
      } catch (e) {
        console.error("Weather location failed:", e);
      }
      if (btn) btn.innerHTML = `<i data-lucide="map-pin"></i> Vị trí của tôi`;
      lucide.createIcons();
    },
    (err) => {
      console.error("Geolocation error:", err);
      if (btn) btn.innerHTML = `<i data-lucide="map-pin"></i> Vị trí của tôi`;
      lucide.createIcons();
      alert("Không thể lấy vị trí. Hãy cho phép truy cập vị trí trong trình duyệt.");
    },
    { timeout: 10000 }
  );
}

function promptAddCity() {
  let overlay = document.getElementById("city-modal");
  if (overlay) overlay.remove();

  overlay = document.createElement("div");
  overlay.id = "city-modal";
  overlay.className = "watchlist-modal";
  overlay.innerHTML = `
    <div class="watchlist-backdrop"></div>
    <div class="watchlist-dialog">
      <h3>Thêm thành phố</h3>
      <p class="muted">Nhập tên thành phố (tiếng Anh hoặc tiếng Việt).</p>
      <form class="watchlist-form">
        <input type="text" class="watchlist-input" placeholder="Tokyo, London, New York..." autocomplete="off" autofocus>
        <div class="watchlist-actions">
          <button type="submit" class="primary-btn">Tìm & Thêm</button>
          <button type="button" class="watchlist-cancel chip">Huỷ</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = overlay.querySelector(".watchlist-input");
  const form = overlay.querySelector(".watchlist-form");
  const cancel = overlay.querySelector(".watchlist-cancel");
  const backdrop = overlay.querySelector(".watchlist-backdrop");

  function close() { overlay.remove(); }
  cancel.addEventListener("click", close);
  backdrop.addEventListener("click", close);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const city = input.value.trim();
    if (!city) return;
    input.disabled = true;

    // Use Open-Meteo geocoding to find lat/lon.
    try {
      const geoRes = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1&language=vi`);
      const geoData = await geoRes.json();
      const result = (geoData.results || [])[0];
      if (!result) {
        input.value = "";
        input.placeholder = "Không tìm thấy! Thử tên khác...";
        input.disabled = false;
        return;
      }
      const weatherRes = await fetch(`/api/weather/location?lat=${result.latitude}&lon=${result.longitude}&name=${encodeURIComponent(result.name)}`);
      const weatherData = await weatherRes.json();
      if (weatherData.error) throw new Error(weatherData.error);
      appendWeatherCard(weatherData);
      saveCustomCity({ lat: result.latitude, lon: result.longitude, name: result.name });
      close();
    } catch (err) {
      console.error(err);
      input.value = "";
      input.placeholder = "Lỗi! Thử lại...";
      input.disabled = false;
    }
  });

  setTimeout(() => input.focus(), 50);
}

function appendWeatherCard(city) {
  if (!el.weatherList) return;
  const forecast = (city.forecast || []).map((day, idx) => `
    <div class="forecast-day" data-day-idx="${idx}" style="cursor:pointer" title="Bấm xem theo giờ">
      <span class="forecast-date">${day.day_label || day.date || ""}</span>
      <i data-lucide="${day.icon || "cloud"}"></i>
      <span class="forecast-temps">${day.temp_min != null ? Math.round(day.temp_min) : "?"}° / ${day.temp_max != null ? Math.round(day.temp_max) : "?"}°</span>
      ${day.rain_prob != null ? `<span class="forecast-rain"><i data-lucide="droplets"></i>${day.rain_prob}%</span>` : ""}
    </div>
  `).join("");

  const card = document.createElement("article");
  card.className = "weather-card custom-card";
  card.dataset.cityName = city.city || "";
  if (city._isMyLocation) card.dataset.isMyLocation = "true";
  card.innerHTML = `
    <button class="remove-watchlist-btn" type="button" title="Xóa">
      <i data-lucide="x"></i>
    </button>
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
    <div class="hourly-detail" hidden></div>
  `;
  card.querySelector(".remove-watchlist-btn").addEventListener("click", () => {
    removeCustomCity(city.city || "");
    card.remove();
  });
  // Hourly expand on forecast day click.
  card.querySelectorAll(".forecast-day").forEach((dayEl) => {
    dayEl.addEventListener("click", () => {
      const idx = parseInt(dayEl.dataset.dayIdx, 10);
      const day = (city.forecast || [])[idx];
      if (!day || !day.hours || !day.hours.length) return;
      const hourlyDiv = card.querySelector(".hourly-detail");
      const isOpen = !hourlyDiv.hidden && hourlyDiv.dataset.idx === String(idx);
      if (isOpen) { hourlyDiv.hidden = true; return; }
      hourlyDiv.dataset.idx = String(idx);
      hourlyDiv.hidden = false;
      hourlyDiv.innerHTML = `
        <div class="hourly-header">${day.day_label} — Dự báo theo giờ</div>
        <div class="hourly-grid">
          ${day.hours.filter((_, i) => i % 3 === 0).map((h) => `
            <div class="hourly-item">
              <span class="hourly-time">${h.time}</span>
              <span class="hourly-temp">${h.temp != null ? Math.round(h.temp) + "°" : ""}</span>
              <span class="hourly-rain">${h.rain != null ? h.rain + "%" : ""}</span>
            </div>
          `).join("")}
        </div>
      `;
    });
  });
  el.weatherList.appendChild(card);
  lucide.createIcons();
}

function saveCustomCity(city) {
  try {
    let list = JSON.parse(localStorage.getItem(LS_KEYS.customCities) || "[]");
    // Remove old entry with same name or old "my location".
    if (city.isMyLocation) {
      list = list.filter((c) => !c.isMyLocation);
    } else {
      list = list.filter((c) => c.name !== city.name);
    }
    list.push(city);
    localStorage.setItem(LS_KEYS.customCities, JSON.stringify(list.slice(-10)));
  } catch (e) { /* ignore */ }
}

function removeCustomCity(name) {
  try {
    const list = JSON.parse(localStorage.getItem(LS_KEYS.customCities) || "[]");
    const filtered = list.filter((c) => c.name !== name);
    localStorage.setItem(LS_KEYS.customCities, JSON.stringify(filtered));
  } catch (e) { /* ignore */ }
}

async function loadSavedWeatherCities() {
  try {
    const list = JSON.parse(localStorage.getItem(LS_KEYS.customCities) || "[]");
    for (const city of list) {
      try {
        const response = await fetch(`/api/weather/location?lat=${city.lat}&lon=${city.lon}&name=${encodeURIComponent(city.name)}`);
        const data = await response.json();
        if (!data.error) appendWeatherCard(data);
      } catch (e) { /* skip */ }
    }
  } catch (e) { /* ignore */ }
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
  const addStockBtn = document.getElementById("add-stock-btn");
  if (addStockBtn) addStockBtn.addEventListener("click", () => promptAddSymbol("stock"));
  const addCryptoBtn = document.getElementById("add-crypto-btn");
  if (addCryptoBtn) addCryptoBtn.addEventListener("click", () => promptAddSymbol("crypto"));
  const addForexBtn = document.getElementById("add-forex-btn");
  if (addForexBtn) addForexBtn.addEventListener("click", promptAddForex);
  const locateBtn = document.getElementById("locate-weather-btn");
  if (locateBtn) locateBtn.addEventListener("click", locateAndAddWeather);
  const addCityBtn = document.getElementById("add-city-btn");
  if (addCityBtn) addCityBtn.addEventListener("click", promptAddCity);
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
  migrateCustomCryptoSymbols();
  state.recentQueries = loadRecentQueries();
  renderRecentChips();
  state.bookmarks = loadBookmarks();
  refreshBookmarksButton();
  bindEvents();
  lucide.createIcons();
  await loadHealth();
  await loadDashboard(false);
  fetchCustomStocks();
  fetchCustomCrypto();
  fetchCustomForex();
  initConverter();
  loadSavedWeatherCities();
  startAutoRefresh();
  registerServiceWorker();
  initInstallPrompt();
  initOfflineIndicator();
}

// One-time cleanup: older versions stored free-text coin names (e.g.
// "TETHER GOLD (XAUT)") that aren't valid Binance pairs, so their cards/charts
// never loaded. Normalise any such entries to proper symbols like "XAUTUSDT".
function migrateCustomCryptoSymbols() {
  try {
    const list = loadWatchlist(LS_KEYS.customCrypto);
    if (!list.length) return;
    const fixed = [];
    let changed = false;
    for (const entry of list) {
      const norm = normalizeCryptoSymbol(entry);
      if (norm && norm !== entry) changed = true;
      if (norm && !fixed.includes(norm)) fixed.push(norm);
    }
    if (changed) saveWatchlist(LS_KEYS.customCrypto, fixed);
  } catch (e) { /* ignore */ }
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  // Avoid registering when the page is served over plain http (other than localhost).
  const isLocalhost = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  if (window.location.protocol !== "https:" && !isLocalhost) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((reg) => {
        // Detect a newer service worker waiting to take over.
        reg.addEventListener("updatefound", () => {
          const newWorker = reg.installing;
          if (!newWorker) return;
          newWorker.addEventListener("statechange", () => {
            if (newWorker.state === "installed" && navigator.serviceWorker.controller) {
              showUpdateToast(reg);
            }
          });
        });
      })
      .catch((err) => console.warn("SW registration failed:", err));

    // When the controller changes (after skipWaiting), reload once to get fresh assets.
    let reloaded = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloaded) return;
      reloaded = true;
      window.location.reload();
    });
  });
}

// Toast inviting the user to load the new version.
function showUpdateToast(reg) {
  let toast = document.getElementById("update-toast");
  if (toast) return;
  toast = document.createElement("div");
  toast.id = "update-toast";
  toast.className = "pwa-toast";
  toast.innerHTML = `
    <i data-lucide="sparkles"></i>
    <span>Đã có bản cập nhật mới</span>
    <button type="button" class="pwa-toast-btn">Tải lại</button>
  `;
  document.body.appendChild(toast);
  lucide.createIcons();
  toast.querySelector(".pwa-toast-btn").addEventListener("click", () => {
    const waiting = reg.waiting;
    if (waiting) {
      waiting.postMessage("skipWaiting");
    } else {
      window.location.reload();
    }
    toast.remove();
  });
  // Auto-dismiss after 12s if ignored.
  setTimeout(() => toast.remove(), 12000);
}

// --- PWA install prompt ------------------------------------------------------

let _deferredInstallPrompt = null;

function initInstallPrompt() {
  const installBtn = document.getElementById("install-btn");

  // Hide the button if already running as an installed app.
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches
    || window.navigator.standalone === true;
  if (isStandalone) {
    if (installBtn) installBtn.hidden = true;
    return;
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    // Chrome/Edge/Android: stash the event and reveal our own button.
    e.preventDefault();
    _deferredInstallPrompt = e;
    if (installBtn) installBtn.hidden = false;
  });

  if (installBtn) {
    installBtn.addEventListener("click", async () => {
      if (!_deferredInstallPrompt) {
        // iOS Safari has no prompt API — guide the user instead.
        showIosInstallHint();
        return;
      }
      _deferredInstallPrompt.prompt();
      try {
        await _deferredInstallPrompt.userChoice;
      } catch (e) { /* ignore */ }
      _deferredInstallPrompt = null;
      installBtn.hidden = true;
    });

    // iOS: no beforeinstallprompt, but still offer the button with a hint.
    const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    if (isIos && !isStandalone) installBtn.hidden = false;
  }

  window.addEventListener("appinstalled", () => {
    _deferredInstallPrompt = null;
    if (installBtn) installBtn.hidden = true;
  });
}

function showIosInstallHint() {
  let hint = document.getElementById("ios-install-hint");
  if (hint) { hint.remove(); return; }
  hint = document.createElement("div");
  hint.id = "ios-install-hint";
  hint.className = "pwa-toast pwa-toast-hint";
  hint.innerHTML = `
    <i data-lucide="share"></i>
    <span>Bấm nút Chia sẻ rồi chọn "Thêm vào MH chính" để cài app.</span>
    <button type="button" class="pwa-toast-btn">OK</button>
  `;
  document.body.appendChild(hint);
  lucide.createIcons();
  hint.querySelector(".pwa-toast-btn").addEventListener("click", () => hint.remove());
  setTimeout(() => hint.remove(), 10000);
}

// --- Offline / online indicator ----------------------------------------------

function initOfflineIndicator() {
  const update = () => {
    const offline = !navigator.onLine;
    document.body.classList.toggle("is-offline", offline);
    let banner = document.getElementById("offline-banner");
    if (offline) {
      if (!banner) {
        banner = document.createElement("div");
        banner.id = "offline-banner";
        banner.className = "offline-banner";
        banner.innerHTML = `<i data-lucide="wifi-off"></i> Đang offline — hiển thị dữ liệu đã lưu`;
        document.body.appendChild(banner);
        lucide.createIcons();
      }
    } else if (banner) {
      banner.remove();
    }
  };
  window.addEventListener("online", update);
  window.addEventListener("offline", update);
  update();
}

init();
