#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== Agentic-Hemisphere-Kubernetes Setup ==="

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required but not found."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED="3.11"
if [ "$(printf '%s\n' "$REQUIRED" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED" ]; then
    echo "ERROR: Python >= $REQUIRED required, found $PYTHON_VERSION"
    exit 1
fi

echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -e ".[dev]"

echo ""
echo "=== Setup complete ==="
echo "Activate the environment with: source .venv/bin/activate"
echo "Run tests with: make test"
echo "See all commands: make help"
