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
  --collect-all libusb_package \
  --icon "$ROOT_DIR/assets/serial.png" \
  "$ROOT_DIR/main.py"

SELF_TEST_REPORT="$ROOT_DIR/dist/linux-self-test.json"
if ! "$ROOT_DIR/dist/SerialMonitor" --self-test "$SELF_TEST_REPORT"; then
  if [[ -f "$SELF_TEST_REPORT" ]]; then
    cat "$SELF_TEST_REPORT"
  fi
  echo "El ejecutable Linux no pasó la autoprueba de dependencias."
  exit 1
fi

mkdir -p "$ROOT_DIR/dist/linux"
cp -f "$ROOT_DIR/dist/SerialMonitor" "$ROOT_DIR/dist/linux/SerialMonitor"
chmod +x "$ROOT_DIR/dist/linux/SerialMonitor"
cp -f "$ROOT_DIR/config.example.json" "$ROOT_DIR/dist/linux/config.json"
cp -f "$ROOT_DIR/assets/serial.png" "$ROOT_DIR/dist/linux/serial.png"
cp -f "$ROOT_DIR/docs/LINUX.md" "$ROOT_DIR/dist/linux/LEEME.md"
cp -f "$SELF_TEST_REPORT" "$ROOT_DIR/dist/linux/runtime-self-test.json"

echo "Build Linux listo en: $ROOT_DIR/dist/linux"
