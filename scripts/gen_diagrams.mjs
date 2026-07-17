// Assemble LikeC4 per-view Mermaid into a single GitHub-rendered docs/diagrams.md.
// Run via `npm run docs:mermaid`. Do not edit docs/diagrams.md by hand.

import { execSync } from "node:child_process";
import { readdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";

const SRC = "docs/architecture";
const TMP = "docs/.diagrams_tmp";
const OUT = "docs/diagrams.md";

const TITLES = {
  index: "Contesto (System Context)",
  containers: "Container",
  components: "Componenti della Pipeline",
  collectionClock: "Dynamic — Collection clock",
  processingClock: "Dynamic — Processing clock",
};
const ORDER = ["index", "containers", "components", "collectionClock", "processingClock"];

rmSync(TMP, { recursive: true, force: true });
execSync(`npx likec4 gen mermaid ${SRC} -o ${TMP}`, { stdio: "inherit" });

const byName = Object.fromEntries(
  readdirSync(TMP)
    .filter((f) => f.endsWith(".mmd"))
    .map((f) => [f.replace(/\.mmd$/, ""), f])
);
const names = [
  ...ORDER.filter((n) => byName[n]),
  ...Object.keys(byName).filter((n) => !ORDER.includes(n)),
];

let md =
  "# Diagrammi architetturali\n\n" +
  "> Generato da LikeC4 (`docs/architecture/*.c4`) con `npm run docs:mermaid`. " +
  "Non modificare a mano.\n> Versione interattiva: " +
  "https://fulviodeg.github.io/NewsReportAgent/\n";

for (const n of names) {
  const body = readFileSync(join(TMP, byName[n]), "utf8").trim();
  md += `\n## ${TITLES[n] || n}\n\n\`\`\`mermaid\n${body}\n\`\`\`\n`;
}

writeFileSync(OUT, md);
rmSync(TMP, { recursive: true, force: true });
console.log(`wrote ${OUT} (${names.length} diagrams)`);
