# Serial Monitor (PyQt6) - v2.0

Aplicación de escritorio para monitoreo y envío de datos por puerto serial, construida con **Python + PyQt6 + pyserial**.

## Versión 2.0 - Novedades

✨ **Interfaz Mejorada:**
- **Tooltips informativos** (🔹) en todos los parámetros de configuración
- Explicaciones contextuales al pasar el ratón
- Mejor claridad para usuarios nuevos

📁 **Organización del Proyecto:**
- Documentación completa en carpeta `docs/`
- Ejecutable Linux listo en `dist/linux/`
- Proyecto compilable para Windows en `dist/windows-build-source/`
- Instrucciones de permisos para Linux serial

## Características Principales

### Core
- Conexión serial configurable: puerto, baud rate, data bits, parity, stop bits y flow control
- **Tooltips informativos** (NUEVO v2) - Aprende cada parámetro
- Recepción y envío en tiempo real
- Formatos de envío: `ASCII` y `HEX`
- Soporte de fin de línea TX/RX: `None`, `LF`, `CR`, `CR+LF`
- Monitor con timestamp, vista ASCII/HEX
- Historial de comandos
- Personalización de colores (RX/TX/Fondo) y tema claro/oscuro

### Secuencias de Comandos
- **Lista ordenada de comandos** con reordenamiento ( ↑↓ )
- **Formato por fila (`Fmt`)**: cada comando puede enviarse como `ASCII` o `HEX`
- **Variables dinámicas**: `{timestamp}`, `{counter}`, `{random}`
- **Modos de ejecución**: Stop o Restart al finalizar
- **Resaltado visual** del comando en ejecución
- **Exportar/Importar** secuencias en formato JSON

Nota de uso para `HEX`:
- Cuando `Fmt = HEX`, el campo `Command` debe contener bytes hexadecimales válidos.
- Ejemplos válidos: `AA 55`, `01 03 00 00 00 02 C4 0B`.
- Si escribes texto normal (por ejemplo `hola mundo`) con `Fmt = HEX`, la app mostrará advertencia de formato inválido.

### Monitoreo Avanzado
- **🔍 Búsqueda en tiempo real** con navegación y resaltado
- **📌 Filtros** (texto o regex) para ocultar mensajes no relevantes
- **📊 Estadísticas**: velocidad (B/s), RX total, TX total
- **🔔 Alertas** configurables por patrón (texto o regex)

### Productividad
- **⌨️ Atajos de teclado**: Ctrl+Enter (enviar), Ctrl+L (limpiar), Ctrl+K (conectar), Ctrl+F (buscar), etc.
- **F1-F5**: Comandos rápidos configurables
- Guardado automático de configuración en `config.json`

### Build y Distribución
- ✅ Ejecutables compilados para Linux: `dist/linux/SerialMonitor`
- 🔧 Proyecto listo para compilar en Windows: `dist/windows-build-source/`
- 📚 Documentación completa

📖 **[Ver documentación completa de funcionalidades →](FEATURES.md)**

## Distribución

### 📦 Descarga directa (GitHub Releases)

En cada release se publican ejecutables de un solo archivo:

- **Windows:** `SerialMonitor-windows.exe`
- **Ubuntu/Linux:** `SerialMonitor-linux`

Descarga desde **Releases** y ejecútalo directamente (sin instalar Python ni dependencias).

Notas:
- En Linux, dar permisos si hace falta: `chmod +x SerialMonitor-linux`
- `config.json` es opcional; si no existe, la app usa valores por defecto

### ✅ Linux - Ejecutable Listo

```bash
./dist/linux/SerialMonitor
```

Ver instrucciones en: [`dist/linux/LEEME.md`](dist/linux/LEEME.md)

### 🔧 Windows - Compilación 

Instrucciones completas en: [`dist/windows-build-source/README_COMPILACION.md`](dist/windows-build-source/README_COMPILACION.md)
## Instalación y Ejecución

### Modo Desarrollo

**Linux / macOS:**
```bash
python3 -m venv GuisSerial
source GuisSerial/bin/activate
pip install -r requirements.txt
./GuisSerial/bin/python main.py
```

