#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${1:-}" == "--clean" ]]; then
  rm -rf build dist
fi

SEP=":"

uv run python -m PyInstaller --noconfirm --clean --windowed --name slideshow-app --paths code --add-data "src${SEP}src" code/app.py
uv run python -m PyInstaller --noconfirm --clean --windowed --name subtitle-editor --paths code code/subtitle_editor.py

echo "Build finished. Outputs are in dist/slideshow-app.app and dist/subtitle-editor.app"
