// Dashboard — loads export.json (main), archive.json (archive), or archive.json filtered (favorites).
// One script drives all pages via <body data-page="main|archive|favorites">.

const REFRESH_MS = 60000;
const PAGE = (typeof document !== "undefined" && document.body && document.body.dataset.page) || "main";
const IS_ARCHIVE = PAGE === "archive";
const IS_FAVORITES = PAGE === "favorites";
const DATA_URL = (IS_ARCHIVE || IS_FAVORITES) ? "archive.json" : "export.json";
const REFRESH_ENDPOINT = "api/refresh";
const FAV_KEY = "newsreport_favorites";

let state = {
  data: null,
  generatedAt: null,
  theme: "",
  favorites: new Set(),
  expanded: new Set(),
  visible: (IS_ARCHIVE || IS_FAVORITES) ? 10 : Infinity,
};
let els;

// --- favorites (localStorage) ------------------------------------------------
function loadFavorites() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || "[]"));
  } catch { return new Set(); }
}
function saveFavorites(set) {
  localStorage.setItem(FAV_KEY, JSON.stringify([...set]));
}
function toggleFavorite(id) {
  const favs = loadFavorites();
  if (favs.has(id)) favs.delete(id);
  else favs.add(id);
  saveFavorites(favs);
  state.favorites = favs;
}

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
function filterStories(stories, { q, theme, testata, favorites }) {
  const needle = (q || "").trim().toLowerCase();
  return stories.filter((s) => {
    if (theme && s.theme !== theme) return false;
    if (testata && !(s.sources || []).some((src) => src.testata === testata)) return false;
    if (favorites && !favorites.has(s.id)) return false;
    if (needle) {
      const hay = [
        s.title || "", s.subtitle || "", s.summary_long || "",
        (s.entities || []).join(" "),
        (s.sources || []).map((src) => src.title).join(" "),
      ].join(" ").toLowerCase();
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
}

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

// --- entity highlighting ---------------------------------------------------
function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function highlight(text, entities) {
  const uniq = [...new Set((entities || []).filter(Boolean))].sort((a, b) => b.length - a.length);
  const raw = String(text == null ? "" : text);
  if (!uniq.length) return escapeHtml(raw);
  const pattern = new RegExp(String.raw`\b(` + uniq.map(escapeRegExp).join("|") + String.raw`)\b`, "g");
  let out = "", last = 0, m;
  while ((m = pattern.exec(raw)) !== null) {
    out += escapeHtml(raw.slice(last, m.index)) + '<mark class="entity">' + escapeHtml(m[0]) + "</mark>";
    last = m.index + m[0].length;
    if (m.index === pattern.lastIndex) pattern.lastIndex++;
  }
  return out + escapeHtml(raw.slice(last));
}

// --- rendering -------------------------------------------------------------
function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text != null) e.textContent = text;
  return e;
}
function elHTML(tag, className, html) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  e.innerHTML = html;
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
  [["ChatGPT", "chatgpt"], ["Perplexity", "perplexity"], ["Claude", "claude"]].forEach(
    ([label, key]) => {
      const a = el("a", "explore-btn", label);
      a.href = exploreUrl(key, story);
      a.target = "_blank";
      a.rel = "noopener";
      btns.appendChild(a);
    }
  );
  bar.appendChild(btns);
  return bar;
}

function renderStory(s) {
  const ent = s.entities || [];
  const card = el("article", "story");
  const isExpanded = state.expanded.has(s.id);
  const isFav = state.favorites.has(s.id);
  if (isExpanded) card.classList.add("expanded");

  // --- click on card to toggle expand ---
  card.addEventListener("click", (e) => {
    // Don't toggle if clicking a link, button, or details/summary
    if (e.target.closest("a, button, details")) return;
    if (isExpanded) state.expanded.delete(s.id);
    else state.expanded.add(s.id);
    render();
  });

  // --- story head: chip + heart button ---
  const head = el("div", "story-head");
  const chip = el("span", "chip theme", s.theme || "—");
  chip.style.background = themeColor(s.theme);
  head.appendChild(chip);

  const favBtn = el("button", "fav-btn" + (isFav ? " active" : ""), isFav ? "❤️" : "🤍");
  favBtn.title = isFav ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti";
  favBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleFavorite(s.id);
    render();
  });
  head.appendChild(favBtn);
  card.appendChild(head);

  // --- title + subtitle ---
  card.appendChild(elHTML("h2", "title", highlight(s.title || (s.sources[0] && s.sources[0].title) || "—", ent)));
  if (s.subtitle) card.appendChild(elHTML("p", "subtitle", highlight(s.subtitle, ent)));

  // --- long description (visible when expanded) ---
  if (s.summary_long) {
    const descLong = elHTML("div", "desc-long", highlight(s.summary_long, ent));
    card.appendChild(descLong);
  }

  // --- sources ---
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
    if (active) { b.style.background = color; b.style.borderColor = color; b.style.color = "#fff"; }
    else { b.style.color = color; b.style.borderColor = color; }
    b.addEventListener("click", () => { state.theme = t; state.visible = 10; renderTabs(); render(); });
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
    o.value = v; o.textContent = v;
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
    favorites: IS_FAVORITES ? state.favorites : null,
  });
  const shown = (IS_ARCHIVE || IS_FAVORITES) ? filtered.slice(0, state.visible) : filtered;
  els.stories.innerHTML = "";
  shown.forEach((s) => els.stories.appendChild(renderStory(s)));

  if (els.loadMore) {
    els.loadMore.style.display = (IS_ARCHIVE || IS_FAVORITES) && filtered.length > shown.length ? "" : "none";
  }
  els.status.textContent =
    `${shown.length} di ${filtered.length} · aggiornato il ${formatTimestamp(state.data.generated_at)}`;
}

async function load() {
  try {
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`);
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

async function checkForNews() {
  els.refresh.disabled = true;
  els.status.textContent = "Verifica nuove notizie in corso…";
  try {
    await fetch(REFRESH_ENDPOINT, { method: "POST" }).catch(() => {});
    state.generatedAt = null;
    await load();
  } finally {
    els.refresh.disabled = false;
  }
}

if (typeof document !== "undefined") {
  state.favorites = loadFavorites();

  els = {
    search: document.getElementById("search"),
    testata: document.getElementById("filter-testata"),
    tabs: document.getElementById("tabs"),
    stories: document.getElementById("stories"),
    status: document.getElementById("status"),
    refresh: document.getElementById("refresh-btn"),
    loadMore: document.getElementById("load-more"),
  };
  ["input", "change"].forEach((evt) => {
    [els.search, els.testata].forEach((c) =>
      c.addEventListener(evt, () => { state.visible = 10; render(); })
    );
  });
  if (els.refresh) els.refresh.addEventListener("click", checkForNews);
  if (els.loadMore) els.loadMore.addEventListener("click", () => { state.visible += 10; render(); });
  load();
  if (!IS_ARCHIVE && !IS_FAVORITES) setInterval(load, REFRESH_MS);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { filterStories, exploreUrl, formatTimestamp, themeColor, highlight };
}