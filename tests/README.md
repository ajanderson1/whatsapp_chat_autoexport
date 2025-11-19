# Testing Guide

This directory contains the test suite for the WhatsApp Chat Auto-Export project using **pytest**.

## Directory Structure

```
tests/
├── conftest.py                    # Shared fixtures and pytest configuration
├── unit/                          # Unit tests (fast, isolated)
│   ├── test_transcription.py      # Transcription service tests
│   ├── test_transcript_parser.py  # Message parsing tests
│   ├── test_output_builder.py     # Output building tests
│   └── test_archive_extractor.py  # Archive extraction tests
├── integration/                   # Integration tests (slower, subprocess-based)
│   └── test_cli.py                # CLI command tests
└── fixtures/                      # Test data directory
```

## Quick Start

```bash
# Install dependencies (including test dependencies)
poetry install --with dev

# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=html
```

## Running Tests

### Basic Commands

```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run with very verbose output (shows test docstrings)
poetry run pytest -vv

# Show print statements
poetry run pytest -s

# Stop at first failure
poetry run pytest -x
```

### Running Specific Tests

```bash
# Run specific directory
poetry run pytest tests/unit/
poetry run pytest tests/integration/

# Run specific file
poetry run pytest tests/unit/test_transcription.py

# Run specific test function
poetry run pytest tests/unit/test_transcription.py::test_mock_transcription

# Run tests matching pattern
poetry run pytest -k "transcription"
poetry run pytest -k "parser or builder"
```

### Using Markers

```bash
# Run only unit tests
poetry run pytest -m unit

# Run only integration tests
poetry run pytest -m integration

# Skip slow tests
poetry run pytest -m "not slow"

# Run tests that don't require API keys
poetry run pytest -m "not requires_api"

# Run tests that don't require device
poetry run pytest -m "not requires_device"
```

## Test Markers

Available markers (defined in `pyproject.toml`):

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests (may use subprocess)
- `@pytest.mark.slow` - Slow-running tests (batch operations, large data)
- `@pytest.mark.requires_api` - Tests requiring API keys (OpenAI, ElevenLabs)
- `@pytest.mark.requires_device` - Tests requiring Android device

## Fixtures

Common fixtures available in all tests (defined in `conftest.py`):

### Directory Fixtures
- `project_root` - Project root directory path
- `sample_data_dir` - Sample data directory path
- `sample_export_dir` - Real WhatsApp export directory (3,151 messages, 191 media)
- `temp_output_dir` - Temporary output directory (auto-cleaned)
- `temp_working_dir` - Temporary working directory (auto-cleaned)

### File Fixtures
- `sample_transcript_file` - Path to sample transcript (3,151 lines)

### Mock Fixtures
- `mock_transcriber` - Mock transcriber (no API calls)
- `mock_api_key` - Sets mock API keys for testing

### Data Fixtures
- `sample_messages` - Sample message data
- `sample_media_files` - Sample media files in temp directory

## Coverage

### Viewing Coverage

```bash
# Terminal coverage report
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=term-missing

# HTML coverage report
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=html
open htmlcov/index.html  # macOS

# Both terminal and HTML
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=term-missing --cov-report=html
```

### Coverage Configuration

- **Target**: 90% code coverage
- **Configuration**: `pyproject.toml` → `[tool.pytest.ini_options]`
- **Excluded**: Test files, `__pycache__`, site-packages

### Improving Coverage

```bash
# See which lines are missing coverage
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=term-missing

# Focus on specific module
poetry run pytest --cov=whatsapp_chat_autoexport.transcription tests/unit/test_transcription.py
```

## Writing Tests

### Test Structure

```python
import pytest
from whatsapp_chat_autoexport.module import SomeClass


@pytest.mark.unit
def test_descriptive_name(fixture_name):
    """
    Clear docstring describing what this test verifies.
    """
    # Arrange
    obj = SomeClass()

    # Act
    result = obj.method()

    # Assert
    assert result == expected, "Descriptive error message"
```

### Using Fixtures

```python
@pytest.mark.unit
def test_with_sample_data(sample_transcript_file, temp_output_dir):
    """Test using sample transcript and temporary output."""
    parser = TranscriptParser()

    # Use fixtures
    messages = parser.parse(sample_transcript_file)
    output_path = temp_output_dir / "output.txt"

    assert len(messages) > 0
    assert temp_output_dir.exists()
```

