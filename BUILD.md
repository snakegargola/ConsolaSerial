# Build de ejecutables (Linux y Windows)

## Requisitos

- Python 3.12+
- Dependencias del proyecto instaladas
- Dependencias de build:

```bash
pip install -r requirements-build.txt
```

## Linux (desde Linux)

```bash
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
```

Salida final:
- `dist/linux/SerialMonitor`
- `dist/linux/config.json`
- `dist/linux/serial.png`

## Windows (desde Windows)

En PowerShell:

```powershell
.\scripts\build_windows.ps1
```

En CMD:

```bat
scripts\build_windows.bat
```

Salida final:
- `dist/windows/SerialMonitor.exe`
- `dist/windows/config.json`
- `dist/windows/serial.ico`

## Nota importante de cross-build

Un `.exe` nativo de Windows debe compilarse en Windows. Desde Linux se genera el binario Linux; para Windows usa el script en una máquina Windows.
