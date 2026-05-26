# AGENTS.md
> Project-specific context. Global conventions: ~/.conventions/CONVENTIONS.md.

## What this is

WhatsApp chat export automation for Android. Uses Appium + UiAutomator2 to drive the WhatsApp UI, trigger per-chat exports to Google Drive, then download, extract, transcribe (Whisper / ElevenLabs), and build a final organised output. Single-user tool; runs locally or in Docker.

## Stack constraints (overrides global defaults)
<!-- Empty — project follows global defaults. -->

## Canonical commands
- dev: n/a
- build: `docker build -t whatsapp-export .`
- test: `uv run pytest`
- lint: `uv run ruff check .`
- format: `uv run ruff format .`
- typecheck: n/a

## Testing
- Standard suite (no device): `uv run pytest`.
- Self-verification loop against a real device (raw-ADB oracle + headless CLI / TUI pilot): see `TESTING.md`.

## Where things live
- `src/whatsapp_chat_autoexport/` — main package.
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
- Convention alignment effort — see `docs/superpowers/specs/2026-05-21-convention-alignment-design.md` and `docs/superpowers/plans/2026-05-21-convention-alignment.md`. Some commands above change as the train lands (typecheck `n/a` → `mypy src/`).

## Autonomous allowlist
<!-- Empty. -->

## Project note
[Atlas/Whatsapp Chat AutoExport](obsidian://open?vault=Journal&file=Atlas%2FWhatsapp%20Chat%20AutoExport)
