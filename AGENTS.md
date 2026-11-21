# AGENTS.md — AI Collaboration Rules for This Repository

> For any AI Agent entering this workspace (Claude Code, Codex, Cursor, Gemini CLI, Antigravity, etc.): read `GLOSSARY.md` and relevant ADRs in `docs/adr/` before modifying code or proposing architectural changes.

## Core Principles

1. **Zero PII Leak**: Never commit real personal chat logs (`raw/`), built SQLite databases (`*.db`), or user-specific personal files into git. Test only against `examples/sample_raw/` or isolated temp directories.
2. **Evidence Before Conclusion**: In Stage 3 cleaning and 4-way matching, vector scores are candidate recall signals only — never present raw cosine counts as final facts without checking Subject-Object Inversion and Negation Blindness guardrails plus stratified evidence excerpts.
3. **Keep Code Small and Single-Purpose**: Every script in `scripts/` must expose clean importable functions verified by `pytest`, run with Python stdlib by default (no mandatory heavyweight model download for CI), and degrade gracefully when optional vector backends are absent.

## Agent skills

### Issue tracker

Local markdown issues live under `.scratch/<feature-slug>/` (ready to switch to GitHub Issues once a GitHub remote is linked). See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical five-role triage label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo layout (`GLOSSARY.md` + `docs/adr/` at the repo root). See `docs/agents/domain.md`.
