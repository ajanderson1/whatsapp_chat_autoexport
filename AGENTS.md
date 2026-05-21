# AGENTS.md
> Project-specific context. Global conventions: ~/.conventions/CONVENTIONS.md.

## What this is

WhatsApp chat export automation for Android. Uses Appium + UiAutomator2 to drive the WhatsApp UI, trigger per-chat exports to Google Drive, then download, extract, transcribe (Whisper / ElevenLabs), and build a final organised output. Single-user tool; runs locally or in Docker.

## Stack constraints (overrides global defaults)
<!-- Empty here at PR 1 time. Entries are added by later PRs in the convention-alignment train. -->

## Canonical commands
- dev: n/a
- build: `docker build -t whatsapp-export .`
- test: `poetry run pytest`
- lint: `poetry run ruff check .`
- format: `poetry run ruff format .`
- typecheck: n/a

## Where things live
- `whatsapp_chat_autoexport/` — main package (moves to `src/whatsapp_chat_autoexport/` in a later PR).
- `tests/unit/`, `tests/integration/` — pytest suite.
- `docs/internals/architecture.md` — developer architecture reference (commands, workflows, testing strategy).
- `docs/superpowers/specs/` — design specs.
- `docs/superpowers/plans/` — implementation plans.
- `sample_data/` — real WhatsApp export used by tests.
- `.ai/` — portable prompt templates, skills, plans (harness-agnostic).

## Project glossary
- **ChatExporter** — orchestrates the per-chat WhatsApp → Drive export flow.
- **WhatsAppDriver** — Appium-based UI driver with verification + lock detection.
- **AppiumManager** — manages Appium server lifecycle on port 4723.
- **Preflight** — API credential capacity checks run before every session.
- **Pipeline** — download → extract → transcribe → build-output stages run after export.

## In-flight
- Convention alignment effort — see `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` and `docs/superpowers/plans/2026-05-21-convention-alignment.md`. Some commands above change as the train lands (poetry → uv; layout flat → `src/`; typecheck `n/a` → `mypy src/`).

## Autonomous allowlist
<!-- Empty. -->

## Project note
[Atlas/Whatsapp Chat AutoExport](obsidian://open?vault=Journal&file=Atlas%2FWhatsapp%20Chat%20AutoExport)
