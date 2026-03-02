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
- Timestamps en mensajes
- Alertas por patrones regex
- Búsqueda y filtrado de logs
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
- Filtrado por patrones
- Búsqueda en logs completos
- Exportación de logs

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
✅ Búsqueda y filtrado
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

