#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$ROOT_DIR/venv/bin/python"
APP_NAME="Spotify Floating Overlay"
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
ICON_PNG="$ROOT_DIR/img/icon.png"
ICONSET_DIR="$BUILD_DIR/app.iconset"
ICON_ICNS="$BUILD_DIR/app.icns"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing venv python at $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" -m pip install pyinstaller >/dev/null

rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR"

if [[ -f "$ICON_PNG" ]]; then
  mkdir -p "$ICONSET_DIR"

  sips -z 16 16 "$ICON_PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
  sips -z 32 32 "$ICON_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "$ICON_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
  sips -z 64 64 "$ICON_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$ICON_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
  sips -z 256 256 "$ICON_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$ICON_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
  sips -z 512 512 "$ICON_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$ICON_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$ICON_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET_DIR" -o "$ICON_ICNS"
fi

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --name "$APP_NAME"
  --clean
  --osx-bundle-identifier "com.wingfungwong.spotifyfloatingoverlay"
)

if [[ -f "$ICON_ICNS" ]]; then
  PYINSTALLER_ARGS+=(--icon "$ICON_ICNS")
fi

if [[ -f "$ROOT_DIR/manual_translations.json" ]]; then
  PYINSTALLER_ARGS+=(--add-data "$ROOT_DIR/manual_translations.json:.")
fi

"$PYTHON_BIN" -m PyInstaller "${PYINSTALLER_ARGS[@]}" "$ROOT_DIR/mac.py"

echo "Built app bundle:"
echo "$DIST_DIR/$APP_NAME.app"
