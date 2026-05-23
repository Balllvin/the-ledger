# AGENTS.md

This repository is The Ledger, a local-first AI usage dashboard. Your job is to make it run on the current user's laptop without collecting, committing, uploading, or exposing their private usage records.

## Primary Goal

Install and run the dashboard locally, then adapt discovery so the app finds Codex records and Codex-linked application records wherever this laptop stores them and wherever the user permits scanning.

## Required Reading

Read these files before changing behavior:

- [docs/INSTALL.md](docs/INSTALL.md): OS-specific install and run commands.
- [docs/DISCOVERY.md](docs/DISCOVERY.md): how to locate Codex roots, auth presence, usage records, and app records.
- [docs/AI_CODING_AGENT_SKILL.md](docs/AI_CODING_AGENT_SKILL.md): end-to-end skill document for AI agents applying this app to a new laptop.
- [docs/DESIGN.md](docs/DESIGN.md): dashboard design rules.
- [docs/PUBLISHING.md](docs/PUBLISHING.md): branch, repo, and privacy-safe publishing workflow.
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md): exact read-only source contracts.

## Non-Negotiables

- Do not commit local usage data, logs, SQLite databases, JSONL sessions, auth files, generated images, or screenshots containing private usage.
- Do not print auth values, tokens, cookies, API keys, refresh tokens, or raw secret-like config values.
- Keep all collectors read-only.
- Prefer explicit environment variables over hardcoded user-specific paths.
- Use bounded scans. Do not crawl an entire disk by default.
- Make the app work on Windows, macOS, and Linux with Python 3.11+ and no required third-party packages.

## Implementation Direction

1. For a normal open request, run `bin/ledger` from the repository root in a long-running terminal session, verify `/healthz`, and open the printed URL.
2. Prefer `bin/ledger` over hand-written Python commands; it sets the bounded scan roots, avoids bytecode churn, reuses an existing healthy server, and starts the server reliably for agent workflows.
3. If no Codex records appear, follow [docs/DISCOVERY.md](docs/DISCOVERY.md) to find the local Codex root.
4. Set `CODEX_HOME` or `THE_LEDGER_SCAN_ROOTS` only when discovery needs help.
5. Keep UI changes simple: three pages, clear header switching, one primary chart, compact source health.
6. Add or update tests for parser, discovery, sanitizer, or app-specific collector changes.

## Expected Finish

A good adaptation ends with:

- Local server running.
- Browser dashboard loading.
- Tests passing.
- Discovered sources visible on the Sources page.
- No private records staged in git.
