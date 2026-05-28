const state = {
  dashboard: null,
  activeTopic: "all",
  loadingQuestion: false,
  aiEnabled: false,
};

const topicOrder = ["all", "thoi_su", "kinh_te", "cong_nghe", "the_gioi", "the_thao"];
const topicMeta = {
  all: { label: "Tổng hợp", icon: "layout-grid" },
  thoi_su: { label: "Thời sự", icon: "newspaper" },
  kinh_te: { label: "Kinh tế", icon: "chart-column" },
  cong_nghe: { label: "Công nghệ", icon: "cpu" },
  the_gioi: { label: "Thế giới", icon: "globe" },
  the_thao: { label: "Thể thao", icon: "trophy" },
};

const el = {
  healthPill: document.getElementById("health-pill"),
  refreshBtn: document.getElementById("refresh-btn"),
  queryForm: document.getElementById("query-form"),
  queryInput: document.getElementById("query-input"),
  quickChips: document.getElementById("quick-chips"),
  topicTabs: document.getElementById("topic-tabs"),
  newsList: document.getElementById("news-list"),
  priceList: document.getElementById("price-list"),
  vnPriceList: document.getElementById("vn-price-list"),
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

function renderNews(topic) {
  if (!topic) {
    el.newsList.innerHTML = `<div class="empty-state">Không có dữ liệu tin.</div>`;
    return;
  }

  const items = topic.items || [];
  if (!items.length) {
    el.newsList.innerHTML = `<div class="empty-state">Chưa có bài mới cho chủ đề này.</div>`;
    return;
  }

  el.newsList.innerHTML = "";
  items.forEach((item) => {
    const node = el.newsTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".source-pill").textContent = item.source || topic.label;
    node.querySelector(".time-pill").textContent = item.published_label || formatRelative(item.published_at);
    const link = node.querySelector(".news-title");
    link.textContent = item.title || "";
    link.href = item.url || "#";
    node.querySelector(".news-summary").textContent = item.summary || "Không có mô tả.";
    el.newsList.appendChild(node);
  });
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

  const minLabel = options.formatTick ? options.formatTick(min) : min.toLocaleString("vi-VN");
  const maxLabel = options.formatTick ? options.formatTick(max) : max.toLocaleString("vi-VN");

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
    });
    el.priceList.appendChild(node);
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

async function loadDashboard(force = false) {
  setHealth("Đang tải dữ liệu", "warn");
  el.refreshBtn.disabled = true;
  try {
    const response = await fetch(`/api/dashboard${force ? "?force=1" : ""}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.error) {
      const offline = data?.error === "offline";
      setHealth(offline ? "Offline" : "Không tải được dữ liệu", offline ? "warn" : "err");
      el.briefText.textContent = offline
        ? "Bạn đang offline. Hiển thị dữ liệu đã lưu trước đó (nếu có)."
        : "Không tải được dữ liệu. Hãy thử làm mới lại.";
      return;
    }
    renderDashboard(data);
  } catch (error) {
    console.error(error);
    setHealth("Không tải được dữ liệu", "err");
    el.briefText.textContent = "Không tải được dữ liệu. Hãy thử làm mới lại.";
    el.newsList.innerHTML = `<div class="empty-state">Không lấy được tin trong lần này.</div>`;
    el.priceList.innerHTML = `<div class="empty-state">Không lấy được giá trong lần này.</div>`;
  } finally {
    el.refreshBtn.disabled = false;
  }
}

async function askQuestion(question) {
  if (!question.trim() || state.loadingQuestion) return;
  state.loadingQuestion = true;
  el.answerMeta.textContent = "Đang suy nghĩ...";
  el.answerBox.innerHTML = `<p class="muted">Đang lấy nguồn...</p>`;
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

function bindEvents() {
  el.refreshBtn.addEventListener("click", () => loadDashboard(true));
  el.queryForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await askQuestion(el.queryInput.value);
  });
  el.quickChips.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-query]");
    if (!button) return;
    const query = button.dataset.query || "";
    el.queryInput.value = query;
    await askQuestion(query);
  });
}

async function init() {
  bindEvents();
  lucide.createIcons();
  await loadHealth();
  await loadDashboard(false);
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
