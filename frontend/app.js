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
  const answer = data.answer || "Chưa có câu trả lời.";
  el.answerMeta.textContent = `${data.intent || "general"} · ${formatTime(data.generated_at)}`;
  el.answerBox.innerHTML = "";

  const text = document.createElement("pre");
  text.textContent = answer;
  el.answerBox.appendChild(text);

  const sources = Array.isArray(data.sources) ? data.sources : [];
  if (sources.length) {
    const list = document.createElement("ul");
    list.className = "answer-sources";
    sources.slice(0, 6).forEach((source) => {
      const node = el.sourceTemplate.content.firstElementChild.cloneNode(true);
      const link = node.querySelector(".source-link");
      link.textContent = source.title || source.domain || "Nguồn";
      link.href = source.url || "#";
      node.querySelector(".source-snippet").textContent = source.snippet || "";
      list.appendChild(node);
    });
    el.answerBox.appendChild(list);
  }
  lucide.createIcons();
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
    if (!response.ok) {
      throw new Error(`Dashboard failed: ${response.status}`);
    }
    const data = await response.json();
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
    if (!response.ok) {
      throw new Error(`Ask failed: ${response.status}`);
    }
    const data = await response.json();
    renderAnswer(data);
  } catch (error) {
    console.error(error);
    el.answerMeta.textContent = "Lỗi";
    el.answerBox.innerHTML = `<p class="muted">Không trả lời được câu hỏi này.</p>`;
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
}

init();
