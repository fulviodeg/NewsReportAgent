// Dashboard — loads export.json and does all filtering, search, and rendering client-side.
// No backend: the pipeline writes export.json, nginx serves it read-only.
// See docs/v1-architecture.md (Sections 3 and 9, item 7).

const REFRESH_MS = 60000;
const EXPORT_URL = "export.json"; // relative -> works at site root and via nginx alias
const REFRESH_ENDPOINT = "api/refresh"; // optional trigger backend; falls back to reload

let state = { data: null, generatedAt: null, theme: "", expanded: new Set() };
let els;

// --- theme colors (tab + tag share the same color per theme) ---------------
const THEME_COLORS = {
  AI: "#2563eb",
  Fintech: "#059669",
  "Big Tech": "#7c3aed",
  Startup: "#d97706",
  Cybersecurity: "#0891b2",
  "Policy/Regulation": "#dc2626",
  Other: "#6b7280",
};
const FALLBACK_COLORS = [
  "#2563eb", "#059669", "#7c3aed", "#d97706", "#0891b2", "#dc2626", "#db2777", "#0d9488",
];
function themeColor(theme) {
  if (THEME_COLORS[theme]) return THEME_COLORS[theme];
  let h = 0;
  for (const ch of theme || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACK_COLORS[h % FALLBACK_COLORS.length];
}

// --- pure filter (also unit-tested under Node) -----------------------------
function filterStories(stories, { q, theme, testata }) {
  const needle = (q || "").trim().toLowerCase();
  return stories.filter((s) => {
    if (theme && s.theme !== theme) return false;
    if (testata && !(s.sources || []).some((src) => src.testata === testata)) return false;
    if (needle) {
      const hay = [
        s.title || "",
        s.subtitle || "",
        s.summary_it || "",
        s.summary_long || "",
        (s.companies || []).join(" "),
        (s.sources || []).map((src) => src.title).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
}

// Deep-link to an AI assistant with the news pre-loaded.
function exploreUrl(provider, story) {
  const link = (story.sources && story.sources[0] && story.sources[0].link) || "";
  const prompt = `Approfondisci questa notizia: ${story.title}. Fonte: ${link}`;
  const q = encodeURIComponent(prompt);
  return {
    chatgpt: `https://chatgpt.com/?q=${q}`,
    perplexity: `https://www.perplexity.ai/search?q=${q}`,
    claude: `https://claude.ai/new?q=${q}`,
  }[provider];
}

// Italian, human-readable timestamp: "17 luglio 2026 alle 15:14".
const MONTHS_IT = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];
function formatTimestamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getDate()} ${MONTHS_IT[d.getMonth()]} ${d.getFullYear()} alle ${hh}:${mm}`;
}

// --- rendering -------------------------------------------------------------
function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text != null) e.textContent = text;
  return e;
}

function sourceLink(src, primary) {
  const a = el("a", primary ? "source primary" : "source");
  a.href = src.link;
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = `${src.testata} — ${src.title}`;
  return a;
}

function exploreBar(story) {
  const bar = el("div", "explore");
  bar.appendChild(el("span", "explore-label", "Esplora con"));
  const btns = el("div", "explore-btns");
  [
    ["ChatGPT", "chatgpt"],
    ["Perplexity", "perplexity"],
    ["Claude", "claude"],
  ].forEach(([label, key]) => {
    const a = el("a", "explore-btn", label);
    a.href = exploreUrl(key, story);
    a.target = "_blank";
    a.rel = "noopener";
    btns.appendChild(a);
  });
  bar.appendChild(btns);
  return bar;
}

function renderStory(s) {
  const card = el("article", "story");
  if (state.expanded.has(s.id)) card.classList.add("expanded");

  const head = el("div", "story-head");
  const theme = el("span", "chip theme", s.theme || "—");
  theme.style.background = themeColor(s.theme);
  head.appendChild(theme);
  (s.companies || []).forEach((c) => head.appendChild(el("span", "chip company", c)));
  card.appendChild(head);

  card.appendChild(el("h2", "title", s.title || (s.sources[0] && s.sources[0].title) || "—"));
  if (s.subtitle) card.appendChild(el("p", "subtitle", s.subtitle));
  card.appendChild(el("p", "summary", s.summary_it || ""));

  if (s.summary_long && s.summary_long !== s.summary_it) {
    card.appendChild(el("p", "summary-long", s.summary_long));
    const toggle = el("button", "expand-btn", state.expanded.has(s.id) ? "Comprimi" : "Espandi");
    toggle.addEventListener("click", () => {
      const open = card.classList.toggle("expanded");
      if (open) state.expanded.add(s.id);
      else state.expanded.delete(s.id);
      toggle.textContent = open ? "Comprimi" : "Espandi";
    });
    card.appendChild(toggle);
  }

  const sources = s.sources || [];
  if (sources[0]) card.appendChild(sourceLink(sources[0], true));
  if (sources.length > 1) {
    const others = el("details", "other-sources");
    others.appendChild(el("summary", null, `Altre fonti (${sources.length - 1})`));
    sources.slice(1).forEach((src) => others.appendChild(sourceLink(src, false)));
    card.appendChild(others);
  }

  card.appendChild(exploreBar(s));
  return card;
}

function renderTabs() {
  els.tabs.innerHTML = "";
  const themes = ["", ...((state.data && state.data.themes) || [])];
  themes.forEach((t) => {
    const active = state.theme === t;
    const b = el("button", "tab" + (active ? " active" : ""), t || "Tutte");
    const color = t ? themeColor(t) : "#854836";
    if (active) {
      b.style.background = color;
      b.style.borderColor = color;
      b.style.color = "#fff";
    } else {
      b.style.color = color;
      b.style.borderColor = color;
    }
    b.addEventListener("click", () => {
      state.theme = t;
      renderTabs();
      render();
    });
    els.tabs.appendChild(b);
  });
}

function fillSelect(select, values) {
  const current = select.value;
  const first = select.querySelector("option");
  select.innerHTML = "";
  select.appendChild(first);
  values.forEach((v) => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    select.appendChild(o);
  });
  if (values.includes(current)) select.value = current;
}

function render() {
  if (!state.data) return;
  const filtered = filterStories(state.data.stories, {
    q: els.search.value,
    theme: state.theme,
    testata: els.testata.value,
  });
  els.stories.innerHTML = "";
  filtered.forEach((s) => els.stories.appendChild(renderStory(s)));
  els.status.textContent =
    `${filtered.length} di ${state.data.stories.length} · aggiornato il ${formatTimestamp(state.data.generated_at)}`;
}

async function load() {
  try {
    const res = await fetch(`${EXPORT_URL}?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.generated_at === state.generatedAt) return;
    state.data = data;
    state.generatedAt = data.generated_at;
    renderTabs();
    fillSelect(els.testata, data.testate || []);
    render();
  } catch (err) {
    els.status.textContent = `Errore nel caricamento: ${err.message}`;
  }
}

// "Verifica nuove notizie": try the optional trigger backend, then reload the feed.
async function checkForNews() {
  els.refresh.disabled = true;
  els.status.textContent = "Verifica nuove notizie in corso…";
  try {
    await fetch(REFRESH_ENDPOINT, { method: "POST" }).catch(() => {});
    state.generatedAt = null; // force re-render even if unchanged
    await load();
  } finally {
    els.refresh.disabled = false;
  }
}

if (typeof document !== "undefined") {
  els = {
    search: document.getElementById("search"),
    testata: document.getElementById("filter-testata"),
    tabs: document.getElementById("tabs"),
    stories: document.getElementById("stories"),
    status: document.getElementById("status"),
    refresh: document.getElementById("refresh-btn"),
  };
  ["input", "change"].forEach((evt) => {
    [els.search, els.testata].forEach((c) => c.addEventListener(evt, render));
  });
  els.refresh.addEventListener("click", checkForNews);
  load();
  setInterval(load, REFRESH_MS);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { filterStories, exploreUrl, formatTimestamp, themeColor };
}