### Testing Exceptions

```python
@pytest.mark.unit
def test_invalid_input_raises_error():
    """Test that invalid input raises ValueError."""
    with pytest.raises(ValueError, match="invalid input"):
        function_that_should_fail(bad_input)
```

### Parameterized Tests

```python
@pytest.mark.unit
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
])
def test_uppercase(input, expected):
    """Test uppercase conversion with multiple inputs."""
    assert input.upper() == expected
```

## Test Categories

### Unit Tests (`tests/unit/`)

**Characteristics:**
- Fast (< 1 second per test)
- Isolated (no external dependencies)
- Mocked external services
- No file I/O (uses temp directories)

**Examples:**
- Transcription logic (with mock transcriber)
- Message parsing
- Output building structure
- Archive validation

### Integration Tests (`tests/integration/`)

**Characteristics:**
- Slower (may take several seconds)
- Tests actual CLI commands
- Uses subprocess
- End-to-end workflows

**Examples:**
- CLI argument parsing
- Full pipeline execution
- Command-line interface behavior

## Continuous Integration

The test suite is designed for CI/CD integration:

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install Poetry
        run: pip install poetry

      - name: Install dependencies
        run: poetry install --with dev

      - name: Run tests
        run: poetry run pytest --cov --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

## Troubleshooting

### Common Issues

**"No module named 'whatsapp_chat_autoexport'"**
```bash
# Ensure package is installed in editable mode
poetry install
```

**"Sample data not found"**
```bash
# Verify sample data exists
ls -la sample_data/

# Check fixture paths
poetry run pytest -vv tests/unit/test_transcript_parser.py
```

**"Coverage too low"**
```bash
# Identify uncovered lines
poetry run pytest --cov=whatsapp_chat_autoexport --cov-report=term-missing

# Focus on specific module to add tests
poetry run pytest --cov=whatsapp_chat_autoexport.processing tests/unit/test_archive_extractor.py
```

**"ImportError: cannot import name 'X'"**
```bash
# Reinstall dependencies
poetry install --with dev

# Clear pytest cache
rm -rf .pytest_cache
```

**"Tests hang or timeout"**
```bash
# Run with timeout warnings
poetry run pytest --timeout=300

# Skip slow tests
poetry run pytest -m "not slow"
```

## Best Practices

1. **Write descriptive test names**
   - ✅ `test_transcription_skips_existing_files`
   - ❌ `test_transcription_1`

2. **Use fixtures over setup/teardown**
   - Fixtures are more flexible and composable
   - Defined in `conftest.py` for reusability

3. **One assertion per test (when possible)**
   - Makes failures easier to debug
   - Use parametrize for multiple inputs

4. **Use appropriate markers**
   - Helps organize and filter tests
   - Makes CI/CD more efficient

5. **Test edge cases**
   - Empty inputs
   - Very large inputs
   - Invalid inputs
   - Boundary conditions

6. **Mock external dependencies**
   - No actual API calls in unit tests
   - Use `mock_transcriber` fixture
   - Mock file operations when appropriate

7. **Clean up after tests**
   - Use temp directories (auto-cleaned)
   - Don't leave artifacts in the filesystem

## Test Data

The `sample_data/` directory contains realistic test data:

```
sample_data/WhatsApp Chat with Example/
├── WhatsApp Chat with Example.txt          # 3,151 line transcript
├── PTT-*.opus (116 files)                  # Voice messages
├── IMG-*.jpg (70 files)                    # Images
├── VID-*.mp4 (1 file)                      # Video
├── AUD-*.aac (1 file)                      # Audio
├── PTT-*_transcription.txt (1 file)        # Sample transcription
└── *.doc (1 file)                          # Document
```

This data ensures tests run against realistic scenarios.

## Additional Resources

- **Main Documentation**: See `CLAUDE.md` for complete testing strategy
- **pytest Documentation**: https://docs.pytest.org/
- **Coverage Documentation**: https://coverage.readthedocs.io/
- **Project README**: See `README.md` for project overview

## Contributing Tests

When contributing new features:

1. Write tests alongside code
2. Ensure tests are isolated and reproducible
3. Add appropriate markers
4. Update fixtures if needed
5. Maintain >90% coverage
6. Run full test suite before PR: `poetry run pytest --cov`

---

**Questions?** Check `CLAUDE.md` or open an issue on GitHub.
