# Build Prompt — News Report Agent v1

Hand this to your coding agent (Claude Code or OpenCode) in a fresh, empty repository. This prompt is the task. It is deliberately lean: the full specification lives in the architecture document, and your standing behavioral rules live in `CLAUDE.md`. Read both before building.

- **Specification (read first, in full):** `v1-architecture.md` — the complete v1 design: components, configuration, guardrails, deployment, and the Definition of Done. Keep this file in the repository (for example `docs/architecture.md`) so you can re-read it on demand.
- **Behavioral rules:** `CLAUDE.md` at the repo root (from `coding-agent-CLAUDE.md`).

---

## Your task

Build v1 of the News Report Agent as specified in the architecture document: a system that ingests news from newsletters, classifies and synthesizes it with an LLM, and publishes a filterable, password-protected static dashboard. Read the architecture document fully first, then implement it. Ask about anything unclear before building on it.

---

## How to work

- **State assumptions and ask instead of guessing.** If a requirement is ambiguous, state your interpretation and confirm before building on it.
- **Keep scope minimal.** Build v1 only. Deferred features are out of scope; do not build them and do not add abstractions for them beyond the two swap interfaces (ingest source, embeddings) named in the architecture document.
- **Start read-only and safe.** The system reads a mailbox and writes local files. It must send nothing and take no irreversible external action. When an action has side effects you are unsure about, ask first.
- **Never commit secrets.** Commit only `.env.example` and `.gitignore`; read secrets from the environment.
- **Work toward the Definition of Done** (below) and stop when it is met.

---

## Locked decisions — implement as specified, do not change

These were decided deliberately during design. If you believe one is wrong, raise it and wait for an answer. Do not silently change it.

- **The runtime is a fixed workflow, not an autonomous agent.** There is no runtime LLM orchestrator: at runtime no LLM decides which step runs next. The sequence is fixed in code and the trigger is a schedule. Do not add a planner, a reasoning loop, or an agent that selects steps.
- **Plain Python, no agent framework** (no LangGraph, no CrewAI). Pydantic for structured, validated LLM output.
- **SQLite** as the single source of truth; a **JSON** subset exported for the dashboard.
- **A static, data-driven dashboard** served by nginx with HTTP basic auth; client-side filtering and search; no backend or DB server.
- **Docker Compose**, two services (nginx `web`, Python `pipeline`) sharing one volume.
- **One source in v1:** newsletters over IMAP, behind a swappable `IngestSource` interface.
- **The LLM runs through OpenRouter**, one model for both LLM steps, referenced from config and never hardcoded.

---

## Open decisions — propose and confirm before committing

Do not guess silently on these. State your choice and reasoning, or ask.

- **OpenRouter model:** not chosen yet. Treat it as a config value. If you need one to test end to end, propose a current option and confirm.
- **Embeddings approach:** a hosted multilingual embeddings model (small image, negligible cost at this volume) or a local multilingual sentence-transformers model (no per-call cost, large image). Recommend one, keep it behind the embeddings interface, and confirm before committing to the heavier option.
- **Config format:** TOML is suggested; confirm if you prefer YAML.

---

## Scope out (deferred)

Additional sources (RSS, scraping, social), keyword and concept alerts, audience-adaptive presentation, the clickable glossary (v1.1), cross-time trend linking, and newsletter repurposing. The architecture document (Sections 1 and 11) explains how the design leaves room for each. Do not build them now.

---

## Definition of Done

Work toward the 12-item Definition of Done in the architecture document (Section 9), verifying each item. When all twelve verifiably hold, v1 is done. Stop there.
