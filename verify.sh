#!/usr/bin/env bash
# Local verification entry point. Mirrors the pre-commit cascade plus pytest.
# Per ~/.conventions/conventions/ci.md § verify.sh contract:
#   - exit 0 = pass
#   - artifacts written to $ARTIFACTS_DIR (set by the harness; defaults below)

set -euo pipefail

: "${ARTIFACTS_DIR:=assets/verification/local}"
mkdir -p "$ARTIFACTS_DIR"

echo "→ ruff format --check"
uv run ruff format --check . | tee "$ARTIFACTS_DIR/01-format.log"

echo "→ ruff check"
uv run ruff check . | tee "$ARTIFACTS_DIR/02-lint.log"

echo "→ mypy src/whatsapp_chat_autoexport"
uv run mypy src/whatsapp_chat_autoexport | tee "$ARTIFACTS_DIR/03-typecheck.log"

if command -v gitleaks > /dev/null; then
    echo "→ gitleaks detect"
    gitleaks detect --no-banner --redact | tee "$ARTIFACTS_DIR/04-secret-scan.log"
else
    echo "→ gitleaks not installed — skipping (install via 'brew install gitleaks')"
fi

echo "→ pytest (no API / device / drive tests)"
uv run pytest -m "not requires_api and not requires_device and not requires_drive" \
    | tee "$ARTIFACTS_DIR/05-pytest.log"

echo
echo "✓ verify.sh passed. Artifacts in $ARTIFACTS_DIR/"
