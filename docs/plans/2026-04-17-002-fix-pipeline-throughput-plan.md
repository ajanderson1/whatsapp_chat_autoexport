---
title: "fix: Pipeline throughput + delete-from-drive (Fixes 4+5)"
type: fix
status: active
date: 2026-04-17
source-spec: docs/specs/2026-04-17-pipeline-throughput-design.md
source-report: docs/failure-reports/2026-04-16-full-run-pause.md
fixes: [4, 5]
---

# fix: Pipeline throughput + delete-from-drive implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the post-export pipeline keep pace with the 956-chat export phase and produce `delete-from-drive` actions that actually fire, by replacing time-filtered Drive polling with discovery-based listing, parallelising per-PTT transcription, bumping pipeline worker count to 4, and writing transcriptions to a durable cache so interrupted runs resume cheaply.

**Architecture:** Two mechanistic changes. (1) `drive_client.poll_for_new_export` (time-windowed poll loop) is replaced with `list_whatsapp_exports_in_folder` (single API call, no time filter); the pipeline uses per-chat submissions plus full discovery sweeps at start and end of run as the work queue. (2) `ParallelPipeline.max_workers` goes from 2 to 4; `TranscriptionManager.batch_transcribe` replaces its serial per-file loop with a `ThreadPoolExecutor(max_workers=8)` fan-out wrapped by `_transcribe_with_retry` (3 attempts, exponential backoff). A new `transcription/transcription_cache.py` module owns `~/.whatsapp_exports_cache/<chat>/transcriptions/` — transcriptions write here during phase 3 and are copied into the final output folder at phase 5. Peak concurrency: 4×8 = 32 in-flight API calls.

**Tech Stack:** Python 3.13, Poetry, pytest, `concurrent.futures.ThreadPoolExecutor`, Google Drive API v3 (`google-api-python-client`), OpenAI Whisper / ElevenLabs Scribe.

---

## Problem Frame

During a 956-chat run on 2026-04-16, the pipeline completed 3 chats in ~3 hours while the export phase produced 282 zips. Root cause investigation during brainstorming:

1. **Pipeline worker pool = 2.** Each worker processes one chat fully before picking up the next.
2. **Transcription inside a worker is serial.** 148 PTTs × 2s each = ~5 min of pure wall time per heavy chat, during which that worker cannot pick up any other chat. Queue grows unboundedly.
3. **Drive polling uses a 5-min `createdTime` filter.** When the queue backs up, files uploaded >5 min ago become invisible to polling, `wait_for_new_export` times out at 300s, download never runs, delete never runs. Fix 4 (`--delete-from-drive` never fires) is a downstream symptom of Fix 5.

The design spec (`docs/specs/2026-04-17-pipeline-throughput-design.md`) removes both root causes at once.

## Requirements Trace

- **R1.** Replace `drive_client.poll_for_new_export()` with `list_whatsapp_exports_in_folder(folder_id="root")` that returns all matching files in a single Drive API call, sorted by `createdTime` ascending, no age filter.
- **R2.** `ParallelPipeline.max_workers` default goes from 2 to 4. `submit()` accepts an optional `file_metadata` dict so workers skip per-chat polling when a file reference is already known.
- **R3.** `ParallelPipeline.submit_if_not_in_flight(chat_name, file_metadata)` — idempotent submit that no-ops if a task for that chat is already queued or running.
- **R4.** `TranscriptionManager.batch_transcribe` runs per-file transcription in a `ThreadPoolExecutor(max_workers=8)`. Order of `on_progress` callbacks may interleave (document this). Aggregate counts (`successful`, `skipped`, `failed`) remain accurate.
- **R5.** Each transcription call is wrapped by `_transcribe_with_retry(media_file, attempts=3, initial_delay=1.0)`. Retries on 429 rate-limit / network errors / timeouts; does not retry on 402 quota / 401 auth / 400 malformed / FileNotFound. Backoff: 1s, 2s, 4s.
- **R6.** Transcriptions are written to `~/.whatsapp_exports_cache/<chat-name>/transcriptions/<media_stem>_transcription.txt`, not to the media file's temp directory. `is_transcribed()` checks the cache path first, then the existing output directory (unchanged).
- **R7.** A new module `whatsapp_chat_autoexport/transcription/transcription_cache.py` is the single owner of cache-path logic. Env var `WHATSAPP_TRANSCRIPTION_CACHE_DIR` overrides the root (for tests).
- **R8.** `OutputBuilder._copy_transcriptions` is called with the cache dir as `source_dir` (pipeline passes it explicitly). No signature change.
- **R9.** `WhatsAppPipeline.process_single_export(chat_name, file_metadata=None)` accepts a pre-fetched file metadata dict. When supplied, the worker skips polling entirely and goes straight to `batch_download_exports([file_metadata])`. When `file_metadata is None`, the worker performs a targeted discovery (list Drive, filter by `chat_name`, 2s poll × up to 15 attempts = 30s window) before erroring.
- **R10.** `WhatsAppPipeline.discovery_sweep_now() -> int` lists the Drive folder once, submits any files not already in flight via `submit_if_not_in_flight`, and returns the count of newly-submitted tasks. This is called once at pipeline start (before the export loop) and once at pipeline end (after the export loop returns).
- **R11.** `--delete-from-drive` semantics unchanged: delete fires inside `batch_download_exports(delete_after=True)` after successful download. After the refactor it reliably *reaches* that code path.
- **R12.** Removed dead code: `poll_for_new_export`, `wait_for_new_export`, and the `PipelineConfig` fields `initial_interval`, `max_interval`, `poll_timeout`, `created_within_seconds`, `poll_interval`.
- **R13.** `README.md` gains a "Pipeline throughput & cache" section documenting the hard-coded concurrency values (4 workers × 8 transcriptions = 32 peak), the cache location, and how to reset it.
- **R14.** All changes covered by unit tests; one integration test validates resume behavior.

## Scope Boundaries

- This plan does NOT change any code in the Fix 1–3 PR (`chat_exporter.py`, `export_pane.py`, `foreground_wait.py`, `whatsapp_driver.py`, `chat_list.py`).
- This plan does NOT add adaptive concurrency (dynamic tuning based on 429s). Bounded retry only.
- This plan does NOT add a local manifest / SQLite / JSON pipeline-state file. Drive is the queue; the transcription cache is the only durable intermediate.
- This plan does NOT add Fix 6 (Retry-failed TUI button) — separate plan.
- This plan does NOT make concurrency settings CLI-configurable; values are hard-coded module constants and mentioned in the README.
- This plan does NOT touch the `legacy/` folder or `whatsapp_export.py` monolith.
- This plan does NOT alter the TUI UX or headless CLI surface; no new flags.
- This plan does NOT introduce new dependencies.

## Context & Research

### Current code

- `whatsapp_chat_autoexport/pipeline.py::WhatsAppPipeline.process_single_export` (line 117) — currently calls `drive_manager.wait_for_new_export(chat_name=chat_name, …)` at line 171. Deletes via `batch_download_exports(delete_after=self.config.delete_from_drive)` at line 187.
- `whatsapp_chat_autoexport/google_drive/drive_client.py::poll_for_new_export` (line 322) — loops 2s→8s, 5-min timeout, filters `createdTime > now-5min`.
- `whatsapp_chat_autoexport/google_drive/drive_manager.py::wait_for_new_export` (line 59) — thin wrapper that re-raises polling timeout as `RuntimeError`.
- `whatsapp_chat_autoexport/export/parallel_pipeline.py::ParallelPipeline.__init__` (line 57) — `max_workers=2` default.
- `whatsapp_chat_autoexport/export/parallel_pipeline.py::ParallelPipeline.submit` (line 75) — submits `_run_task(chat_name, google_drive_folder)`; does NOT currently accept file_metadata.
- `whatsapp_chat_autoexport/transcription/transcription_manager.py::batch_transcribe` (line 204) — serial `for i, media_file in enumerate(media_files, 1)` at line 277.
- `whatsapp_chat_autoexport/transcription/transcription_manager.py::get_transcription_path` (line 50) — currently returns `media_file.parent / f"{media_file.stem}_transcription.txt"`.
- `whatsapp_chat_autoexport/transcription/transcription_manager.py::is_transcribed` (line 63) — currently checks `get_transcription_path(media_file)` (temp) and `output_dir / contact_name / "transcriptions" / …` (previous runs).
- `whatsapp_chat_autoexport/output/output_builder.py::_copy_transcriptions` (line 355) — takes `source_dir: Path` and copies from there.

### Call sites that care about the refactor

- `pipeline.py::process_single_export` — the only caller of `wait_for_new_export`.
- `chat_exporter.py::_setup_pipeline` (around line 1650) — instantiates `ParallelPipeline(max_workers=max_concurrent)` where `max_concurrent = getattr(self.pipeline.config, 'max_concurrent', 2)`. After this plan, the default source (`PipelineConfig.max_concurrent`) changes to 4.
- `headless.py::run_headless` and `run_pipeline_only` — both construct `PipelineConfig`; no change needed since the default shifts.
- `tui/textual_panes/export_pane.py` — does not touch pipeline concurrency.

### Retry semantics reference

OpenAI SDK raises `openai.RateLimitError` for 429, `openai.AuthenticationError` for 401, `openai.NotFoundError` for missing, `openai.APIError` for general 5xx. ElevenLabs SDK raises `elevenlabs.core.api_error.ApiError` with a `.status_code` attribute. Both project transcribers today catch at the transcribe call boundary and set `result.success=False`, `result.error=<str>`. The retry wrapper inspects the error message for retriable patterns (`"rate limit"`, `"429"`, `"timeout"`, `"connection"`) — string-match rather than exception-type to stay provider-agnostic.

### Cache layout

```
~/.whatsapp_exports_cache/
├── Peter Cocking/
│   └── transcriptions/
│       ├── PTT-20230709-WA0000_transcription.txt
│       ├── PTT-20230710-WA0001_transcription.txt
│       └── …
├── Harry Droop/
│   └── transcriptions/
│       └── …
```

