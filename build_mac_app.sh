#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
APP_NAME="Spotify Floating Overlay"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing venv python at $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" -m pip install pyinstaller >/dev/null

rm -rf "$BUILD_DIR" "$DIST_DIR"

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --name "$APP_NAME"
  --clean
  --osx-bundle-identifier "com.wingfungwong.spotifyfloatingoverlay"
)

if [[ -f "$ROOT_DIR/manual_translations.json" ]]; then
  PYINSTALLER_ARGS+=(--add-data "$ROOT_DIR/manual_translations.json:.")
fi

"$PYTHON_BIN" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$ROOT_DIR/mac.py"

echo "Built app bundle:"
echo "$DIST_DIR/$APP_NAME.app"
