#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$ROOT_DIR/GuisSerial/bin/python"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "No se encontró Python del entorno virtual en: $PYTHON_BIN"
  echo "Define PYTHON_BIN o activa tu entorno virtual antes de compilar."
  exit 1
fi

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name SerialMonitor \
  --icon "$ROOT_DIR/assets/serial.png" \
  "$ROOT_DIR/main.py"

mkdir -p "$ROOT_DIR/dist/linux"
cp -f "$ROOT_DIR/dist/SerialMonitor" "$ROOT_DIR/dist/linux/SerialMonitor"
chmod +x "$ROOT_DIR/dist/linux/SerialMonitor"
cp -f "$ROOT_DIR/config.json" "$ROOT_DIR/dist/linux/config.json"
cp -f "$ROOT_DIR/assets/serial.png" "$ROOT_DIR/dist/linux/serial.png"

echo "Build Linux listo en: $ROOT_DIR/dist/linux"
