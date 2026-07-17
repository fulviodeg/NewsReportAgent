// Dashboard — loads export.json and does all filtering, search, and rendering client-side.
// No backend: the pipeline writes export.json, nginx serves it read-only.
// See docs/v1-architecture.md (Sections 3 and 9, item 7).

const REFRESH_MS = 60000;
const EXPORT_URL = "export.json"; // relative -> works at site root and via nginx alias

let state = { data: null, generatedAt: null, theme: "", expanded: new Set() };
let els;

// --- pure filter (also unit-tested under Node) -----------------------------
function filterStories(stories, { q, theme, company, testata }) {
  const needle = (q || "").trim().toLowerCase();
  return stories.filter((s) => {
    if (theme && s.theme !== theme) return false;
    if (company && !(s.companies || []).includes(company)) return false;
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

// Build the deep-link to an AI assistant with the news pre-loaded.
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
  [
    ["ChatGPT", "chatgpt"],
    ["Perplexity", "perplexity"],
    ["Claude", "claude"],
  ].forEach(([label, key]) => {
    const a = el("a", "explore-btn", label);
    a.href = exploreUrl(key, story);
    a.target = "_blank";
    a.rel = "noopener";
    bar.appendChild(a);
  });
  return bar;
}

function renderStory(s) {
  const card = el("article", "story");
  if (state.expanded.has(s.id)) card.classList.add("expanded");

  const head = el("div", "story-head");
  head.appendChild(el("span", "chip theme", s.theme || "—"));
  (s.companies || []).forEach((c) => head.appendChild(el("span", "chip company", c)));
  card.appendChild(head);

  card.appendChild(el("h2", "title", s.title || (s.sources[0] && s.sources[0].title) || "—"));
  if (s.subtitle) card.appendChild(el("p", "subtitle", s.subtitle));
  card.appendChild(el("p", "summary", s.summary_it || ""));

  if (s.summary_long) {
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
    const b = el("button", "tab" + (state.theme === t ? " active" : ""), t || "Tutte");
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
    company: els.company.value,
    testata: els.testata.value,
  });
  els.stories.innerHTML = "";
  filtered.forEach((s) => els.stories.appendChild(renderStory(s)));
  els.status.textContent = `${filtered.length}/${state.data.stories.length} · agg. ${state.data.generated_at || ""}`;
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
    fillSelect(els.company, data.companies || []);
    fillSelect(els.testata, data.testate || []);
    render();
  } catch (err) {
    els.status.textContent = `Errore nel caricamento: ${err.message}`;
  }
}

if (typeof document !== "undefined") {
  els = {
    search: document.getElementById("search"),
    company: document.getElementById("filter-company"),
    testata: document.getElementById("filter-testata"),
    tabs: document.getElementById("tabs"),
    stories: document.getElementById("stories"),
    status: document.getElementById("status"),
  };
  ["input", "change"].forEach((evt) => {
    [els.search, els.company, els.testata].forEach((c) => c.addEventListener(evt, render));
  });
  load();
  setInterval(load, REFRESH_MS);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { filterStories, exploreUrl };
}
