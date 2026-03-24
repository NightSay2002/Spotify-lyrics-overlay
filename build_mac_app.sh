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
API_SOURCE_DIR="$ROOT_DIR/api-enhanced"
API_STAGING_DIR="$BUILD_DIR/api-enhanced"
API_ARCHIVE="$BUILD_DIR/api-enhanced.tar.gz"
NODE_BIN="$(command -v node || true)"
NODE_RUNTIME="$BUILD_DIR/node-runtime"
SPEC_FILE="$BUILD_DIR/$APP_NAME.spec"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing venv python at $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" -m pip install pyinstaller >/dev/null

rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR"

if [[ -d "$API_SOURCE_DIR" ]]; then
  rsync -a \
    --exclude '.git' \
    --exclude '.github' \
    --exclude 'test' \
    --exclude '.husky' \
    --exclude '.DS_Store' \
    --exclude '._*' \
    "$API_SOURCE_DIR/" "$API_STAGING_DIR/"
  find "$API_STAGING_DIR" -name '._*' -delete
  COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1 tar -czf "$API_ARCHIVE" -C "$BUILD_DIR" api-enhanced
fi

if [[ -n "$NODE_BIN" && -x "$NODE_BIN" ]]; then
  cp "$NODE_BIN" "$NODE_RUNTIME"
  chmod 755 "$NODE_RUNTIME"
fi

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

ROOT_DIR="$ROOT_DIR" BUILD_DIR="$BUILD_DIR" SPEC_FILE="$SPEC_FILE" ICON_ICNS="$ICON_ICNS" APP_NAME="$APP_NAME" \
API_ARCHIVE="$API_ARCHIVE" NODE_RUNTIME="$NODE_RUNTIME" "$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

root_dir = Path(os.environ["ROOT_DIR"])
build_dir = Path(os.environ["BUILD_DIR"])
spec_file = Path(os.environ["SPEC_FILE"])
icon_icns = Path(os.environ["ICON_ICNS"])
app_name = os.environ["APP_NAME"]
api_archive = Path(os.environ["API_ARCHIVE"])
node_runtime = Path(os.environ["NODE_RUNTIME"])

datas = []
manual_translations = root_dir / "manual_translations.json"
if manual_translations.is_file():
    datas.append((str(manual_translations), "."))
if api_archive.is_file():
    datas.append((str(api_archive), "."))
if node_runtime.is_file():
    datas.append((str(node_runtime), "."))

spec_text = f"""# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['{root_dir / "mac.py"}'],
    pathex=[],
    binaries=[],
    datas={datas!r},
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{app_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['{icon_icns}'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{app_name}',
)
app = BUNDLE(
    coll,
    name='{app_name}.app',
    icon='{icon_icns}',
    bundle_identifier='com.wingfungwong.spotifyfloatingoverlay',
)
"""
spec_file.write_text(spec_text, encoding="utf-8")
PY

"$PYTHON_BIN" -m PyInstaller "$SPEC_FILE"

echo "Built app bundle:"
echo "$DIST_DIR/$APP_NAME.app"
