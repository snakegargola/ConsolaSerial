# Serial Monitor - Arquitectura del Proyecto

## Descripción General
Serial Monitor es una aplicación PyQt6 para monitoreo y comunicación con dispositivos seriales (puertos COM). Proporciona una interfaz gráfica completa con soporte para logging, alertas, secuencias de comandos y tema oscuro/claro.

## Estructura del Proyecto

```
SerialPython/
├── main.py                      # Punto de entrada de la aplicación
├── app/                         # Módulo principal de la aplicación
│   ├── __init__.py
│   ├── serial_monitor.py        # Ventana principal (PyQt6)
│   ├── serial_worker.py         # Worker thread para comunicación serial
│   ├── serial_payload.py        # Validación y vista previa ASCII/HEX
│   ├── usb_bridge.py            # Catálogo y detección por capacidades
│   ├── bridge_interface_manager.py # Arbitraje genérico por interfaz
│   ├── i2c_worker.py            # Workers FTDI/I²C sin bloquear la GUI
│   ├── i2c_bus.py               # Ajustes, PEC y clasificación de errores
│   ├── i2c_transaction_lab.py   # UI Raw I²C, SMBus y diagnóstico
│   ├── i2c_formula.py           # Fórmulas seguras, bits y enumeraciones
│   ├── i2c_device_inspector.py  # UI de registros, sensores y memorias
│   ├── i2c_register_map.py      # Modelo versionado de perfiles de registros
│   ├── i2c_register_map_widget.py # Editor/runner de mapas de registros
│   ├── ft4232_channels.py       # Compatibilidad con imports anteriores
│   ├── i2c_value_codec.py       # Conversiones puras de valores I²C
│   ├── display_image_converter.py # Imágenes monocromáticas SSD1306
│   ├── config_manager.py        # Gestión de configuración (JSON)
│   └── log_manager.py           # Gestión de logs
├── assets/                      # Recursos (iconos, imágenes)
├── scripts/                     # Scripts de compilación
│   ├── build_linux.sh
│   ├── build_windows.bat
│   └── build_windows.ps1
├── dist/                        # Ejecutables compilados
│   ├── linux/                   # Ejecutable para Linux
│   └── windows/                 # Ejecutable para Windows (generado)
├── docs/                        # Documentación del proyecto
├── config.json                  # Configuración de usuario
└── requirements.txt             # Dependencias Python
```

## Módulos Principales

### 1. **main.py**
- Punto de entrada de la aplicación
- Inicializa ConfigManager y lanza la ventana principal

### 2. **app/serial_monitor.py**
**Responsabilidades:**
- Construir interfaz gráfica (PyQt6)
- Gestionar eventos del usuario
- Coordinar worker threads
- Manejar logging y display de datos

**Componentes principales:**
- `_build_ui()` - Construye la interfaz completa
- `_build_config_panel()` - Panel de configuración serial con tooltips
- `_build_send_panel()` - Panel para envío de datos
- `_build_log_panel()` - Panel de logging
- `_build_sequence_panel()` - Panel de secuencias de comandos
- `_toggle_connection()` - Conecta/desconecta puerto serial
- `_send_data()` - Envía datos al puerto
- `_display_rx()` - Muestra datos recibidos
- `_pick_color()` - Selector de colores
- `_toggle_theme()` - Cambia tema oscuro/claro

**Características:**
- Tooltips informativos en cada control (🔹)
- Soporte para ASCII y HEX
- Validación estricta y vista previa byte por byte antes de transmitir
- Timestamps en mensajes
- Alertas por patrones regex
- Búsqueda literal y navegación de coincidencias
- Estadísticas de transferencia

### 3. **app/serial_worker.py**
**Responsabilidades:**
- Manejar comunicación serial en thread separado
- Leer/escribir datos del puerto
- Emitir señales de datos recibidos

**Funciones principales:**
- `SerialWorker` - QThread para operaciones serial
- `list_ports()` - Lista puertos seriales disponibles
- Manejo seguro de conexión/desconexión

### 4. **app/config_manager.py**
**Responsabilidades:**
- Cargar/guardar configuración en JSON
- Mantener estado de la aplicación
- Persistencia de preferencias del usuario

**Config almacenada:**
- Puerto serial y parámetros (baud, parity, etc.)
- Colores personalizados (RX, TX, BG)
- Tema (light/dark)
- Preferencias de visualización