**Windows (PowerShell):**
```powershell
py -m venv GuisSerial
.\GuisSerial\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Modo Ejecutable

**Linux:**
```bash
./dist/linux/SerialMonitor
```
Ver: [`dist/linux/LEEME.md`](dist/linux/LEEME.md)

**Windows:**
Compilar con instrucciones en: [`dist/windows-build-source/README_COMPILACION.md`](dist/windows-build-source/README_COMPILACION.md)

## Documentación

### Para Usuarios
- **[`dist/linux/LEEME.md`](dist/linux/LEEME.md)** - Instrucciones Linux, permisos seriales

### Para Desarrolladores
- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** - Arquitectura y módulos
- **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** - Guía de desarrollo
- **[`FEATURES.md`](FEATURES.md)** - Características detalladas
- **[`BUILD.md`](BUILD.md)** - Instrucciones de compilación

## Estructura del Proyecto

```
Serialpython/
├── main.py                          # Punto de entrada
├── app/                             # Código fuente
│   ├── serial_monitor.py            # Ventana principal (PyQt6)
│   ├── serial_worker.py             # Worker thread serial
│   ├── config_manager.py            # Gestión de config
│   └── log_manager.py               # Gestión de logs
├── dist/
│   ├── linux/                       # ✅ Ejecutable Linux listo
│   │   ├── SerialMonitor            # Ejecutable
│   │   ├── LEEME.md                 # Instrucciones
│   │   ├── config.json
│   │   └── serial.png
│   ├── windows/                     # 📝 Instrucciones para compilar
│   │   └── BUILD_INSTRUCCIONES.md
│   └── windows-build-source/        # 🔧 Proyecto para compilar en Windows
│       ├── app/                     # Código fuente
│       ├── main.py
│       ├── requirements.txt
│       └── README_COMPILACION.md
├── docs/                            # 📚 Documentación técnica
│   ├── ARCHITECTURE.md
│   └── DEVELOPMENT.md
├── assets/
├── scripts/
├── config.json                      # Configuración
├── requirements.txt                 # Dependencias
└── README.md                        # Este archivo
```

## Características v2.0

## Características v2.0

✨ **Interfaz Mejorada:**
- Tooltips informativos (🔹) en todos los parámetros
- Explicaciones claras para usuarios nuevos
- Mejor organización visual

📚 **Documentación Completa:**
- Documentación técnica en `docs/`
- Instrucciones Linux en `dist/linux/LEEME.md`
- Guía Windows en `dist/windows-build-source/`

⚙️ **Build Listo:**
- Ejecutable Linux funcional en `dist/linux/`
- Proyecto Windows listo para compilar

## Troubleshooting

### Linux - Permisos de Puerto Serial

```bash
# Agregar usuario a grupo dialout
sudo usermod -a -G dialout $USER
newgrp dialout
```

Ver instrucciones completas: [`dist/linux/LEEME.md`](dist/linux/LEEME.md)

### No aparecen puertos seriales

- Verificar permisos (Linux)
- Revisar cable/driver USB-Serial
- Comprobar en gestor de dispositivos

### Error al iniciar

- Verificar que Python 3.12+ esté instalado
- Reinstalar dependencias: `pip install -r requirements.txt --upgrade`

### No envía en HEX desde secuencias

- Verifica que en la columna `Fmt` esté seleccionado `HEX` en esa fila.
- Escribe bytes hex válidos separados por espacios (ejemplo: `AA 55 0D 0A`).
- Si necesitas enviar texto, usa `Fmt = ASCII`.

## Próximos Pasos

1. ✅ Compilación y ejecución funcional
2. ✅ Documentación completa
3. ✅ Interfaz mejorada con tooltips
4. 📊 Estadísticas y monitoreo avanzado
5. 🧪 Suite de pruebas automatizadas

## Contribuciones

1. Crea rama feature: `git checkout -b feature/mejora`
2. Haz cambios claros y prueba
3. Commit descriptivo: `git commit -m "feat: descripción"`
4. Push y Pull Request

## Roadmap

- [ ] Exportar/importar perfiles de configuración
- [ ] Protocolo Modbus
- [ ] Interfaz web de monitoreo
- [ ] Aplicación móvil

## Publicación

Checklist para release:

- [x] README.md actualizado
- [x] Documentación técnica
- [x] Ejecutable Linux funcional
- [x] Proyecto Windows compilable
- [x] Instrucciones de instalación
- [ ] Release en GitHub
- [ ] Artefactos en GitHub

Guía: [`PUBLISH.md`](PUBLISH.md)

---

**Serial Monitor v2.0** - Listo para usar y distribuir 🚀
