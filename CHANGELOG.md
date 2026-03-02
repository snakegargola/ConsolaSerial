# Historial de Cambios

## v2.0 (Actual) - Serial Monitor v2 Release

### ✨ Nuevas Características

#### Interfaz Mejorada
- **Tooltips informativos** en todos los parámetros de configuración (🔹)
- Indicadores visuales para campos con ayuda disponible
- Explicaciones claras al pasar el ratón:
  - **Port**: "Serial port to connect to (e.g., COM3, /dev/ttyUSB0)"
  - **Baud**: "Transmission speed in bits per second (higher = faster)"
  - **Data**: "Number of data bits per character (usually 8)"
  - **Parity**: "Error checking method: None, Even, Odd, Mark, or Space"
  - **Stop**: "Number of stop bits (1, 1.5, or 2)"
  - **Flow**: "Flow control method for handshaking"
  - **EOL TX/RX**: "Line ending configuration"
  - **Show**: "Display format options (ASCII, HEX, Timestamp)"
  - **Colors**: "Customize RX, TX, and background colors"

### 📚 Documentación

#### Nueva Documentación Técnica
- `docs/ARCHITECTURE.md` - Arquitectura completa del proyecto
- `docs/DEVELOPMENT.md` - Guía de desarrollo y contribuciones
- `dist/linux/LEEME.md` - Instrucciones Linux y permisos seriales
- `dist/windows-build-source/README_COMPILACION.md` - Compilación Windows

#### README Actualizado
- Información sobre v2.0
- Secciones para distribución Linux y Windows
- Enlaces a documentación técnica
- Troubleshooting mejorado

### 📁 Distribución Organizad

#### Linux (`dist/linux/`)
- ✅ Ejecutable compilado: `SerialMonitor` (57 MB)
- 📝 Instrucciones: `LEEME.md`
- ⚙️ Config por defecto: `config.json`
- 🎨 Icono: `serial.png`

#### Windows (`dist/windows-build-source/`)
- 📖 Guía completa de compilación: `README_COMPILACION.md`
- 📂 Código fuente:
  - `app/` - Módulos de aplicación
  - `main.py` - Punto de entrada
  - `requirements.txt` - Dependencias
  - `config.json` - Configuración por defecto

### 🧹 Limpieza del Proyecto

- Removido carpeta `build/` (artifacts de PyInstaller)
- Removido `dist/SerialMonitor` (ejecutable no se copia, solo genera via script)
- Eliminados tous los `__pycache__/` recursivamente
- Organización clara de carpetas de distribución

### 🔍 Cambios de Código

#### `app/serial_monitor.py`
- Agregados diccionarios de tooltips en `_build_config_panel()`
- Labels mejorados con indicadores visuales (🔹)
- `.setToolTip()` en todos los controles
- Mejor documentación de parámetros con ejemplos

### ✅ Checklist v2.0 Completado

- [x] Interfaz mejorada con tooltips
- [x] Indicadores visuales de ayuda
- [x] Documentación técnica completa
- [x] Instrucciones para Linux
- [x] Proyecto compilable para Windows
- [x] Limpieza de proyecto
- [x] README.md actualizado
- [x] Código documentado

## v1.0 (Anterior)

### Características Base
- Conexión serial configurable
- Recepción/envío en tiempo real
- Secuencias de comandos
- Búsqueda y filtrado
- Tema oscuro/claro
- Colores personalizables
- Estadísticas de transferencia
- Alertas por patrones
- Atajos de teclado
- Build para Linux y Windows

---

## Notas de Versión

### Para Desarrolladores

Ver `docs/DEVELOPMENT.md` para:
- Setup del entorno
- Agregar nuevas funcionalidades
- Standards de código
- Testing

### Para Usuarios Linux

Ver `dist/linux/LEEME.md` para:
- Cómo ejecutar el programa
- Solucionar permisos de puerto serial
- Identificar puertos disponibles
- Troubleshooting

### Para Compilación Windows

Ver `dist/windows-build-source/README_COMPILACION.md` para:
- Requisitos previos
- Paso a paso de compilación
- Crear scripts de build automático
- Distribución del ejecutable

