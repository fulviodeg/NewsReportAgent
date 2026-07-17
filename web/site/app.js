// Dashboard — loads /export.json and does all filtering and search client-side.
// No backend: the pipeline writes export.json, nginx serves it read-only.
// See docs/v1-architecture.md (Sections 3 and 9, item 7).

const REFRESH_MS = 60000; // auto-refresh cadence
const EXPORT_URL = "export.json"; // relative -> works at site root and via nginx alias

let state = { data: null, generatedAt: null };
let els;

// Pure filter — kept separate so it is easy to reason about and test.
function filterStories(stories, { q, theme, company, testata }) {
  const needle = (q || "").trim().toLowerCase();
  return stories.filter((s) => {
    if (theme && s.theme !== theme) return false;
    if (company && !(s.companies || []).includes(company)) return false;
    if (testata && !(s.sources || []).some((src) => src.testata === testata)) return false;
    if (needle) {
      const hay = [
        s.summary_it || "",
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

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text != null) e.textContent = text;
  return e;
}

function renderStory(s) {
  const card = el("article", "story");
  const head = el("div", "story-head");
  head.appendChild(el("span", "chip theme", s.theme || "—"));
  (s.companies || []).forEach((c) => head.appendChild(el("span", "chip company", c)));
  card.appendChild(head);

  card.appendChild(el("p", "summary", s.summary_it || ""));

  const sources = s.sources || [];
  const primary = el("div", "sources");
  sources.slice(0, 1).forEach((src) => primary.appendChild(sourceLink(src, true)));
  card.appendChild(primary);

  if (sources.length > 1) {
    const others = el("details", "other-sources");
    others.appendChild(el("summary", null, `Altre fonti (${sources.length - 1})`));
    sources.slice(1).forEach((src) => others.appendChild(sourceLink(src, false)));
    card.appendChild(others);
  }
  return card;
}

function sourceLink(src, primary) {
  const a = el("a", primary ? "source primary" : "source");
  a.href = src.link;
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = `${src.testata} — ${src.title}`;
  return a;
}

function render() {
  if (!state.data) return;
  const filtered = filterStories(state.data.stories, {
    q: els.search.value,
    theme: els.theme.value,
    company: els.company.value,
    testata: els.testata.value,
  });
  els.stories.innerHTML = "";
  filtered.forEach((s) => els.stories.appendChild(renderStory(s)));
  els.status.textContent = `${filtered.length} / ${state.data.stories.length} storie · aggiornato ${state.data.generated_at || ""}`;
}

async function load() {
  try {
    const res = await fetch(`${EXPORT_URL}?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.generated_at === state.generatedAt) return; // no change -> keep state
    state = { data, generatedAt: data.generated_at };
    fillSelect(els.theme, data.themes || []);
    fillSelect(els.company, data.companies || []);
    fillSelect(els.testata, data.testate || []);
    render();
  } catch (err) {
    els.status.textContent = `Errore nel caricamento: ${err.message}`;
  }
}

// Bootstrap only in a browser; under Node (tests) we just export the pure logic.
if (typeof document !== "undefined") {
  els = {
    search: document.getElementById("search"),
    theme: document.getElementById("filter-theme"),
    company: document.getElementById("filter-company"),
    testata: document.getElementById("filter-testata"),
    stories: document.getElementById("stories"),
    status: document.getElementById("status"),
  };

  ["input", "change"].forEach((evt) => {
    [els.search, els.theme, els.company, els.testata].forEach((c) =>
      c.addEventListener(evt, render)
    );
  });

  load();
  setInterval(load, REFRESH_MS);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { filterStories };
}

