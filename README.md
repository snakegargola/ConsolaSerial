# Serial Monitor (PyQt6)

Aplicación de escritorio para monitoreo y envío de datos por puerto serial, construida con **Python + PyQt6 + pyserial**.

## Características

- Conexión serial configurable: puerto, baud rate, data bits, parity, stop bits y flow control.
- Recepción y envío en tiempo real.
- Formatos de envío: `ASCII` y `HEX`.
- Soporte de fin de línea TX/RX: `None`, `LF`, `CR`, `CR+LF`.
- Modo auto-envío con intervalo configurable.
- Monitor con timestamp, vista ASCII/HEX y contadores RX/TX.
- Historial de comandos.
- Personalización de colores (RX/TX/Fondo) y tema claro/oscuro.
- Guardado de configuración en `config.json`.
- Build de ejecutables para Linux y Windows con PyInstaller.

## Requisitos

- Python 3.12+
- pip
- Dependencias del sistema para PyQt6 (en Linux, según distro)

## Instalación (desarrollo)

### Linux / macOS

```bash
python3 -m venv GuisSerial
source GuisSerial/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
py -m venv GuisSerial
.\GuisSerial\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

Si usas el entorno del proyecto en Linux:

```bash
GuisSerial/bin/python main.py
```

## Build de ejecutables

Consulta [BUILD.md](BUILD.md).

### Resumen rápido

- Linux:
  - `chmod +x scripts/build_linux.sh`
  - `./scripts/build_linux.sh`
  - Salida: `dist/linux/SerialMonitor`

- Windows (en una máquina Windows):
  - `scripts\build_windows.bat` o `./scripts/build_windows.ps1`
  - Salida: `dist/windows/SerialMonitor.exe`

> Nota: un `.exe` nativo de Windows debe compilarse en Windows.

## Estructura del proyecto

```text
Serialpython/
├── app/
│   ├── config_manager.py
│   ├── log_manager.py
│   ├── serial_monitor.py
│   └── serial_worker.py
├── assets/
├── scripts/
├── main.py
├── config.json
├── requirements.txt
├── requirements-build.txt
└── BUILD.md
```

## Configuración

La configuración de usuario se guarda en `config.json`.

- En modo desarrollo: en la raíz del proyecto.
- En ejecutable empaquetado: junto al binario (`dist/linux` o `dist/windows`).

## Troubleshooting

- **No aparecen puertos seriales**
  - Verifica permisos del sistema (Linux: grupo `dialout` o equivalente).
  - Revisa cable/driver del adaptador USB-Serial.

- **Error al iniciar GUI en Linux**
  - Instala librerías faltantes de Qt/X11 según tu distro.

- **Build Windows desde Linux no genera `.exe` válido**
  - Compila Windows directamente en Windows con los scripts del proyecto.

## Roadmap sugerido

- Exportar/importar perfiles de configuración.
- Vista de tramas por protocolo.
- Pruebas automatizadas para lógica serial y configuración.

## Contribuciones

1. Crea una rama (`feature/mi-cambio`).
2. Realiza cambios pequeños y claros.
3. Abre un Pull Request con descripción y pasos de prueba.

## Publicación en GitHub

Checklist recomendado:

- [ ] Revisar y actualizar este `README.md`.
- [x] Agregar archivo `LICENSE` (MIT).
- [ ] Confirmar que `.gitignore` excluye binarios/venv.
- [ ] Crear primer release con artefactos (`dist/linux` y `dist/windows`).

Guía paso a paso: `PUBLISH.md`

---

Proyecto listo para preparar y publicar el primer release en GitHub.