Chat name is the raw chat name as received by the pipeline (same string used in temp-dir prefixes today). No sanitisation beyond replacing `/` with `_` (which Python's filesystem layer would already reject).

### Test fixtures

- `tests/conftest.py` already provides `temp_output_dir` (auto-cleaned) and `mock_transcriber` — both used by the new tests.
- A new fixture `transcription_cache_tmp` needs to live in `conftest.py`: creates a temp dir, sets `WHATSAPP_TRANSCRIPTION_CACHE_DIR` for test scope, yields the path, cleans up.

## File Structure

**New files:**

- `whatsapp_chat_autoexport/transcription/transcription_cache.py` — module owning cache layout. Public API: `get_cache_root() -> Path`, `get_chat_cache_dir(chat_name) -> Path`, `get_transcription_cache_path(media_file, chat_name) -> Path`, `transcription_exists_in_cache(media_file, chat_name) -> bool`, `read_transcription_from_cache(media_file, chat_name) -> Optional[Path]`. Uses `os.environ.get("WHATSAPP_TRANSCRIPTION_CACHE_DIR")` with fallback to `Path.home() / ".whatsapp_exports_cache"`.
- `tests/unit/test_transcription_cache.py` — 6 tests for the cache module.
- `tests/unit/test_transcription_parallel.py` — 5 tests for `batch_transcribe` parallelism.
- `tests/unit/test_transcription_retry.py` — 7 tests for `_transcribe_with_retry`.
- `tests/unit/test_parallel_pipeline_submit_if_not_in_flight.py` — 4 tests for idempotent submission and worker-count default.
- `tests/unit/test_drive_client_list_exports.py` — 5 tests for `list_whatsapp_exports_in_folder`.
- `tests/unit/test_pipeline_discovery.py` — 4 tests for `discovery_sweep_now` and `process_single_export(file_metadata=...)`.
- `tests/unit/test_output_builder_cache_source.py` — 2 tests confirming output builder reads from cache path.
- `tests/integration/test_pipeline_resume.py` — 1 end-to-end resume test.

**Modified files:**

- `whatsapp_chat_autoexport/pipeline.py` — adds `discovery_sweep_now()`; `process_single_export` accepts `file_metadata: Optional[Dict] = None`; removes polling call when `file_metadata` supplied; adds `_targeted_discovery(chat_name, poll_interval=2, max_attempts=15)` private helper; passes chat-name-scoped cache dir to `OutputBuilder._copy_transcriptions`.
- `whatsapp_chat_autoexport/google_drive/drive_client.py` — removes `poll_for_new_export`; adds `list_whatsapp_exports_in_folder(folder_id: str = "root", chat_name: Optional[str] = None) -> List[Dict]`.
- `whatsapp_chat_autoexport/google_drive/drive_manager.py` — removes `wait_for_new_export`; adds `list_whatsapp_exports_in_folder` pass-through (thin wrapper for callers that use the manager).
- `whatsapp_chat_autoexport/export/parallel_pipeline.py` — `max_workers=2` → `max_workers=4` in `__init__`; `submit(chat_name, google_drive_folder=None, file_metadata=None)`; `submit_if_not_in_flight(...)` new method; `_run_task(chat_name, google_drive_folder, file_metadata)` passes file_metadata through to pipeline.
- `whatsapp_chat_autoexport/transcription/transcription_manager.py` — `get_transcription_path(media_file, chat_name=None)` routes through the cache module when `chat_name` is provided; `is_transcribed` checks the cache; `save_transcription` writes to cache; `batch_transcribe(media_files, chat_name=..., …)` accepts `chat_name` for cache routing and uses a `ThreadPoolExecutor(max_workers=8)` fan-out; new private `_transcribe_with_retry(media_file, attempts=3)`.
- `whatsapp_chat_autoexport/pipeline.py::_phase3_transcribe` (existing private helper) — passes `chat_name` into `batch_transcribe` so writes go to the cache.
- `whatsapp_chat_autoexport/pipeline.py::_phase4_build_outputs` — passes the cache dir for `chat_name` as `source_dir` when calling `output_builder` (which passes it through to `_copy_transcriptions`).
- `whatsapp_chat_autoexport/pipeline.py::PipelineConfig` — removes `initial_interval`, `max_interval`, `poll_timeout`, `created_within_seconds`, `poll_interval` fields; bumps `max_concurrent` default from 2 to 4.
- `tests/conftest.py` — adds `transcription_cache_tmp` fixture.
- `README.md` — adds "Pipeline throughput & cache" section.

**Removed code:**

- `drive_client.py::poll_for_new_export` — method body deleted (all callers moved).
- `drive_manager.py::wait_for_new_export` — method body deleted.
- `pipeline.py::PipelineConfig` — 5 polling-related fields deleted.

Decomposition rationale: one module per concern. `transcription_cache.py` owns path logic so neither the manager, the pipeline, nor the output builder need to reimplement it. `_transcribe_with_retry` lives inside the manager because it's the only caller. `discovery_sweep_now` lives on the pipeline because that's where the work queue is consumed.

---

## Task Decomposition

### Task 1: Create `transcription_cache` module

**Files:**
- Create: `whatsapp_chat_autoexport/transcription/transcription_cache.py`
- Test:   `tests/unit/test_transcription_cache.py`
- Modify: `tests/conftest.py` (add fixture)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_transcription_cache.py
"""Tests for transcription cache path helpers."""

import os
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.transcription.transcription_cache import (
    get_cache_root,
    get_chat_cache_dir,
    get_transcription_cache_path,
    transcription_exists_in_cache,
    read_transcription_from_cache,
)


def test_get_cache_root_defaults_to_home_dotfile(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TRANSCRIPTION_CACHE_DIR", raising=False)
    assert get_cache_root() == Path.home() / ".whatsapp_exports_cache"


def test_get_cache_root_honours_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_TRANSCRIPTION_CACHE_DIR", str(tmp_path))
    assert get_cache_root() == tmp_path


def test_get_chat_cache_dir_creates_on_access(transcription_cache_tmp):
    chat_dir = get_chat_cache_dir("Peter Cocking")
    assert chat_dir == transcription_cache_tmp / "Peter Cocking" / "transcriptions"
    assert chat_dir.exists()
    assert chat_dir.is_dir()


def test_get_transcription_cache_path_format(transcription_cache_tmp):
    media = Path("/tmp/whatsapp_xyz/media/PTT-20230101-WA0000.opus")
    result = get_transcription_cache_path(media, "Peter Cocking")
    assert result.parent == transcription_cache_tmp / "Peter Cocking" / "transcriptions"
    assert result.name == "PTT-20230101-WA0000_transcription.txt"


def test_transcription_exists_in_cache_false_when_missing(transcription_cache_tmp):
    media = Path("/tmp/whatsapp_xyz/media/PTT-absent.opus")
    assert transcription_exists_in_cache(media, "Peter Cocking") is False


def test_transcription_exists_in_cache_true_when_non_empty(transcription_cache_tmp):
    media = Path("/tmp/whatsapp_xyz/media/PTT-present.opus")
    cache_path = get_transcription_cache_path(media, "Peter Cocking")
    cache_path.write_text("hello")
    assert transcription_exists_in_cache(media, "Peter Cocking") is True


def test_transcription_exists_in_cache_false_when_zero_bytes(transcription_cache_tmp):
    """A zero-byte cache file is treated as absent so a partial write does not hide a retry."""
    media = Path("/tmp/whatsapp_xyz/media/PTT-empty.opus")
    cache_path = get_transcription_cache_path(media, "Peter Cocking")
    cache_path.write_text("")
    assert transcription_exists_in_cache(media, "Peter Cocking") is False


def test_read_transcription_from_cache_returns_path_or_none(transcription_cache_tmp):
    media_present = Path("/tmp/whatsapp_xyz/media/PTT-hit.opus")
    get_transcription_cache_path(media_present, "Peter Cocking").write_text("text")
    assert read_transcription_from_cache(media_present, "Peter Cocking") is not None

    media_absent = Path("/tmp/whatsapp_xyz/media/PTT-miss.opus")
    assert read_transcription_from_cache(media_absent, "Peter Cocking") is None
```

In `tests/conftest.py`, append:

```python
@pytest.fixture
def transcription_cache_tmp(tmp_path, monkeypatch):
    """Point the transcription cache at a temp dir for the duration of the test."""
    monkeypatch.setenv("WHATSAPP_TRANSCRIPTION_CACHE_DIR", str(tmp_path))
    yield tmp_path
```

- [ ] **Step 2: Run tests — expect failure (module not found)**

Run: `poetry run pytest tests/unit/test_transcription_cache.py -v --no-cov`
Expected: `ModuleNotFoundError: No module named 'whatsapp_chat_autoexport.transcription.transcription_cache'`

- [ ] **Step 3: Implement the module**

```python
# whatsapp_chat_autoexport/transcription/transcription_cache.py
"""
Transcription cache.

Transcriptions live durably in ``~/.whatsapp_exports_cache/<chat>/transcriptions/``
so that an interrupted pipeline run can be resumed without re-transcribing work
already completed. The output builder copies from this cache into the final
``~/whatsapp_exports/<chat>/transcriptions/`` directory at phase 5.

Safe to delete the whole cache directory - the next run just re-transcribes.
"""

import os
from pathlib import Path
from typing import Optional


_TRANSCRIPTION_SUFFIX = "_transcription.txt"


def get_cache_root() -> Path:
    """Root directory for the transcription cache.

    Honours ``WHATSAPP_TRANSCRIPTION_CACHE_DIR`` env var for tests; otherwise
    ``~/.whatsapp_exports_cache``.
    """
    override = os.environ.get("WHATSAPP_TRANSCRIPTION_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".whatsapp_exports_cache"


def get_chat_cache_dir(chat_name: str) -> Path:
    """Return (and create) the per-chat transcription cache directory."""
    chat_dir = get_cache_root() / chat_name / "transcriptions"
    chat_dir.mkdir(parents=True, exist_ok=True)
    return chat_dir


def get_transcription_cache_path(media_file: Path, chat_name: str) -> Path:
    """Return the cache path where ``media_file``'s transcription belongs."""
    return get_chat_cache_dir(chat_name) / f"{media_file.stem}{_TRANSCRIPTION_SUFFIX}"


def transcription_exists_in_cache(media_file: Path, chat_name: str) -> bool:
    """True iff a non-empty transcription exists in the cache for ``media_file``.

    Zero-byte files are treated as absent: a partial/interrupted write should not
    hide a retry on a subsequent run.
    """
    path = get_transcription_cache_path(media_file, chat_name)
    return path.exists() and path.stat().st_size > 0


def read_transcription_from_cache(
    media_file: Path, chat_name: str
) -> Optional[Path]:
    """Return the cache path if a transcription exists for ``media_file``, else None."""
    if transcription_exists_in_cache(media_file, chat_name):
        return get_transcription_cache_path(media_file, chat_name)
    return None
```

- [ ] **Step 4: Run tests — expect 8 passed**

Run: `poetry run pytest tests/unit/test_transcription_cache.py -v --no-cov`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/transcription/transcription_cache.py \
        tests/unit/test_transcription_cache.py \
        tests/conftest.py
git commit -m "feat(transcription): add durable transcription cache module"
```

---

### Task 2: Route `TranscriptionManager` through the cache

**Files:**
- Modify: `whatsapp_chat_autoexport/transcription/transcription_manager.py` (methods `get_transcription_path`, `is_transcribed`, `save_transcription`, `transcribe_file`, `batch_transcribe`)
- Test:   `tests/unit/test_transcription.py` (existing, extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_transcription.py`:

```python
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.transcription.transcription_manager import (
    TranscriptionManager,
)
from whatsapp_chat_autoexport.transcription.base_transcriber import (
    TranscriptionResult,
)


class TestTranscriptionCacheIntegration:
    """TranscriptionManager writes to the cache when chat_name is supplied."""

    def _mk_manager(self, transcription_cache_tmp):
        transcriber = MagicMock()
        transcriber.is_available.return_value = True
        transcriber.validate_file.return_value = (True, None)
        transcriber.transcribe.return_value = TranscriptionResult(
            text="hello", success=True, language="en"
        )
        return TranscriptionManager(transcriber=transcriber)

    def test_save_transcription_writes_to_cache_when_chat_name_given(
        self, tmp_path, transcription_cache_tmp
    ):
        mgr = self._mk_manager(transcription_cache_tmp)
        media = tmp_path / "media" / "PTT-001.opus"
        media.parent.mkdir()
        media.write_bytes(b"fake audio")

        result = TranscriptionResult(text="hello", success=True)
        out_path = mgr.save_transcription(
            media, result, include_metadata=False, chat_name="Peter Cocking"
        )

        expected = (
            transcription_cache_tmp / "Peter Cocking" / "transcriptions"
            / "PTT-001_transcription.txt"
        )
        assert out_path == expected
        assert out_path.read_text().strip() == "hello"

    def test_save_transcription_falls_back_to_media_dir_without_chat_name(
        self, tmp_path
    ):
        mgr = self._mk_manager(tmp_path)
        media = tmp_path / "media" / "PTT-002.opus"
        media.parent.mkdir()
        media.write_bytes(b"fake audio")

        result = TranscriptionResult(text="hi", success=True)
        out_path = mgr.save_transcription(media, result, include_metadata=False)

        assert out_path == tmp_path / "media" / "PTT-002_transcription.txt"

    def test_is_transcribed_checks_cache_when_chat_name_given(
        self, tmp_path, transcription_cache_tmp
    ):
        mgr = self._mk_manager(transcription_cache_tmp)
        media = tmp_path / "media" / "PTT-003.opus"
        media.parent.mkdir()
        media.write_bytes(b"fake audio")

        # Seed cache
        cache_path = (
            transcription_cache_tmp / "Peter Cocking" / "transcriptions"
            / "PTT-003_transcription.txt"
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("cached")

        found, location = mgr.is_transcribed(media, chat_name="Peter Cocking")
        assert found is True
        assert location == "cache"
```

- [ ] **Step 2: Run test — expect failure**

Run: `poetry run pytest tests/unit/test_transcription.py::TestTranscriptionCacheIntegration -v --no-cov`
Expected: `TypeError: save_transcription() got an unexpected keyword argument 'chat_name'` (or similar).

- [ ] **Step 3: Implement**

In `transcription_manager.py`, add near the imports:

```python
from .transcription_cache import (
    get_transcription_cache_path,
    transcription_exists_in_cache,
)
```

Replace `get_transcription_path`:

```python
    def get_transcription_path(
        self, media_file: Path, chat_name: Optional[str] = None
    ) -> Path:
        """Return the output path for a transcription file.

        When ``chat_name`` is supplied, returns the durable cache path under
        ``~/.whatsapp_exports_cache/<chat_name>/transcriptions/``. Otherwise
        falls back to the legacy behaviour of writing alongside the media file.
        The cache path is preferred for pipeline runs because it survives
        temp-dir cleanup and lets interrupted runs resume cheaply.
        """
        if chat_name:
            return get_transcription_cache_path(media_file, chat_name)
        return media_file.parent / f"{media_file.stem}{self.TRANSCRIPTION_SUFFIX}"
```

Replace `is_transcribed`:

```python
    def is_transcribed(
        self,
        media_file: Path,
        transcript_path: Optional[Path] = None,
        chat_name: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Check if a media file has already been transcribed.

        Checks up to three locations:
        1. Durable cache (if chat_name is given) -> "cache"
        2. Temp processing directory -> "temp"
        3. Final output directory (previous runs) -> "output"
        """
        # 1. Cache
        if chat_name and transcription_exists_in_cache(media_file, chat_name):
            return True, "cache"

        # 2. Temp
        temp_transcription_path = (
            media_file.parent / f"{media_file.stem}{self.TRANSCRIPTION_SUFFIX}"
        )
        if temp_transcription_path.exists() and temp_transcription_path.stat().st_size > 0:
            return True, "temp"

        # 3. Final output directory (from previous runs)
        if self.output_dir and transcript_path and self.contact_name_extractor:
            try:
                contact_name = self.contact_name_extractor(transcript_path)
                output_transcription_path = (
                    self.output_dir / contact_name / "transcriptions" /
                    f"{media_file.stem}{self.TRANSCRIPTION_SUFFIX}"
                )
                if output_transcription_path.exists() and output_transcription_path.stat().st_size > 0:
                    return True, "output"
            except Exception as e:
                self.logger.debug_msg(
                    f"Could not check output directory for {media_file.name}: {e}"
                )

        return False, None
```

Update `save_transcription` signature and body — add `chat_name` parameter and route through `get_transcription_path`:

```python
    def save_transcription(
        self,
        media_file: Path,
        result: TranscriptionResult,
        include_metadata: bool = True,
        chat_name: Optional[str] = None,
    ) -> Optional[Path]:
        """Save transcription result to file.

        When ``chat_name`` is supplied, writes to the durable cache; otherwise
        writes alongside the media file.
        """
        if not result.success or not result.text:
            self.logger.error(f"Cannot save failed transcription for {media_file.name}")
            return None

        transcription_path = self.get_transcription_path(media_file, chat_name=chat_name)

        try:
            with open(transcription_path, 'w', encoding='utf-8') as f:
                if include_metadata:
                    f.write(f"# Transcription of: {media_file.name}\n")
                    f.write(f"# Transcribed at: {result.timestamp}\n")
                    if result.language:
                        f.write(f"# Language: {result.language}\n")
                    if result.duration_seconds:
                        f.write(f"# Processing time: {result.duration_seconds:.2f}s\n")
                    if result.metadata:
                        f.write(f"# Model: {result.metadata.get('model', 'unknown')}\n")
                    f.write("\n")
                f.write(result.text)
                f.write("\n")

            self.logger.success(f"Saved transcription: {transcription_path.name}")
            return transcription_path

        except Exception as e:
            self.logger.error(f"Failed to save transcription: {e}")
            return None
```

Update `transcribe_file` to thread `chat_name` through:

```python
    def transcribe_file(
        self,
        media_file: Path,
        skip_existing: bool = True,
        transcript_path: Optional[Path] = None,
        chat_name: Optional[str] = None,
        **transcribe_kwargs
    ) -> Tuple[bool, Optional[Path], Optional[str]]:
        if skip_existing:
            is_transcribed, location = self.is_transcribed(
                media_file, transcript_path, chat_name=chat_name
            )
            if is_transcribed:
                if location == "cache":
                    self.logger.info(
                        f"⏭️  Skipping (cache hit): {chat_name}/{media_file.name}"
                    )
                elif location == "output" and self.contact_name_extractor and transcript_path:
                    contact_name = self.contact_name_extractor(transcript_path)
                    self.logger.info(
                        f"⏭️  Skipping (found in output): {contact_name}/{media_file.name}"
                    )
                else:
                    folder_name = media_file.parent.name
                    self.logger.info(
                        f"⏭️  Skipping (found in temp): {folder_name}/{media_file.name}"
                    )
                return True, self.get_transcription_path(media_file, chat_name=chat_name), None

        is_valid, error_msg = self.transcriber.validate_file(media_file)
        if not is_valid:
            self.logger.error(f"Invalid file: {error_msg}")
            return False, None, error_msg

        result = self.transcriber.transcribe(
            media_file, skip_existing=skip_existing, **transcribe_kwargs
        )

        if not result.success:
            return False, None, result.error

        transcription_path = self.save_transcription(
            media_file, result, chat_name=chat_name
        )

        if transcription_path:
            return True, transcription_path, None
        else:
            return False, None, "Failed to save transcription"
```

- [ ] **Step 4: Run tests — expect pass**

Run: `poetry run pytest tests/unit/test_transcription.py -v --no-cov`
Expected: all tests pass, including the three new ones.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/transcription/transcription_manager.py \
        tests/unit/test_transcription.py
git commit -m "feat(transcription): route TranscriptionManager through durable cache when chat_name supplied"
```

---

### Task 3: Add `_transcribe_with_retry` wrapper

**Files:**
- Modify: `whatsapp_chat_autoexport/transcription/transcription_manager.py` (add private method)
- Test:   `tests/unit/test_transcription_retry.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_transcription_retry.py
"""Tests for bounded retry wrapper around transcription API calls."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.transcription.transcription_manager import (
    TranscriptionManager,
)
from whatsapp_chat_autoexport.transcription.base_transcriber import (
    TranscriptionResult,
)


@pytest.fixture
def manager():
    transcriber = MagicMock()
    transcriber.is_available.return_value = True
    transcriber.validate_file.return_value = (True, None)
    return TranscriptionManager(transcriber=transcriber)


def test_retries_429_and_succeeds_on_third_attempt(manager, tmp_path, monkeypatch):
    media = tmp_path / "PTT-001.opus"
    media.write_bytes(b"fake")
    results = [
        TranscriptionResult(text="", success=False, error="429 rate limit exceeded"),
        TranscriptionResult(text="", success=False, error="429 rate limit exceeded"),
        TranscriptionResult(text="hello", success=True),
    ]
    manager.transcriber.transcribe.side_effect = results

    slept = []
    monkeypatch.setattr(
        "whatsapp_chat_autoexport.transcription.transcription_manager.time.sleep",
        lambda s: slept.append(s),
    )

    final = manager._transcribe_with_retry(media, attempts=3, initial_delay=1.0)
    assert final.success is True
    assert final.text == "hello"
    assert slept == [1.0, 2.0]  # two backoffs before the third attempt
    assert manager.transcriber.transcribe.call_count == 3


def test_does_not_retry_on_402_quota(manager, tmp_path, monkeypatch):
    media = tmp_path / "PTT-002.opus"
    media.write_bytes(b"fake")
    manager.transcriber.transcribe.return_value = TranscriptionResult(
        text="", success=False, error="insufficient_quota (402)"
    )

    slept = []
    monkeypatch.setattr(
        "whatsapp_chat_autoexport.transcription.transcription_manager.time.sleep",
        lambda s: slept.append(s),
    )

    final = manager._transcribe_with_retry(media, attempts=3, initial_delay=1.0)
    assert final.success is False
    assert slept == []
    assert manager.transcriber.transcribe.call_count == 1


def test_does_not_retry_on_401_auth(manager, tmp_path, monkeypatch):
    media = tmp_path / "PTT-003.opus"
    media.write_bytes(b"fake")
    manager.transcriber.transcribe.return_value = TranscriptionResult(
        text="", success=False, error="401 unauthorized"
    )

    monkeypatch.setattr(
        "whatsapp_chat_autoexport.transcription.transcription_manager.time.sleep",
        lambda s: None,
    )

    final = manager._transcribe_with_retry(media, attempts=3, initial_delay=1.0)
    assert final.success is False
    assert manager.transcriber.transcribe.call_count == 1


def test_retries_network_error(manager, tmp_path, monkeypatch):
    media = tmp_path / "PTT-004.opus"
    media.write_bytes(b"fake")
    manager.transcriber.transcribe.side_effect = [
        TranscriptionResult(text="", success=False, error="Connection timeout"),
        TranscriptionResult(text="ok", success=True),
    ]
    monkeypatch.setattr(
        "whatsapp_chat_autoexport.transcription.transcription_manager.time.sleep",
        lambda s: None,
    )

    final = manager._transcribe_with_retry(media, attempts=3, initial_delay=0.01)
    assert final.success is True


def test_exhausts_attempts_on_sustained_failure(manager, tmp_path, monkeypatch):
    media = tmp_path / "PTT-005.opus"
    media.write_bytes(b"fake")
    manager.transcriber.transcribe.return_value = TranscriptionResult(
        text="", success=False, error="429 rate limit exceeded"
    )
    monkeypatch.setattr(
        "whatsapp_chat_autoexport.transcription.transcription_manager.time.sleep",
        lambda s: None,
    )

    final = manager._transcribe_with_retry(media, attempts=3, initial_delay=0.01)
    assert final.success is False
    assert manager.transcriber.transcribe.call_count == 3


def test_backoff_doubles_each_attempt(manager, tmp_path, monkeypatch):
    media = tmp_path / "PTT-006.opus"
    media.write_bytes(b"fake")
    manager.transcriber.transcribe.return_value = TranscriptionResult(
        text="", success=False, error="timeout"
    )
    slept = []
    monkeypatch.setattr(
        "whatsapp_chat_autoexport.transcription.transcription_manager.time.sleep",
        lambda s: slept.append(s),
    )

    manager._transcribe_with_retry(media, attempts=4, initial_delay=1.0)
    # 3 backoffs between 4 attempts: 1, 2, 4
    assert slept == [1.0, 2.0, 4.0]


def test_retriable_vs_nonretriable_matcher():
    from whatsapp_chat_autoexport.transcription.transcription_manager import (
        _is_retriable_error,
    )
    assert _is_retriable_error("429 rate limit exceeded") is True
    assert _is_retriable_error("Connection timeout") is True
    assert _is_retriable_error("ReadTimeout") is True
    assert _is_retriable_error("Rate limit reached for requests") is True

    assert _is_retriable_error("insufficient_quota") is False
    assert _is_retriable_error("401 unauthorized") is False
    assert _is_retriable_error("400 bad request") is False
    assert _is_retriable_error("File not found") is False
    assert _is_retriable_error("") is False
```

- [ ] **Step 2: Run tests — expect failure**

Run: `poetry run pytest tests/unit/test_transcription_retry.py -v --no-cov`
Expected: `AttributeError: 'TranscriptionManager' object has no attribute '_transcribe_with_retry'`

- [ ] **Step 3: Implement**

In `transcription_manager.py`, add near the top of the module (after imports):

```python
import time

_RETRIABLE_PATTERNS = (
    "429",
    "rate limit",
    "timeout",
    "connection",
    "server error",
    "502",
    "503",
    "504",
)

_NONRETRIABLE_PATTERNS = (
    "401",
    "402",
    "400",
    "unauthorized",
    "insufficient_quota",
    "bad request",
    "not found",
)


def _is_retriable_error(error_message: str) -> bool:
    """True if the error text matches a transient-failure pattern.

    Non-retriable matches take precedence over retriable matches so that a
    message like "400 bad request (rate limit)" is treated as non-retriable.
    String-match rather than exception-type keeps this provider-agnostic.
    """
    if not error_message:
        return False
    lower = error_message.lower()
    for pat in _NONRETRIABLE_PATTERNS:
        if pat in lower:
            return False
    for pat in _RETRIABLE_PATTERNS:
        if pat in lower:
            return True
    return False
```

Add the method to `TranscriptionManager`:

```python
    def _transcribe_with_retry(
        self,
        media_file: Path,
        attempts: int = 3,
        initial_delay: float = 1.0,
        **transcribe_kwargs,
    ) -> TranscriptionResult:
        """Call the transcriber up to ``attempts`` times with exponential backoff.

        Retries on transient errors (429 / timeout / connection); returns
        immediately on non-retriable errors (402 / 401 / 400).

        Backoff schedule: initial_delay, 2*initial_delay, 4*initial_delay, ...
        Sleeps between attempts only, not after the final one.
        """
        last_result = None
        delay = initial_delay
        for attempt in range(1, attempts + 1):
            result = self.transcriber.transcribe(media_file, **transcribe_kwargs)
            if result.success:
                return result
            last_result = result
            if not _is_retriable_error(result.error or ""):
                self.logger.debug_msg(
                    f"Non-retriable error for {media_file.name}: {result.error}"
                )
                return result
            if attempt < attempts:
                self.logger.debug_msg(
                    f"Retriable error for {media_file.name} (attempt {attempt}/{attempts}): "
                    f"{result.error}. Sleeping {delay}s."
                )
                time.sleep(delay)
                delay *= 2
        return last_result
```

- [ ] **Step 4: Run tests — expect 7 passed**

Run: `poetry run pytest tests/unit/test_transcription_retry.py -v --no-cov`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/transcription/transcription_manager.py \
        tests/unit/test_transcription_retry.py
git commit -m "feat(transcription): add bounded retry wrapper with exponential backoff"
```

---

### Task 4: Parallel `batch_transcribe`

**Files:**
- Modify: `whatsapp_chat_autoexport/transcription/transcription_manager.py::batch_transcribe`
- Test:   `tests/unit/test_transcription_parallel.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_transcription_parallel.py
"""Tests for parallel per-file transcription in batch_transcribe."""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.transcription.transcription_manager import (
    TranscriptionManager,
)
from whatsapp_chat_autoexport.transcription.base_transcriber import (
    TranscriptionResult,
)


def _make_media_files(tmp_path, n=8):
    files = []
    for i in range(n):
        p = tmp_path / f"PTT-{i:03d}.opus"
        p.write_bytes(b"fake audio")
        files.append(p)
    return files


def test_batch_transcribe_runs_at_least_4_concurrently(tmp_path):
    """Smoke test: 8 files with a 200ms-per-file transcriber should finish under 400ms if concurrency is >= 4."""
    transcriber = MagicMock()
    transcriber.is_available.return_value = True
    transcriber.validate_file.return_value = (True, None)

    def slow_transcribe(media_file, **kwargs):
        time.sleep(0.2)
        return TranscriptionResult(text="ok", success=True)

    transcriber.transcribe.side_effect = slow_transcribe

    mgr = TranscriptionManager(transcriber=transcriber)
    files = _make_media_files(tmp_path, n=8)

    start = time.monotonic()
    results = mgr.batch_transcribe(files, skip_existing=False, show_progress=False)
    elapsed = time.monotonic() - start

    # Serial would be >= 1.6s; concurrency >=4 should stay under ~0.7s even on a
    # loaded CI runner.
    assert elapsed < 0.7, f"batch_transcribe took {elapsed:.2f}s; concurrency not active"
    assert results["successful"] == 8
    assert results["failed"] == 0


def test_batch_transcribe_preserves_result_totals_with_mixed_outcomes(tmp_path):
    transcriber = MagicMock()
    transcriber.is_available.return_value = True
    transcriber.validate_file.return_value = (True, None)

    outcomes = [
        TranscriptionResult(text="a", success=True),
        TranscriptionResult(text="", success=False, error="insufficient_quota"),
        TranscriptionResult(text="c", success=True),
        TranscriptionResult(text="", success=False, error="insufficient_quota"),
    ]
    transcriber.transcribe.side_effect = outcomes

    mgr = TranscriptionManager(transcriber=transcriber)
    files = _make_media_files(tmp_path, n=4)

    results = mgr.batch_transcribe(files, skip_existing=False, show_progress=False)

    assert results["total"] == 4
    assert results["successful"] == 2
    assert results["failed"] == 2
    assert len(results["errors"]) == 2


def test_batch_transcribe_fires_on_progress_once_per_file(tmp_path):
    transcriber = MagicMock()
    transcriber.is_available.return_value = True
    transcriber.validate_file.return_value = (True, None)
    transcriber.transcribe.return_value = TranscriptionResult(text="x", success=True)

    mgr = TranscriptionManager(transcriber=transcriber)
    files = _make_media_files(tmp_path, n=5)

    events = []
    def on_progress(phase, message, current, total, item_name=""):
        events.append((phase, current, total))

    mgr.batch_transcribe(
        files, skip_existing=False, show_progress=False, on_progress=on_progress
    )

    assert len(events) == 5
    assert {e[0] for e in events} == {"transcribe"}
    totals = {e[2] for e in events}
    assert totals == {5}


def test_batch_transcribe_honours_cache_when_chat_name_supplied(
    tmp_path, transcription_cache_tmp
):
    transcriber = MagicMock()
    transcriber.is_available.return_value = True
    transcriber.validate_file.return_value = (True, None)
    transcriber.transcribe.return_value = TranscriptionResult(text="x", success=True)

    mgr = TranscriptionManager(transcriber=transcriber)
    files = _make_media_files(tmp_path, n=3)

    # Seed cache for file 0 and 1 only
    cache_dir = transcription_cache_tmp / "Peter Cocking" / "transcriptions"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{files[0].stem}_transcription.txt").write_text("cached-0")
    (cache_dir / f"{files[1].stem}_transcription.txt").write_text("cached-1")

    results = mgr.batch_transcribe(
        files,
        skip_existing=True,
        show_progress=False,
        chat_name="Peter Cocking",
    )

    # 2 cache hits, 1 fresh transcription
    assert results["skipped"] == 2
    assert results["successful"] == 1
    assert transcriber.transcribe.call_count == 1


def test_batch_transcribe_applies_retry_to_each_call(tmp_path):
    transcriber = MagicMock()
    transcriber.is_available.return_value = True
    transcriber.validate_file.return_value = (True, None)
    transcriber.transcribe.side_effect = [
        TranscriptionResult(text="", success=False, error="429 rate limit"),
        TranscriptionResult(text="a", success=True),
    ]

    mgr = TranscriptionManager(transcriber=transcriber)
    files = _make_media_files(tmp_path, n=1)

    results = mgr.batch_transcribe(files, skip_existing=False, show_progress=False)

    assert results["successful"] == 1
    assert transcriber.transcribe.call_count == 2
```

- [ ] **Step 2: Run tests — expect failure**

Run: `poetry run pytest tests/unit/test_transcription_parallel.py -v --no-cov`
Expected: failures — `batch_transcribe` is still serial, does not use `_transcribe_with_retry`, does not accept `chat_name`.

- [ ] **Step 3: Implement**

Replace the body of `batch_transcribe` in `transcription_manager.py` (was a serial for-loop starting around line 277). New signature and body:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_TRANSCRIPTION_CONCURRENCY = 8  # module constant; documented in README


def batch_transcribe(
    self,
    media_files: List[Path],
    skip_existing: bool = True,
    show_progress: bool = True,
    transcript_path: Optional[Path] = None,
    on_progress: Optional[Callable] = None,
    chat_name: Optional[str] = None,
    **transcribe_kwargs,
) -> Dict[str, any]:
    """Transcribe multiple files in parallel with bounded concurrency and retry.

    Per-file transcriptions run via a ``ThreadPoolExecutor(max_workers=8)``;
    each call is wrapped by ``_transcribe_with_retry`` (3 attempts, exponential
    backoff).

    When ``chat_name`` is supplied, transcriptions are written to the durable
    cache and the cache is consulted by ``is_transcribed`` for skip decisions.

    The order of ``on_progress`` callbacks may interleave with respect to
    ``media_files`` input order (results arrive in completion order). Aggregate
    counts (``successful`` / ``skipped`` / ``failed``) remain accurate.
    """
    if not media_files:
        self.logger.warning("No media files to transcribe")
        return {
            "total": 0,
            "successful": 0,
            "skipped": 0,
            "failed": 0,
            "transcriptions": [],
            "skipped_files": [],
            "errors": [],
        }

    self.logger.info(f"Transcribing {len(media_files)} file(s)...")

    if not self.transcriber.is_available():
        self.logger.error("Transcription service not available")
        return {
            "total": len(media_files),
            "successful": 0,
            "skipped": 0,
            "failed": len(media_files),
            "transcriptions": [],
            "skipped_files": [],
            "errors": [(f, "Transcription service not available") for f in media_files],
        }

    results = {
        "total": len(media_files),
        "successful": 0,
        "skipped": 0,
        "failed": 0,
        "transcriptions": [],
        "skipped_files": [],
        "errors": [],
    }
    total_files = len(media_files)
    completed = 0

    def _process_one(media_file: Path):
        already_transcribed, _loc = (
            self.is_transcribed(media_file, transcript_path, chat_name=chat_name)
            if skip_existing
            else (False, None)
        )
        if already_transcribed:
            return ("skipped", media_file, self.get_transcription_path(media_file, chat_name=chat_name), None)

        is_valid, error_msg = self.transcriber.validate_file(media_file)
        if not is_valid:
            return ("failed", media_file, None, error_msg or "Invalid file")

        result = self._transcribe_with_retry(
            media_file, attempts=3, initial_delay=1.0, **transcribe_kwargs
        )
        if not result.success:
            return ("failed", media_file, None, result.error or "Unknown error")

        path = self.save_transcription(media_file, result, chat_name=chat_name)
        if path:
            return ("success", media_file, path, None)
        return ("failed", media_file, None, "Failed to save transcription")

    with ThreadPoolExecutor(max_workers=MAX_TRANSCRIPTION_CONCURRENCY) as pool:
        futures = {pool.submit(_process_one, mf): mf for mf in media_files}
        for future in as_completed(futures):
            media_file = futures[future]
            outcome, mf, path, err = future.result()
            completed += 1

            if show_progress:
                self.logger.info(f"[{completed}/{total_files}] {mf.name}: {outcome}")

            if outcome == "success":
                results["successful"] += 1
                if path:
                    results["transcriptions"].append(path)
            elif outcome == "skipped":
                results["skipped"] += 1
                results["skipped_files"].append(mf)
                if path:
                    results["transcriptions"].append(path)
            else:
                results["failed"] += 1
                results["errors"].append((mf, err or "Unknown error"))

            if on_progress:
                try:
                    on_progress(
                        "transcribe",
                        f"Transcribed {mf.name}" if outcome != "failed"
                        else f"Failed {mf.name}",
                        completed,
                        total_files,
                        mf.name,
                    )
                except Exception:
                    pass

    self.logger.info("=" * 70)
    self.logger.info("Transcription Summary")
    self.logger.info("=" * 70)
    self.logger.info(f"Total files: {results['total']}")
    self.logger.success(f"Successful: {results['successful']}")
    if results["skipped"] > 0:
        self.logger.info(f"Skipped (existing): {results['skipped']}")
    if results["failed"] > 0:
        self.logger.error(f"Failed: {results['failed']}")
    return results
```

- [ ] **Step 4: Run tests — expect pass**

Run: `poetry run pytest tests/unit/test_transcription_parallel.py tests/unit/test_transcription.py tests/unit/test_transcription_retry.py -v --no-cov`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/transcription/transcription_manager.py \
        tests/unit/test_transcription_parallel.py
git commit -m "feat(transcription): parallelise batch_transcribe with 8-wide ThreadPoolExecutor"
```

---

### Task 5: `list_whatsapp_exports_in_folder` on `GoogleDriveClient`

**Files:**
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py`
- Test:   `tests/unit/test_drive_client_list_exports.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_drive_client_list_exports.py
"""Tests for list_whatsapp_exports_in_folder (no time filter, sorted asc)."""

from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest

from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient


def _mk_client_with_files(files):
    client = GoogleDriveClient.__new__(GoogleDriveClient)
    client.logger = MagicMock()
    client.service = MagicMock()

    def list_files(q=None, pageSize=None, fields=None, orderBy=None):
        # Mimic the Drive SDK .execute() chain
        req = MagicMock()
        req.execute.return_value = {"files": files}
        return req

    client.service.files.return_value.list = list_files
    return client


def test_returns_all_matches_in_folder():
    files = [
        {"id": "1", "name": "WhatsApp Chat with Alice", "createdTime": "2026-01-01T12:00:00Z"},
        {"id": "2", "name": "WhatsApp Chat with Bob", "createdTime": "2026-01-01T12:05:00Z"},
        {"id": "3", "name": "unrelated.txt", "createdTime": "2026-01-01T12:10:00Z"},
    ]
    # The Drive API's `name contains` filter is applied server-side; here the
    # client only forwards the query. Return only matching files from our stub.
    matching = [f for f in files if "WhatsApp Chat with" in f["name"]]
    client = _mk_client_with_files(matching)

    result = client.list_whatsapp_exports_in_folder(folder_id="root")
    assert [f["id"] for f in result] == ["1", "2"]


def test_sorted_by_createdtime_ascending():
    files = [
        {"id": "b", "name": "WhatsApp Chat with B", "createdTime": "2026-01-01T12:05:00Z"},
        {"id": "a", "name": "WhatsApp Chat with A", "createdTime": "2026-01-01T12:00:00Z"},
        {"id": "c", "name": "WhatsApp Chat with C", "createdTime": "2026-01-01T12:10:00Z"},
    ]
    client = _mk_client_with_files(files)

    result = client.list_whatsapp_exports_in_folder(folder_id="root")
    assert [f["id"] for f in result] == ["a", "b", "c"]


def test_accepts_chat_name_filter_through_query_string():
    # Verifies the query string builder incorporates chat_name; it's tested by
    # capturing the `q` argument.
    captured = {}

    client = GoogleDriveClient.__new__(GoogleDriveClient)
    client.logger = MagicMock()
    client.service = MagicMock()

    def list_files(q=None, **kwargs):
        captured["q"] = q
        req = MagicMock()
        req.execute.return_value = {"files": []}
        return req

    client.service.files.return_value.list = list_files
    client.list_whatsapp_exports_in_folder(folder_id="root", chat_name="Alice's Chat")

    assert "WhatsApp Chat with" in captured["q"]
    assert "root" in captured["q"]
    # Single quote must be escaped for the Drive API
    assert "Alice\\'s Chat" in captured["q"]


def test_empty_result_returns_empty_list():
    client = _mk_client_with_files([])
    result = client.list_whatsapp_exports_in_folder(folder_id="root")
    assert result == []


def test_returns_empty_on_api_error():
    client = GoogleDriveClient.__new__(GoogleDriveClient)
    client.logger = MagicMock()
    client.service = MagicMock()
    client.service.files.return_value.list.side_effect = RuntimeError("boom")

    result = client.list_whatsapp_exports_in_folder(folder_id="root")
    assert result == []
```

- [ ] **Step 2: Run tests — expect failure**

Run: `poetry run pytest tests/unit/test_drive_client_list_exports.py -v --no-cov`
Expected: `AttributeError: 'GoogleDriveClient' object has no attribute 'list_whatsapp_exports_in_folder'`

- [ ] **Step 3: Implement**

In `drive_client.py`, immediately above the old `poll_for_new_export` (which will be removed in Task 6), add:

```python
    def list_whatsapp_exports_in_folder(
        self,
        folder_id: str = "root",
        chat_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all WhatsApp export files in the given folder.

        Unlike the old ``poll_for_new_export`` there is NO ``createdTime`` filter:
        any file in the folder whose name contains "WhatsApp Chat with" is
        returned, sorted oldest-first.

        Args:
            folder_id: Drive folder ID (default ``"root"`` for the top-level Drive).
            chat_name: Optional chat name to narrow the server-side query.

        Returns:
            List of file metadata dicts, sorted by ``createdTime`` ascending.
            Empty list on any API error (logged).
        """
        query = f"name contains 'WhatsApp Chat with' and '{folder_id}' in parents"
        if chat_name:
            safe_name = chat_name.replace("'", "\\'")
            query += f" and name contains '{safe_name}'"

        try:
            response = self.service.files().list(
                q=query,
                pageSize=1000,
                fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents)",
                orderBy="createdTime asc",
            ).execute()
        except Exception as e:
            self.logger.error(f"list_whatsapp_exports_in_folder failed: {e}")
            return []

        return response.get("files", [])
```

- [ ] **Step 4: Run tests — expect 5 passed**

Run: `poetry run pytest tests/unit/test_drive_client_list_exports.py -v --no-cov`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/google_drive/drive_client.py \
        tests/unit/test_drive_client_list_exports.py
git commit -m "feat(drive): add list_whatsapp_exports_in_folder (no time filter, asc sort)"
```

---

### Task 6: Remove dead polling code

**Files:**
- Modify: `whatsapp_chat_autoexport/google_drive/drive_client.py` (delete `poll_for_new_export`)
- Modify: `whatsapp_chat_autoexport/google_drive/drive_manager.py` (delete `wait_for_new_export`; add passthrough for `list_whatsapp_exports_in_folder`)
- Test:   no new tests; this task only removes code.

- [ ] **Step 1: Check that no remaining code calls the soon-removed methods**

Run:
```bash
grep -n "poll_for_new_export\|wait_for_new_export" whatsapp_chat_autoexport/
```

Expected: matches appear ONLY in `drive_client.py` and `drive_manager.py` (the definitions themselves). If any other file matches, that file must be updated in Task 7 first — STOP and return to Task 7.

- [ ] **Step 2: Delete `poll_for_new_export` from `drive_client.py`**

Remove the entire method (currently at `drive_client.py:322-432`). Keep the `list_whatsapp_exports_in_folder` method added in Task 5 intact.

- [ ] **Step 3: Delete `wait_for_new_export` from `drive_manager.py`**

Remove the entire method (currently at `drive_manager.py:59-109`).

- [ ] **Step 4: Add a passthrough `list_whatsapp_exports_in_folder` on the manager**

Add to `drive_manager.py` at the same location where `wait_for_new_export` lived:

```python
    def list_whatsapp_exports_in_folder(
        self,
        folder_id: str = "root",
        chat_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all WhatsApp exports in the given folder; no time filter.

        See :meth:`GoogleDriveClient.list_whatsapp_exports_in_folder`.
        """
        return self.client.list_whatsapp_exports_in_folder(
            folder_id=folder_id, chat_name=chat_name
        )
```

- [ ] **Step 5: Run full unit suite to catch any stragglers**

Run:
```bash
poetry run pytest tests/unit/ --no-cov --timeout=30 -q \
  --deselect tests/unit/test_connect_pane.py::test_connect_pane_mounts_connect_button \
  --deselect tests/unit/test_discover_select_pane.py::TestDiscoverSelectPaneInit::test_discovered_chats_defaults_empty \
  --deselect tests/unit/test_discover_select_pane.py::test_discover_select_pane_mounts_discovery_inventory
```

Expected: all pass. If a test fails due to removed methods, update those tests to use `list_whatsapp_exports_in_folder` (they are testing removed polling behavior).

- [ ] **Step 6: Commit**

```bash
git add whatsapp_chat_autoexport/google_drive/drive_client.py \
        whatsapp_chat_autoexport/google_drive/drive_manager.py
git commit -m "refactor(drive): remove poll_for_new_export / wait_for_new_export in favor of list_whatsapp_exports_in_folder"
```

---

### Task 7: `ParallelPipeline` — 4 workers, `submit_if_not_in_flight`, `file_metadata` passthrough

**Files:**
- Modify: `whatsapp_chat_autoexport/export/parallel_pipeline.py`
- Test:   `tests/unit/test_parallel_pipeline_submit_if_not_in_flight.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_parallel_pipeline_submit_if_not_in_flight.py
"""Tests for ParallelPipeline idempotent submission and default worker count."""

from unittest.mock import MagicMock

import pytest

from whatsapp_chat_autoexport.export.parallel_pipeline import (
    ParallelPipeline,
    PipelineTaskResult,
)


class _FakePipeline:
    def __init__(self):
        self.calls = []

    def process_single_export(self, chat_name, google_drive_folder=None, file_metadata=None):
        self.calls.append((chat_name, file_metadata))
        return {
            "success": True,
            "chat_name": chat_name,
            "output_path": None,
            "phases_completed": ["download"],
            "errors": [],
        }


def test_default_max_workers_is_4():
    pp = ParallelPipeline(pipeline=_FakePipeline(), logger=MagicMock())
    try:
        assert pp._max_workers == 4
    finally:
        pp.shutdown(wait=True)


def test_submit_if_not_in_flight_noop_when_already_queued():
    fake = _FakePipeline()
    pp = ParallelPipeline(pipeline=fake, logger=MagicMock(), max_workers=1)
    try:
        pp.submit_if_not_in_flight("Alice")
        pp.submit_if_not_in_flight("Alice")  # noop
        pp.submit_if_not_in_flight("Bob")
        pp.collect_results(timeout=5.0)
    finally:
        pp.shutdown(wait=True)

    names_called = sorted(c[0] for c in fake.calls)
    assert names_called == ["Alice", "Bob"]


def test_submit_threads_file_metadata_through():
    fake = _FakePipeline()
    pp = ParallelPipeline(pipeline=fake, logger=MagicMock(), max_workers=1)
    try:
        pp.submit("Carol", file_metadata={"id": "xyz", "name": "WhatsApp Chat with Carol"})
        pp.collect_results(timeout=5.0)
    finally:
        pp.shutdown(wait=True)

    assert len(fake.calls) == 1
    chat_name, file_metadata = fake.calls[0]
    assert chat_name == "Carol"
    assert file_metadata == {"id": "xyz", "name": "WhatsApp Chat with Carol"}


def test_submit_if_not_in_flight_requeues_after_completion():
    """Once a task has completed, another submit for the same chat is a fresh task."""
    fake = _FakePipeline()
    pp = ParallelPipeline(pipeline=fake, logger=MagicMock(), max_workers=1)
    try:
        pp.submit_if_not_in_flight("Dave")
        pp.collect_results(timeout=5.0)  # drain first
        pp.submit_if_not_in_flight("Dave")  # fresh submit
        pp.collect_results(timeout=5.0)
    finally:
        pp.shutdown(wait=True)

    names_called = [c[0] for c in fake.calls]
    assert names_called == ["Dave", "Dave"]
```

- [ ] **Step 2: Run tests — expect failures**

Run: `poetry run pytest tests/unit/test_parallel_pipeline_submit_if_not_in_flight.py -v --no-cov`
Expected: `AttributeError: 'ParallelPipeline' object has no attribute 'submit_if_not_in_flight'` and default worker assertion fails at 2 ≠ 4.

- [ ] **Step 3: Implement**

In `parallel_pipeline.py`:

Change `__init__` default:

```python
    def __init__(
        self,
        pipeline: "WhatsAppPipeline",
        logger: "Logger",
        max_workers: int = 4,  # was 2; peak concurrency 4*8 = 32 API calls
    ) -> None:
```

Change `submit` to accept `file_metadata`:

```python
    def submit(
        self,
        chat_name: str,
        google_drive_folder: Optional[str] = None,
        file_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Submit a pipeline task for *chat_name*.

        Args:
            chat_name: Chat whose export should be polled/downloaded/processed.
            google_drive_folder: Optional Drive folder override.
            file_metadata: Optional pre-fetched Drive file metadata. When
                supplied, the worker skips the targeted-discovery step and
                downloads this file directly.
        """
        with self._lock:
            if self._shutdown:
                self._logger.warning(
                    f"ParallelPipeline already shut down; ignoring submit for '{chat_name}'"
                )
                return
            future = self._executor.submit(
                self._run_task, chat_name, google_drive_folder, file_metadata
            )
            self._futures[chat_name] = future
            self._logger.debug_msg(
                f"Submitted pipeline task for '{chat_name}' "
                f"({len(self._futures)} task(s) queued)"
            )
```

Add `submit_if_not_in_flight`:

```python
    def submit_if_not_in_flight(
        self,
        chat_name: str,
        google_drive_folder: Optional[str] = None,
        file_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Idempotent submit: no-op if a task for ``chat_name`` is currently
        queued or running. Returns True if a new task was submitted, False if
        an existing task was kept.

        An already-completed task DOES get resubmitted (a previous run finished
        and we've decided to re-run this chat).
        """
        with self._lock:
            existing = self._futures.get(chat_name)
            if existing is not None and not existing.done():
                self._logger.debug_msg(
                    f"Task for '{chat_name}' already in flight; skipping resubmit"
                )
                return False
        self.submit(chat_name, google_drive_folder=google_drive_folder, file_metadata=file_metadata)
        return True
```

Change `_run_task` to accept and forward `file_metadata`:

```python
    def _run_task(
        self,
        chat_name: str,
        google_drive_folder: Optional[str],
        file_metadata: Optional[Dict[str, Any]] = None,
    ) -> PipelineTaskResult:
        """Execute the pipeline for a single chat. Captures all exceptions.

        This method runs in a worker thread.
        """
        result = PipelineTaskResult(chat_name=chat_name)
        start = time.monotonic()

        try:
            self._logger.info(
                f"[pipeline-bg] Starting background processing for '{chat_name}'"
            )
            pipeline_result = self._pipeline.process_single_export(
                chat_name=chat_name,
                google_drive_folder=google_drive_folder,
                file_metadata=file_metadata,
            )
            result.success = pipeline_result.get("success", False)
            result.output_path = pipeline_result.get("output_path")
            result.phases_completed = pipeline_result.get("phases_completed", [])
            result.errors = pipeline_result.get("errors", [])
            if result.success:
                self._logger.info(f"[pipeline-bg] Completed '{chat_name}' successfully")
            else:
                self._logger.warning(
                    f"[pipeline-bg] '{chat_name}' finished with errors: {result.errors}"
                )
        except Exception as exc:
            result.success = False
            result.errors.append(str(exc))
            self._logger.error(f"[pipeline-bg] Exception processing '{chat_name}': {exc}")
            self._logger.debug_msg(traceback.format_exc())

        result.elapsed_s = time.monotonic() - start
        result.process_time_s = result.elapsed_s
        return result
```

Add import at the top of the file if not already present:

```python
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
```

- [ ] **Step 4: Run tests — expect 4 passed**

Run: `poetry run pytest tests/unit/test_parallel_pipeline_submit_if_not_in_flight.py tests/unit/test_parallel_pipeline.py -v --no-cov`
Expected: all pass. The pre-existing `test_parallel_pipeline.py` may have a "default workers = 2" assertion — if so, update it to 4 (the new default is the whole point of the change).

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/export/parallel_pipeline.py \
        tests/unit/test_parallel_pipeline_submit_if_not_in_flight.py \
        tests/unit/test_parallel_pipeline.py
git commit -m "feat(parallel-pipeline): 4 default workers; submit_if_not_in_flight; file_metadata passthrough"
```

---

### Task 8: `process_single_export` accepts `file_metadata`; add targeted discovery

**Files:**
- Modify: `whatsapp_chat_autoexport/pipeline.py::process_single_export` and add `_targeted_discovery` private helper
- Test:   `tests/unit/test_pipeline_discovery.py` (new, first half)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_pipeline_discovery.py
"""Tests for discovery-driven pipeline entrypoints."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline


def _mk_pipeline(tmp_path):
    cfg = PipelineConfig(
        output_dir=tmp_path / "output",
        delete_from_drive=False,
    )
    return WhatsAppPipeline(config=cfg, logger=MagicMock())


def test_process_single_export_skips_targeted_discovery_when_file_metadata_given(tmp_path):
    pipeline = _mk_pipeline(tmp_path)
    pipeline.drive_manager = MagicMock()
    pipeline.drive_manager.connect.return_value = True
    pipeline.drive_manager.batch_download_exports.return_value = []  # simulate download fail quickly

    file_metadata = {
        "id": "abc",
        "name": "WhatsApp Chat with Alice",
        "createdTime": "2026-04-01T12:00:00Z",
    }

    with patch.object(pipeline, "_targeted_discovery") as mock_disc:
        pipeline.process_single_export("Alice", file_metadata=file_metadata)

    mock_disc.assert_not_called()
    # batch_download_exports should have been called with the file metadata
    assert pipeline.drive_manager.batch_download_exports.called
    args, _ = pipeline.drive_manager.batch_download_exports.call_args
    assert args[0] == [file_metadata]


def test_process_single_export_uses_targeted_discovery_when_no_metadata(tmp_path):
    pipeline = _mk_pipeline(tmp_path)
    pipeline.drive_manager = MagicMock()
    pipeline.drive_manager.connect.return_value = True
    pipeline.drive_manager.batch_download_exports.return_value = []

    file_metadata = {
        "id": "abc",
        "name": "WhatsApp Chat with Bob",
        "createdTime": "2026-04-01T12:00:00Z",
    }

    with patch.object(pipeline, "_targeted_discovery", return_value=file_metadata) as mock_disc:
        pipeline.process_single_export("Bob")

    mock_disc.assert_called_once_with("Bob")


def test_targeted_discovery_retries_until_file_found(tmp_path, monkeypatch):
    pipeline = _mk_pipeline(tmp_path)
    pipeline.drive_manager = MagicMock()
    # First two lookups empty, third returns the file
    file_metadata = {
        "id": "abc",
        "name": "WhatsApp Chat with Carol",
        "createdTime": "2026-04-01T12:00:00Z",
    }
    pipeline.drive_manager.list_whatsapp_exports_in_folder.side_effect = [
        [],
        [],
        [file_metadata],
    ]

    # Patch sleep to make the test fast
    monkeypatch.setattr(
        "whatsapp_chat_autoexport.pipeline.time.sleep", lambda s: None
    )

    result = pipeline._targeted_discovery("Carol", poll_interval=0, max_attempts=15)
    assert result == file_metadata
    assert pipeline.drive_manager.list_whatsapp_exports_in_folder.call_count == 3


def test_targeted_discovery_returns_none_after_max_attempts(tmp_path, monkeypatch):
    pipeline = _mk_pipeline(tmp_path)
    pipeline.drive_manager = MagicMock()
    pipeline.drive_manager.list_whatsapp_exports_in_folder.return_value = []

    monkeypatch.setattr(
        "whatsapp_chat_autoexport.pipeline.time.sleep", lambda s: None
    )

    result = pipeline._targeted_discovery("NeverArrives", poll_interval=0, max_attempts=5)
    assert result is None
    assert pipeline.drive_manager.list_whatsapp_exports_in_folder.call_count == 5
```

- [ ] **Step 2: Run tests — expect failures**

Run: `poetry run pytest tests/unit/test_pipeline_discovery.py -v --no-cov`
Expected: `AttributeError: 'WhatsAppPipeline' object has no attribute '_targeted_discovery'` and the `file_metadata` kwarg in the assertion is unsupported.

- [ ] **Step 3: Implement**

In `pipeline.py`, add `import time` at the top if missing. Update `process_single_export` signature and replace the old polling block. The existing method body (lines 117–261) becomes:

```python
    def process_single_export(
        self,
        chat_name: str,
        google_drive_folder: Optional[str] = None,
        file_metadata: Optional[Dict] = None,
    ) -> Dict:
        """Process a single chat export.

        When ``file_metadata`` is supplied (discovery-driven path), the worker
        downloads that file directly. Otherwise it runs a targeted discovery
        sweep (2s poll × 15 attempts = ~30s window) to find the file.
        """
        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"Processing export: '{chat_name}'")
        self.logger.info("=" * 70)

        results = {
            "success": False,
            "chat_name": chat_name,
            "output_path": None,
            "phases_completed": [],
            "errors": [],
        }
        temp_dir = None

        try:
            temp_dir = Path(tempfile.mkdtemp(prefix=f"whatsapp_{chat_name.replace(' ', '_')}_"))
            self.logger.debug_msg(f"Temp directory: {temp_dir}")

            # Phase 1: discover (if needed) and download
            self.logger.info("\n" + "-" * 70)
            self.logger.info("Phase 1: Download from Google Drive")
            self.logger.info("-" * 70)
            self._fire_progress("download", "Preparing download", 0, 1, chat_name)

            if self.drive_manager is None:
                self.drive_manager = GoogleDriveManager(logger=self.logger)
                if not self.drive_manager.connect():
                    raise RuntimeError("Failed to connect to Google Drive")

            if file_metadata is None:
                file_metadata = self._targeted_discovery(chat_name)
                if file_metadata is None:
                    raise RuntimeError(
                        f"Export for '{chat_name}' not found on Drive after 30s. "
                        "The upload may still be in progress or may have failed."
                    )

            download_dir = temp_dir / "downloads"
            download_dir.mkdir(parents=True, exist_ok=True)

            downloaded = self.drive_manager.batch_download_exports(
                [file_metadata],
                download_dir,
                delete_after=self.config.delete_from_drive,
            )
            if not downloaded:
                raise RuntimeError(f"Failed to download export for '{chat_name}'")

            self.logger.success(f"Downloaded: {file_metadata['name']}")
            self._fire_progress("download", "Download complete", 1, 1, chat_name)
            results["phases_completed"].append("download")

            # Phase 2: extract
            self.logger.info("\n" + "-" * 70)
            self.logger.info("Phase 2: Extract and Organize")
            self.logger.info("-" * 70)
            self._fire_progress("extract", "Extracting", 0, 1, chat_name)
            transcript_files = self._phase2_extract_and_organize(download_dir)
            if not transcript_files:
                raise RuntimeError(f"No transcript found after extraction for '{chat_name}'")
            self._fire_progress("extract", "Extraction complete", 1, 1, chat_name)
            results["phases_completed"].append("extract")

            # Phase 3: transcribe (with cache routing)
            if self.config.transcribe_audio_video:
                self.logger.info("\n" + "-" * 70)
                self.logger.info("Phase 3: Transcribe Audio/Video")
                self.logger.info("-" * 70)
                self._fire_progress("transcribe", "Starting transcription", 0, 1, chat_name)
                self._phase3_transcribe(transcript_files, chat_name=chat_name)
                self._fire_progress("transcribe", "Transcription complete", 1, 1, chat_name)
                results["phases_completed"].append("transcribe")

            # Phase 4: build output
            self.logger.info("\n" + "-" * 70)
            self.logger.info("Phase 4: Build Output")
            self.logger.info("-" * 70)
            self._fire_progress("build_output", "Building output", 0, 1, chat_name)
            outputs = self._phase4_build_outputs(transcript_files, chat_name=chat_name)
            if outputs:
                results["output_path"] = outputs[0]
                self._fire_progress("build_output", "Output built", 1, 1, chat_name)
                results["phases_completed"].append("build_output")

            if self.config.cleanup_temp:
                self._fire_progress("cleanup", "Cleaning up", 0, 1, chat_name)
                self._fire_progress("cleanup", "Cleanup complete", 1, 1, chat_name)
                results["phases_completed"].append("cleanup")

            results["success"] = True
            self.logger.success(f"\n✅ Successfully processed '{chat_name}'")
            if results["output_path"]:
                self.logger.info(f"   Output: {results['output_path']}")

        except Exception as e:
            self.logger.error(f"Failed to process '{chat_name}': {e}")
            results["errors"].append(str(e))
            import traceback
            traceback.print_exc()
        finally:
            if temp_dir and temp_dir.exists() and self.config.cleanup_temp:
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup temp directory: {e}")

        return results
```

Add `_targeted_discovery` below:

```python
    def _targeted_discovery(
        self,
        chat_name: str,
        poll_interval: float = 2.0,
        max_attempts: int = 15,
    ) -> Optional[Dict]:
        """Discover a specific chat's zip on Drive.

        Uses ``list_whatsapp_exports_in_folder(chat_name=...)`` — NO time
        filter. Retries up to ``max_attempts`` times with ``poll_interval``
        seconds between attempts (default ~30s total). Returns the first
        matching file metadata, or None after exhaustion.
        """
        for attempt in range(1, max_attempts + 1):
            try:
                files = self.drive_manager.list_whatsapp_exports_in_folder(
                    folder_id="root", chat_name=chat_name
                )
            except Exception as e:
                self.logger.warning(f"Drive discovery error for '{chat_name}': {e}")
                files = []
            if files:
                self.logger.info(
                    f"Discovered Drive file for '{chat_name}' on attempt {attempt}: {files[0]['name']}"
                )
                return files[0]
            if attempt < max_attempts:
                self.logger.debug_msg(
                    f"Discovery miss {attempt}/{max_attempts} for '{chat_name}'; "
                    f"sleeping {poll_interval}s"
                )
                time.sleep(poll_interval)
        return None
```

Note: `_phase3_transcribe` and `_phase4_build_outputs` gain a `chat_name` parameter here. Those changes land in Task 9 and 10 respectively; for the test here, they can remain as stubs that accept and ignore `chat_name` — but to keep the code compiling, update their signatures now too (this is a real code change; it's documented here so the plan is self-contained).

In `pipeline.py::_phase3_transcribe` and `_phase4_build_outputs`, add `chat_name: Optional[str] = None` to both signatures. They can ignore it for now; Tasks 9 and 10 wire the actual behavior.

- [ ] **Step 4: Run tests — expect pass**

Run: `poetry run pytest tests/unit/test_pipeline_discovery.py -v --no-cov`
Expected: 4 passed.

Also run the broader pipeline tests:
```bash
poetry run pytest tests/unit/test_pipeline_progress.py tests/unit/test_pipeline_only.py -v --no-cov
```
Expected: all pass (no regression from the signature changes).

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/pipeline.py tests/unit/test_pipeline_discovery.py
git commit -m "feat(pipeline): process_single_export accepts file_metadata; add _targeted_discovery"
```

---

### Task 9: `_phase3_transcribe` passes `chat_name` into `batch_transcribe`

**Files:**
- Modify: `whatsapp_chat_autoexport/pipeline.py::_phase3_transcribe`
- Test:   covered by the integration test in Task 12; no new unit test here.

- [ ] **Step 1: Locate the current `_phase3_transcribe`**

Search:
```bash
grep -n "def _phase3_transcribe" whatsapp_chat_autoexport/pipeline.py
```

- [ ] **Step 2: Modify the signature and wire `chat_name` into `batch_transcribe`**

Change the signature to `def _phase3_transcribe(self, transcript_files, chat_name: Optional[str] = None):` and inside the body, when calling `self.transcription_manager.batch_transcribe(...)`, pass `chat_name=chat_name` as a kwarg.

Exact diff inside the method (example — the body may vary slightly; preserve existing behavior):

```python
        batch_results = self.transcription_manager.batch_transcribe(
            transcribable_files,
            skip_existing=self.config.skip_existing_transcriptions,
            show_progress=True,
            transcript_path=transcript_path,
            on_progress=self.on_progress,
            chat_name=chat_name,   # NEW: routes transcriptions to the durable cache
        )
```

- [ ] **Step 3: Run pipeline tests**

Run: `poetry run pytest tests/unit/test_pipeline_progress.py tests/unit/test_pipeline_only.py -v --no-cov`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add whatsapp_chat_autoexport/pipeline.py
git commit -m "feat(pipeline): thread chat_name into batch_transcribe for cache routing"
```

---

### Task 10: `_phase4_build_outputs` reads transcriptions from the cache

**Files:**
- Modify: `whatsapp_chat_autoexport/pipeline.py::_phase4_build_outputs`
- Modify: `whatsapp_chat_autoexport/output/output_builder.py::build_output` (add `transcriptions_source_dir` parameter)
- Test:   `tests/unit/test_output_builder_cache_source.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_output_builder_cache_source.py
"""Verify that the output builder reads transcriptions from an explicit source dir."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _mk_builder():
    from whatsapp_chat_autoexport.output.output_builder import OutputBuilder
    return OutputBuilder(logger=MagicMock())


def test_copy_transcriptions_uses_explicit_source_dir(tmp_path):
    """_copy_transcriptions should look in the given source_dir, not in the media file's parent."""
    from whatsapp_chat_autoexport.output.output_builder import OutputBuilder

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media_file = media_dir / "PTT-001.opus"
    media_file.write_bytes(b"fake")

    cache_dir = tmp_path / "cache" / "transcriptions"
    cache_dir.mkdir(parents=True)
    (cache_dir / "PTT-001_transcription.txt").write_text("hello")

    dest_dir = tmp_path / "out"
    dest_dir.mkdir()

    builder = OutputBuilder(logger=MagicMock())
    copied = builder._copy_transcriptions(
        [media_file], source_dir=cache_dir, dest_dir=dest_dir
    )

    assert len(copied) == 1
    assert (dest_dir / "PTT-001_transcription.txt").read_text() == "hello"


def test_build_output_accepts_transcriptions_source_dir(tmp_path):
    """build_output exposes a transcriptions_source_dir that overrides the default media-parent lookup."""
    from whatsapp_chat_autoexport.output.output_builder import OutputBuilder

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "PTT-001.opus").write_bytes(b"fake")

    cache_dir = tmp_path / "cache" / "transcriptions"
    cache_dir.mkdir(parents=True)
    (cache_dir / "PTT-001_transcription.txt").write_text("hi")

    transcript = tmp_path / "WhatsApp Chat with Alice.txt"
    transcript.write_text("[2023-01-01, 12:00] Alice: hi\n")

    out_root = tmp_path / "exports"
    out_root.mkdir()

    builder = OutputBuilder(logger=MagicMock())
    # Call with explicit transcriptions source
    builder.build_output(
        transcript_file=transcript,
        media_dir=media_dir,
        dest_dir=out_root,
        copy_media=False,
        include_transcriptions=True,
        transcriptions_source_dir=cache_dir,
    )

    assert (out_root / "Alice" / "transcriptions" / "PTT-001_transcription.txt").exists()
```

- [ ] **Step 2: Run tests — expect failure**

Run: `poetry run pytest tests/unit/test_output_builder_cache_source.py -v --no-cov`
Expected: `TypeError: build_output() got an unexpected keyword argument 'transcriptions_source_dir'` (the first test may pass since `_copy_transcriptions` already takes `source_dir`).

- [ ] **Step 3: Implement**

In `output_builder.py::build_output`, add `transcriptions_source_dir: Optional[Path] = None` to the signature. In the body, when calling `self._copy_transcriptions(...)`, use `transcriptions_source_dir` as the `source_dir` when supplied; otherwise fall back to current behavior (`source_dir=media_dir`).

Example diff:

```python
    def build_output(
        self,
        transcript_file: Path,
        media_dir: Path,
        dest_dir: Path,
        copy_media: bool = True,
        include_transcriptions: bool = True,
        transcriptions_source_dir: Optional[Path] = None,  # NEW
    ) -> Dict:
        # ... (existing setup)
        if include_transcriptions:
            copied_transcriptions = self._copy_transcriptions(
                media_files,
                transcriptions_source_dir or media_dir,  # NEW
                transcriptions_out_dir,
            )
```

In `pipeline.py::_phase4_build_outputs`, modify the call to `output_builder.build_output` (or `batch_build_outputs` if that's what's used) to pass `transcriptions_source_dir=get_chat_cache_dir(chat_name)` when `chat_name` is set:

```python
from .transcription.transcription_cache import get_chat_cache_dir

def _phase4_build_outputs(self, transcript_files, chat_name: Optional[str] = None):
    # ... existing setup
    transcriptions_source_dir = (
        get_chat_cache_dir(chat_name) if chat_name else None
    )
    # ... when calling build_output / batch_build_outputs:
    self.output_builder.build_output(
        transcript_file=tf,
        media_dir=md,
        dest_dir=self.config.output_dir,
        copy_media=self.config.include_media,
        include_transcriptions=self.config.include_transcriptions,
        transcriptions_source_dir=transcriptions_source_dir,
    )
```

- [ ] **Step 4: Run tests — expect pass**

Run: `poetry run pytest tests/unit/test_output_builder_cache_source.py tests/unit/test_output_builder.py tests/unit/test_pipeline_progress.py -v --no-cov`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/output/output_builder.py \
        whatsapp_chat_autoexport/pipeline.py \
        tests/unit/test_output_builder_cache_source.py
git commit -m "feat(output): build_output accepts transcriptions_source_dir; pipeline wires cache"
```

---

### Task 11: `discovery_sweep_now`; `PipelineConfig` cleanup; default `max_concurrent=4`

**Files:**
- Modify: `whatsapp_chat_autoexport/pipeline.py` (add `discovery_sweep_now`, clean up `PipelineConfig`)
- Test:   `tests/unit/test_pipeline_discovery.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_pipeline_discovery.py`:

```python
def test_discovery_sweep_now_submits_all_new_files(tmp_path):
    pipeline = _mk_pipeline(tmp_path)
    pipeline.drive_manager = MagicMock()
    pipeline.drive_manager.list_whatsapp_exports_in_folder.return_value = [
        {"id": "1", "name": "WhatsApp Chat with A", "createdTime": "2026-04-01T12:00:00Z"},
        {"id": "2", "name": "WhatsApp Chat with B", "createdTime": "2026-04-01T12:05:00Z"},
    ]

    parallel = MagicMock()
    parallel.submit_if_not_in_flight = MagicMock(return_value=True)
    pipeline.parallel_pipeline = parallel

    n = pipeline.discovery_sweep_now()
    assert n == 2
    assert parallel.submit_if_not_in_flight.call_count == 2
    calls = parallel.submit_if_not_in_flight.call_args_list
    # Both calls pass file_metadata through
    assert calls[0].kwargs["file_metadata"]["id"] == "1"
    assert calls[1].kwargs["file_metadata"]["id"] == "2"


def test_discovery_sweep_now_skips_in_flight(tmp_path):
    pipeline = _mk_pipeline(tmp_path)
    pipeline.drive_manager = MagicMock()
    pipeline.drive_manager.list_whatsapp_exports_in_folder.return_value = [
        {"id": "1", "name": "WhatsApp Chat with A", "createdTime": "2026-04-01T12:00:00Z"},
        {"id": "2", "name": "WhatsApp Chat with B", "createdTime": "2026-04-01T12:05:00Z"},
    ]

    parallel = MagicMock()
    # Return False for the first call (already in flight), True for the second
    parallel.submit_if_not_in_flight = MagicMock(side_effect=[False, True])
    pipeline.parallel_pipeline = parallel

    n = pipeline.discovery_sweep_now()
    assert n == 1  # only the second file was freshly submitted


def test_pipeline_config_default_max_concurrent_is_4():
    cfg = PipelineConfig(output_dir=Path("/tmp/out"))
    assert cfg.max_concurrent == 4


def test_pipeline_config_removed_polling_fields():
    """Polling-related fields are gone from PipelineConfig."""
    cfg = PipelineConfig(output_dir=Path("/tmp/out"))
    for removed_field in [
        "initial_interval",
        "max_interval",
        "poll_timeout",
        "created_within_seconds",
        "poll_interval",
    ]:
        assert not hasattr(cfg, removed_field), f"PipelineConfig still exposes {removed_field}"
```

The last test relies on `hasattr` — make sure to delete the fields, not just default them to None.

- [ ] **Step 2: Run tests — expect failures**

Run: `poetry run pytest tests/unit/test_pipeline_discovery.py -v --no-cov`
Expected: `discovery_sweep_now` not defined; config defaults wrong; removed fields still present.

- [ ] **Step 3: Implement**

In `pipeline.py::PipelineConfig`, remove the five polling-related fields (`initial_interval`, `max_interval`, `poll_timeout`, `created_within_seconds`, `poll_interval`). Bump `max_concurrent` default from 2 to 4:

```python
@dataclass
class PipelineConfig:
    google_drive_folder: Optional[str] = None
    delete_from_drive: bool = False
    skip_download: bool = False

    # Concurrency settings
    max_concurrent: int = 4  # was 2

    # Processing settings
    download_dir: Optional[Path] = None
    keep_archives: bool = False

    # Transcription settings
    transcribe_audio_video: bool = True
    transcription_language: Optional[str] = None
    transcription_provider: str = "whisper"
    skip_existing_transcriptions: bool = True
    convert_opus_to_m4a: bool = True

    # Output settings
    output_dir: Path = Path("~/whatsapp_exports").expanduser()
    include_media: bool = True
    include_transcriptions: bool = True

    # General settings
    cleanup_temp: bool = True
    dry_run: bool = False
    limit: Optional[int] = None
    chat_names: Optional[List[str]] = None

    # Debug/testing settings
    video_test_mode: bool = False
```

Add `discovery_sweep_now` to `WhatsAppPipeline`:

```python
    def discovery_sweep_now(self) -> int:
        """Perform one full-folder discovery sweep of Drive.

        Lists all matching WhatsApp export files in the Drive root (no time
        filter), and submits any that are not already in flight to the
        parallel pipeline. Returns the count of newly-submitted tasks.

        Safe to call from any thread that has access to the pipeline instance.
        """
        if self.drive_manager is None:
            self.drive_manager = GoogleDriveManager(logger=self.logger)
            if not self.drive_manager.connect():
                self.logger.error("discovery_sweep_now: cannot connect to Drive")
                return 0

        try:
            files = self.drive_manager.list_whatsapp_exports_in_folder(folder_id="root")
        except Exception as e:
            self.logger.warning(f"discovery_sweep_now: Drive list failed: {e}")
            return 0

        if not self.parallel_pipeline:
            self.logger.warning("discovery_sweep_now: no ParallelPipeline attached")
            return 0

        submitted = 0
        for file_metadata in files:
            chat_name = _chat_name_from_drive_filename(file_metadata["name"])
            if chat_name is None:
                continue
            if self.parallel_pipeline.submit_if_not_in_flight(
                chat_name, file_metadata=file_metadata
            ):
                submitted += 1

        self.logger.info(
            f"discovery_sweep_now: discovered {len(files)} file(s); "
            f"submitted {submitted} new task(s)"
        )
        return submitted


def _chat_name_from_drive_filename(name: str) -> Optional[str]:
    """Extract chat name from a Drive filename like 'WhatsApp Chat with Alice'
    or 'WhatsApp Chat with Alice.zip'.
    """
    prefix = "WhatsApp Chat with "
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    if rest.endswith(".zip"):
        rest = rest[:-4]
    return rest.strip() or None
```

Also ensure `WhatsAppPipeline.__init__` exposes `self.parallel_pipeline = None` (if not already), so `discovery_sweep_now` doesn't `AttributeError`. The actual `ParallelPipeline` instance is attached by the chat_exporter wiring (existing code).

- [ ] **Step 4: Run tests — expect pass**

Run: `poetry run pytest tests/unit/test_pipeline_discovery.py -v --no-cov`
Expected: all pass.

Also run the full unit suite to catch any call-site regression from the removed polling fields:
```bash
poetry run pytest tests/unit/ --no-cov --timeout=30 -q \
  --deselect tests/unit/test_connect_pane.py::test_connect_pane_mounts_connect_button \
  --deselect tests/unit/test_discover_select_pane.py::TestDiscoverSelectPaneInit::test_discovered_chats_defaults_empty \
  --deselect tests/unit/test_discover_select_pane.py::test_discover_select_pane_mounts_discovery_inventory
```
Expected: all pass. Any test still referencing the removed config fields must be updated to stop doing so.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_chat_autoexport/pipeline.py tests/unit/test_pipeline_discovery.py
git commit -m "feat(pipeline): add discovery_sweep_now; drop polling config fields; max_concurrent=4"
```

---

### Task 12: Wire discovery sweeps into the export-and-pipeline orchestration

**Files:**
- Modify: `whatsapp_chat_autoexport/export/chat_exporter.py` (around the `ParallelPipeline` setup and post-export collection)

Context: The chat exporter already creates a `ParallelPipeline` and wires the pipeline/exporter together. This task adds two `discovery_sweep_now()` calls — one immediately after `ParallelPipeline` is wired, one after the export loop returns.

- [ ] **Step 1: Locate the wiring points**

Run:
```bash
grep -n "ParallelPipeline\|parallel_pipeline\|submit\|collect_results" whatsapp_chat_autoexport/export/chat_exporter.py
```

- [ ] **Step 2: Add the two sweep calls**

Immediately after `self.pipeline.parallel_pipeline = ParallelPipeline(...)` assignment (exact line depends on the current code; search for "Parallel pipeline enabled"):

```python
            self.logger.info("Discovery sweep at pipeline start...")
            try:
                self.pipeline.discovery_sweep_now()
            except Exception as e:
                self.logger.warning(f"Initial discovery sweep failed: {e}")
```

Immediately before `self.pipeline.parallel_pipeline.shutdown(...)` at the end of the export-batch orchestration, add a final sweep:

```python
            self.logger.info("Final discovery sweep before shutdown...")
            try:
                self.pipeline.discovery_sweep_now()
            except Exception as e:
                self.logger.warning(f"Final discovery sweep failed: {e}")
```

- [ ] **Step 3: Run the full unit suite to confirm no regression**

```bash
poetry run pytest tests/unit/ --no-cov --timeout=30 -q \
  --deselect tests/unit/test_connect_pane.py::test_connect_pane_mounts_connect_button \
  --deselect tests/unit/test_discover_select_pane.py::TestDiscoverSelectPaneInit::test_discovered_chats_defaults_empty \
  --deselect tests/unit/test_discover_select_pane.py::test_discover_select_pane_mounts_discovery_inventory
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add whatsapp_chat_autoexport/export/chat_exporter.py
git commit -m "feat(exporter): trigger initial and final discovery sweeps around the export loop"
```

---

### Task 13: Integration test — pipeline resume semantics

**Files:**
- Create: `tests/integration/test_pipeline_resume.py`

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_pipeline_resume.py
"""End-to-end: pipeline that crashes mid-transcribe resumes using the cache."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock
import zipfile

import pytest

from whatsapp_chat_autoexport.pipeline import PipelineConfig, WhatsAppPipeline
from whatsapp_chat_autoexport.transcription.transcription_manager import (
    TranscriptionManager,
)
from whatsapp_chat_autoexport.transcription.base_transcriber import (
    TranscriptionResult,
)


def _make_fake_zip(dst_dir: Path, chat_name: str):
    zip_path = dst_dir / f"WhatsApp Chat with {chat_name}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            f"WhatsApp Chat with {chat_name}.txt",
            f"[2023-01-01, 12:00] {chat_name}: PTT-001.opus (file attached)\n",
        )
        zf.writestr("PTT-001.opus", b"fake-opus-data")
    return zip_path


def _make_fake_drive_manager(downloaded_dir: Path, zip_path: Path):
    """Return a MagicMock drive_manager whose batch_download_exports drops the zip into place."""
    mgr = MagicMock()
    mgr.connect.return_value = True

    def fake_download(file_list, dest_dir, delete_after=False):
        for _ in file_list:
            shutil.copy2(zip_path, dest_dir / zip_path.name)
        return [zip_path]

    mgr.batch_download_exports.side_effect = fake_download
    mgr.list_whatsapp_exports_in_folder.return_value = [
        {"id": "abc", "name": zip_path.name, "createdTime": "2026-04-01T12:00:00Z"}
    ]
    return mgr


@pytest.mark.slow
def test_resume_reuses_cache(tmp_path, transcription_cache_tmp):
    """Run pipeline with failing transcriber; rerun with working transcriber.

    Assert that the second run reads the cached transcription (no new calls).
    """
    fake_zip = _make_fake_zip(tmp_path, "Alice")

    # First run: transcriber raises on every call (simulate crash)
    failing_transcriber = MagicMock()
    failing_transcriber.is_available.return_value = True
    failing_transcriber.validate_file.return_value = (True, None)
    failing_transcriber.transcribe.return_value = TranscriptionResult(
        text="", success=False, error="insufficient_quota"
    )

    cfg = PipelineConfig(
        output_dir=tmp_path / "output",
        delete_from_drive=False,
        include_media=False,
    )
    pipeline = WhatsAppPipeline(config=cfg, logger=MagicMock())
    pipeline.transcription_manager = TranscriptionManager(
        transcriber=failing_transcriber
    )
    pipeline.drive_manager = _make_fake_drive_manager(tmp_path, fake_zip)

    r1 = pipeline.process_single_export("Alice")
    assert r1["success"] is False or "transcribe" not in r1["phases_completed"]

    # Second run: transcriber returns success — but we expect the cache to
    # still be empty (first run never succeeded), so transcriber will be called.
    succeeding_transcriber = MagicMock()
    succeeding_transcriber.is_available.return_value = True
    succeeding_transcriber.validate_file.return_value = (True, None)
    succeeding_transcriber.transcribe.return_value = TranscriptionResult(
        text="hello", success=True
    )

    pipeline2 = WhatsAppPipeline(config=cfg, logger=MagicMock())
    pipeline2.transcription_manager = TranscriptionManager(
        transcriber=succeeding_transcriber
    )
    pipeline2.drive_manager = _make_fake_drive_manager(tmp_path, fake_zip)

    r2 = pipeline2.process_single_export("Alice")
    assert r2["success"] is True
    assert succeeding_transcriber.transcribe.call_count == 1

    # Third run: cache has the transcription; transcriber must NOT be called
    third_transcriber = MagicMock()
    third_transcriber.is_available.return_value = True
    third_transcriber.validate_file.return_value = (True, None)
    third_transcriber.transcribe.return_value = TranscriptionResult(
        text="should-not-be-used", success=True
    )

    pipeline3 = WhatsAppPipeline(config=cfg, logger=MagicMock())
    pipeline3.transcription_manager = TranscriptionManager(
        transcriber=third_transcriber
    )
    pipeline3.drive_manager = _make_fake_drive_manager(tmp_path, fake_zip)

    r3 = pipeline3.process_single_export("Alice")
    assert r3["success"] is True
    assert third_transcriber.transcribe.call_count == 0  # cache hit
```

- [ ] **Step 2: Run the test**

Run: `poetry run pytest tests/integration/test_pipeline_resume.py -v --no-cov -s`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_pipeline_resume.py
git commit -m "test(integration): pipeline resume reuses transcription cache"
```

---

### Task 14: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Pipeline throughput & cache" section**

Append to `README.md` (before the "License" section, or in an appropriate location):

```markdown
## Pipeline throughput & transcription cache

The post-export pipeline (download → extract → transcribe → build output) runs
in parallel with the WhatsApp-to-Drive export phase. Concurrency is
intentionally hard-coded:

| Dimension | Value | Rationale |
|---|---|---|
| Pipeline workers | 4 | Four chats in flight at once (download + extract + transcribe + build) |
| Transcription calls per worker | 8 | Whisper / ElevenLabs accept concurrent requests; 8 stays well within free-tier rate limits |
| Peak concurrent API calls | 32 | 4 × 8 |

**Transcription cache.** Transcription outputs are written to
`~/.whatsapp_exports_cache/<chat-name>/transcriptions/` before being copied
into the final output directory at the end of the pipeline. If a run is
interrupted, the next run reuses the cache — no re-transcription charges for
already-completed files.

To force re-transcription, delete the cache:

```bash
rm -rf ~/.whatsapp_exports_cache
```

The `--force-transcribe` flag also bypasses cache hits.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): document hard-coded pipeline concurrency and transcription cache"
```

---

### Task 15: Full-suite sanity check + manual verification surface

**Files:** none (verification).

- [ ] **Step 1: Run full unit suite**

```bash
poetry run pytest tests/unit/ --no-cov --timeout=30 -q \
  --deselect tests/unit/test_connect_pane.py::test_connect_pane_mounts_connect_button \
  --deselect tests/unit/test_discover_select_pane.py::TestDiscoverSelectPaneInit::test_discovered_chats_defaults_empty \
  --deselect tests/unit/test_discover_select_pane.py::test_discover_select_pane_mounts_discovery_inventory
```

Expected: all pass (~840 tests).

- [ ] **Step 2: Run integration test**

```bash
poetry run pytest tests/integration/test_pipeline_resume.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 3: Prepare manual verification plan for user**

Surface the following steps for the user to run with their phone connected:

```bash
# 1. Fresh 30-chat run, full pipeline, delete-from-drive on
poetry run whatsapp --headless \
  --output ~/whatsapp_exports \
  --auto-select \
  --limit 30 \
  --no-output-media \
  --delete-from-drive

# Watch Drive folder file count during the run: must stay flat or shrink, not monotonically grow.

# 2. Partial-then-resume test
# Kill process around chat 20 (Ctrl-C)
# Re-run the same command:
poetry run whatsapp --headless \
  --output ~/whatsapp_exports \
  --auto-select \
  --limit 30 \
  --no-output-media \
  --delete-from-drive

# Confirm: cache-hit log lines for chats 1..N; fresh transcription only for the remaining chats; Drive empty at run end.
```

- [ ] **Step 4: Leave the branch ready for merge**

No additional commits; just confirm the branch state:

```bash
git status                 # clean
git log --oneline main..HEAD   # list of commits from this plan
```

---

## Self-Review

**Spec coverage (R1–R14):**

- R1: Task 5.
- R2: Task 7 (default 2 → 4 and `file_metadata`).
- R3: Task 7 (`submit_if_not_in_flight`).
- R4: Task 4.
- R5: Task 3.
- R6: Tasks 1, 2 (cache module + writes).
- R7: Task 1 (`transcription_cache.py` + env var override).
- R8: Task 10 (`build_output` accepts `transcriptions_source_dir`).
- R9: Task 8 (`process_single_export(file_metadata=…)` and `_targeted_discovery`).
- R10: Task 11 (`discovery_sweep_now`).
- R11: unchanged behavior preserved (Task 8 keeps `delete_after=self.config.delete_from_drive` on the download call).
- R12: Task 6 (remove polling) + Task 11 (remove config fields).
- R13: Task 14 (README).
- R14: Tasks 1, 2, 3, 4, 5, 7, 8, 10, 11, 13 (unit + integration).

**Placeholder scan:** None. Every step has a concrete artifact or commit.

**Type consistency:**

- `file_metadata: Optional[Dict]` — defined in Task 7 (`ParallelPipeline.submit`), consumed in Task 8 (`process_single_export`). Consistent.
- `chat_name: Optional[str]` — threaded through `batch_transcribe` (Task 4), `_phase3_transcribe` (Task 9), `_phase4_build_outputs` (Task 10), `get_transcription_path` / `is_transcribed` / `save_transcription` (Task 2).
- `transcriptions_source_dir: Optional[Path]` — added in Task 10 to `build_output`, consumed by the same method.
- `_targeted_discovery` (Task 8) and `discovery_sweep_now` (Task 11) both call `drive_manager.list_whatsapp_exports_in_folder` (defined in Tasks 5 and 6).
- `MAX_TRANSCRIPTION_CONCURRENCY = 8` module constant introduced in Task 4; referenced by the module's own `batch_transcribe`. No other callers.

No drift detected.

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-04-17-002-fix-pipeline-throughput-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