### 5. **app/log_manager.py**
**Responsabilidades:**
- Gestionar logs de sesión
- Búsqueda literal en el monitor
- Exportación de logs

### 6. Módulos I²C

- `i2c_device_inspector.py` contiene las pestañas de registros/sensores y
  memorias. Emite solicitudes y no conoce PyFtdi.
- `i2c_value_codec.py` implementa el pipeline de shift, máscara, extensión de
  signo, escala y offset; se prueba sin hardware.
- `i2c_formula.py` limita fórmulas de datasheet y extrae campos de bits sin
  usar `eval`.
- `i2c_bus.py` centraliza frecuencia, clock stretching, reintentos, direcciones,
  PEC SMBus y categorías de error.
- `i2c_transaction_lab.py` construye solicitudes Raw/SMBus y presenta diagnóstico
  e historial sin acceder al hardware.
- `i2c_register_map.py` valida el esquema JSON y mantiene los perfiles separados
  de PyQt y PyFtdi; `i2c_register_map_widget.py` implementa su editor y runner.
- `i2c_worker.py` posee el acceso USB en threads. Ejecuta escaneos, Raw/SMBus,
  diagnóstico, registros, bancos/páginas de memoria, SSD1306 y secuencias.
- `serial_monitor.py` actúa como coordinador y mantiene una sola operación I²C
  activa por vez.

Consulta [`I2C.md`](I2C.md) para el flujo de usuario y las garantías de escritura
en memorias.

### 7. Sesiones USB Bridge concurrentes

La ventana principal crea un workspace con tantas sesiones como interfaces
declare el adaptador detectado. `usb_bridge.py` separa la identificación de
hardware de la UI y describe sus capacidades.
`UartSessionPanel` e `I2cSessionPanel` reutilizan las herramientas existentes,
pero mantienen señales, timers y workers propios. `UsbBridgeInterfaceManager` evita
asignaciones incompatibles dentro del mismo canal y permite que canales
distintos trabajen en paralelo. `ScopedConfig` separa preferencias e historial
por sesión. Consulta [`USB_BRIDGES.md`](USB_BRIDGES.md).

## Parámetros de Configuración Serial

| Parámetro | Descripción | Valores |
|-----------|------------|---------|
| **Port** | Puerto serial a conectar | COM3, /dev/ttyUSB0, etc. |
| **Baud** | Velocidad de transmisión | 300, 1200, 9600, 115200, 921600 |
| **Data** | Bits de datos por carácter | 5, 6, 7, 8 |
| **Parity** | Control de paridad | None, Even, Odd, Mark, Space |
| **Stop** | Bits de parada | 1, 1.5, 2 |
| **Flow** | Control de flujo | None, RTS/CTS, XON/XOFF |
| **EOL TX** | Terminador línea (tx) | None, LF, CR, CR+LF |
| **EOL RX** | Terminador línea (rx) | None, LF, CR, CR+LF |

## Flujo de Datos

```
Usuario Input
    ↓
PyQt6 Signals
    ↓
SerialMonitorApp (main thread)
    ↓
SerialWorker (worker thread) ←→ Puerto Serial
    ↓
PyQt6 Signals
    ↓
Display/Logging
```

## Características v2.0

### Nuevas
✅ Tooltips informativos en configuración serial (🔹)
✅ Indicadores visuales de ayuda
✅ Mejora en claridad de interfaz

### Existentes
✅ Comunicación serial bidireccional
✅ Logging completo de sesión
✅ Secuencias de comandos automatizadas
✅ Alertas por patrones regex
✅ Tema oscuro/claro personalizable
✅ Colores personalizables (RX, TX, BG)
✅ Búsqueda literal con navegación
✅ Estadísticas de transferencia
✅ Autoescroll en logs
✅ Exportación de logs

## Compilación

### Linux
```bash
bash scripts/build_linux.sh
# Resultado: dist/linux/SerialMonitor
```

### Windows
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# Resultado: dist/windows/SerialMonitor.exe
```

## Dependencias Principales

- **PyQt6** - Framework GUI
- **pyserial** - Comunicación serial
- **Pillow** - Procesamiento de imágenes

Ver `requirements.txt` para versiones exactas.

## Notas de Desarrollo

- Usar threads para operaciones serial (no bloquear GUI)
- Las señales PyQt6 son seguras entre threads
- Config.json se guarda después de cada cambio
- Los logs se almacenan en memoria (lista completa)
- Los tooltips se muestran automáticamente al hacer hover
