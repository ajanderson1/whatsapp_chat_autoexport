"""
Real-Drive concurrency test for GoogleDriveClient.

GATED: This test requires live Google Drive credentials and a fixture folder
populated with small binary files. It is skipped by default and in CI.

Run locally with:

    export DRIVE_INTEGRATION_FIXTURE_FOLDER_ID=<drive folder id>
    poetry run pytest tests/integration/test_drive_client_concurrency.py \
        -m requires_drive -v

See tests/integration/README_drive_integration.md for setup.
"""
import hashlib
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from whatsapp_chat_autoexport.google_drive.auth import GoogleDriveAuth
from whatsapp_chat_autoexport.google_drive.drive_client import GoogleDriveClient


pytestmark = [pytest.mark.integration, pytest.mark.requires_drive]


FIXTURE_FOLDER_ENV = "DRIVE_INTEGRATION_FIXTURE_FOLDER_ID"


def _fixture_folder_id() -> str:
    folder_id = os.environ.get(FIXTURE_FOLDER_ENV)
    if not folder_id:
        pytest.skip(
            f"Set {FIXTURE_FOLDER_ENV} to a Drive folder populated with "
            f"small fixture files. See README_drive_integration.md."
        )
    return folder_id


@pytest.fixture(scope="module")
def connected_client() -> GoogleDriveClient:
    auth = GoogleDriveAuth()
    client = GoogleDriveClient(auth=auth)
    assert client.connect(), "Failed to connect to Google Drive"
    return client


def test_concurrent_downloads_do_not_corrupt_each_other(connected_client, tmp_path):
    """Fire 4-wide concurrent downloads across all fixture files, repeated
    enough times to produce clear contention. Every download must succeed
    with content matching a pre-download sequential baseline."""
    folder_id = _fixture_folder_id()
    files = connected_client.list_files(folder_id=folder_id, page_size=100)
    assert files, (
        f"Fixture folder {folder_id} is empty. Upload a handful of small files "
        f"before running this test."
    )

    # Baseline: sequential downloads to establish expected hashes.
    baseline_hashes: dict[str, str] = {}
    baseline_dir = tmp_path / "baseline"
    for f in files:
        dest = baseline_dir / f["name"]
        assert connected_client.download_file(f["id"], dest, show_progress=False), (
            f"Baseline download failed for {f['name']}"
        )
        baseline_hashes[f["id"]] = hashlib.sha256(dest.read_bytes()).hexdigest()

    # Concurrent: 4 workers, enough rounds to drive contention.
    concurrent_dir = tmp_path / "concurrent"
    concurrent_dir.mkdir()
    # At least 20 downloads across 4 threads — enough to reliably trigger the
    # pre-fix SSL cascade in < 30s of wall time on a 1 Mbps line.
    rounds = max(1, 20 // len(files) + 1)
    jobs = [(f, r) for r in range(rounds) for f in files]

    def _do_download(file_and_round):
        file_meta, round_idx = file_and_round
        dest = concurrent_dir / f"{round_idx:02d}_{file_meta['name']}"
        ok = connected_client.download_file(file_meta["id"], dest, show_progress=False)
        if not ok:
            return (file_meta["id"], dest, None, "download returned False")
        try:
            actual = hashlib.sha256(dest.read_bytes()).hexdigest()
        except Exception as e:
            return (file_meta["id"], dest, None, f"hash failed: {e}")
        return (file_meta["id"], dest, actual, None)

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_do_download, job) for job in jobs]
        for fut in as_completed(futures):
            file_id, dest, actual_hash, err = fut.result()
            if err:
                errors.append(f"{dest.name}: {err}")
                continue
            expected = baseline_hashes[file_id]
            if actual_hash != expected:
                errors.append(
                    f"{dest.name}: hash mismatch (expected {expected[:12]}, "
                    f"got {actual_hash[:12]})"
                )

    assert not errors, (
        "Concurrent downloads produced errors — thread-safety regression?\n"
        + "\n".join(errors)
    )
