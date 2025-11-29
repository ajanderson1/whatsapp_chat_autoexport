"""
Shared pytest fixtures and configuration for WhatsApp Chat Auto-Export tests.
"""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """
    Returns the project root directory.
    """
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def sample_data_dir(project_root: Path) -> Path:
    """
    Returns the path to the sample_data directory containing test fixtures.
    """
    return project_root / "sample_data"


@pytest.fixture(scope="session")
def sample_export_dir(sample_data_dir: Path) -> Path:
    """
    Returns the path to the sample WhatsApp export directory.
    Contains: transcript file, 191 media files (116 PTT, 70 images, 1 video, etc.)
    """
    export_dir = sample_data_dir / "WhatsApp Chat with Example"
    assert export_dir.exists(), f"Sample export not found: {export_dir}"
    return export_dir


@pytest.fixture(scope="session")
def sample_transcript_file(sample_export_dir: Path) -> Path:
    """
    Returns the path to the sample WhatsApp chat transcript file.
    Contains: 3,151 lines of real WhatsApp chat messages from 2017-2025.
    """
    transcript = sample_export_dir / "WhatsApp Chat with Example.txt"
    assert transcript.exists(), f"Sample transcript not found: {transcript}"
    return transcript


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """
    Creates a temporary output directory for test outputs.
    Automatically cleaned up after the test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_working_dir() -> Generator[Path, None, None]:
    """
    Creates a temporary working directory for test operations.
    Automatically cleaned up after the test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_transcriber():
    """
    Returns a mock transcriber for testing transcription functionality
    without making actual API calls.
    """
    from whatsapp_chat_autoexport.transcription.base_transcriber import BaseTranscriber

    class MockTranscriber(BaseTranscriber):
        """Mock transcriber for testing."""

        def __init__(self):
            super().__init__()
            self.transcription_calls = []
            self.should_fail = False

        def is_available(self) -> bool:
            """Mock is always available."""
            return True

        def _transcribe_file(self, file_path: Path, language: str = "auto") -> str:
            """
            Mock transcription that returns a predictable result.
            """
            self.transcription_calls.append((file_path, language))

            if self.should_fail:
                raise Exception("Mock transcription failure")

            filename = file_path.name
            return f"Mock transcription of {filename}"

    return MockTranscriber()


@pytest.fixture
def sample_messages():
    """
    Returns sample WhatsApp message data for testing message parsing.
    """
    return [
        {
            "raw": "26/07/2017, 14:56 - AJ Anderson: Hello, this is a test message",
            "timestamp": "26/07/2017, 14:56",
            "sender": "AJ Anderson",
            "content": "Hello, this is a test message",
            "has_media": False,
        },
        {
            "raw": "26/07/2017, 15:02 - John Doe: PTT-20190919-WA0005.opus (file attached)",
            "timestamp": "26/07/2017, 15:02",
            "sender": "John Doe",
            "content": "PTT-20190919-WA0005.opus (file attached)",
            "has_media": True,
            "media_filename": "PTT-20190919-WA0005.opus",
        },
        {
            "raw": "26/07/2017, 15:10 - Jane Smith: IMG-20170811-WA0013.jpg (file attached)",
            "timestamp": "26/07/2017, 15:10",
            "sender": "Jane Smith",
            "content": "IMG-20170811-WA0013.jpg (file attached)",
            "has_media": True,
            "media_filename": "IMG-20170811-WA0013.jpg",
        },
    ]


@pytest.fixture
def sample_media_files(temp_working_dir: Path) -> Generator[dict, None, None]:
    """
    Creates sample media files for testing.
    Returns a dict mapping media types to file paths.
    """
    media_dir = temp_working_dir / "media"
    media_dir.mkdir()

    # Create dummy media files
    media_files = {
        "ptt": media_dir / "PTT-20190919-WA0001.opus",
        "image": media_dir / "IMG-20170811-WA0001.jpg",
        "video": media_dir / "VID-20230217-WA0001.mp4",
        "audio": media_dir / "AUD-20250711-WA0001.aac",
    }

    for media_type, file_path in media_files.items():
        # Create dummy files with minimal content
        file_path.write_bytes(b"dummy content")

    yield media_files


@pytest.fixture
def mock_api_key(monkeypatch):
    """
    Sets a mock API key for testing API-dependent functionality.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-key-for-testing")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "mock-elevenlabs-key")


@pytest.fixture(autouse=True)
def reset_environment():
    """
    Resets environment variables after each test.
    """
    yield
    # Cleanup happens automatically after yield
