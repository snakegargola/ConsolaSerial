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

Preparación completa recomendada en PowerShell (crea `.venv`, instala, prueba,
compila y valida el `.exe`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_windows.ps1
```

O desde CMD:

```bat
scripts\prepare_windows.bat
```

Si el entorno ya está preparado, se puede ejecutar solamente el build en
PowerShell:

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
- `dist/windows/LEEME-WINDOWS.md`
- `dist/windows/runtime-self-test.json`

El build ejecuta `SerialMonitor.exe --self-test` y falla si PyQt, PyFtdi,
PyUSB o la DLL libusb no quedaron dentro del paquete. El uso físico de I²C/SPI
requiere además configurar el driver del FTDI como explica
[`docs/WINDOWS.md`](docs/WINDOWS.md).

## Nota importante de cross-build

Un `.exe` nativo de Windows debe compilarse en Windows. Desde Linux se genera el binario Linux; para Windows usa el script en una máquina Windows.

Cada push a `main` también ejecuta pruebas y builds nativos Linux/Windows en
GitHub Actions. Los artefactos se descargan desde la ejecución
`Build and Release Binaries`; los tags `v*` siguen creando la publicación.
