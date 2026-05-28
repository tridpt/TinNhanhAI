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
  briefText: document.getElementById("brief-text"),
  answerBox: document.getElementById("answer-box"),
  answerMeta: document.getElementById("answer-meta"),
  metricTopics: document.getElementById("metric-topics"),
  metricArticles: document.getElementById("metric-articles"),
  metricSources: document.getElementById("metric-sources"),
  metricUpdated: document.getElementById("metric-updated"),
  newsTemplate: document.getElementById("news-item-template"),
  priceTemplate: document.getElementById("price-item-template"),
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

function renderDashboard(dashboard) {
  state.dashboard = dashboard;
  updateMetrics(dashboard);
  const topics = dashboard.topics || [];
  renderTopics(topics);
  const active = topics.find((topic) => topic.key === state.activeTopic) || topics.find((topic) => topic.key === "all");
  renderNews(active);
  renderPrices(dashboard.prices?.cards || []);
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
