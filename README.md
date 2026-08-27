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
- Build reproducible para Windows con preparación y autoprueba automática
- Instrucciones de permisos para Linux serial

## Características Principales

### Core
- Conexión serial configurable: puerto, baud rate, data bits, parity, stop bits y flow control
- Consola `USB Serial / General` para CH340, CP210x, PL2303, CDC/ACM, puertos
  COM y adaptadores seriales no administrados por el workspace de protocolos
- `USB Serial / General` y `USB Bridge` se alternan automáticamente: General se
  oculta mientras un puente compatible está administrado y vuelve al retirarlo
- Monitoreo USB en segundo plano para sustituir adaptadores sin congelar la UI
- Detección por capacidades de FT232R, FT-X, FT232H, FT2232 y FT4232H/HA/HP
- Escáner I²C mediante MPSSE, selección automática de interfaces compatibles,
  reloj editable, reintentos y clock stretching opcional
- Laboratorio Raw I²C/SMBus con repeated START, PEC, diagnóstico/recuperación
  del bus e historial exportable
- Workspace `USB Bridge` con sesiones independientes según las interfaces reales
  del adaptador conectado
- Maestro SPI por interfaz MPSSE con modos 0–3, reloj editable, hasta cinco
  señales `/CS`, escritura, lectura, Write→Read, full-duplex e historial
- Pruebas rápidas SPI de loopback MOSI→MISO e identificación JEDEC `0x9F`
  con perfiles JSON y secuencias editables para memorias, pantallas y comandos
  de dispositivos.
- Inspector SPI de registros y visor/programador para NOR, EEPROM 25xx y FRAM,
  con SFDP, paginación, polling BUSY, confirmación y verificación posterior.
- Polling de registros con estadísticas/CSV, perfiles versionados, comparación
  BIN y reportes reproducibles de secuencias SPI.
- Diagnóstico de protección, edición HEX segura y selección de geometría/opcodes
  desde datos JEDEC/SFDP para memorias SPI.
- Mapas de múltiples registros SPI con polling/CSV y secuencias cancelables con
  timeout y variables dinámicas seguras.
- Inspector I²C de registros/sensores con HEX, decimal, octal, binario, signo,
  máscara, escala, offset, fórmula segura, campos de bits y lectura periódica
- Mapas de registros guardables en JSON, lectura individual/total, polling y
  exportación de muestras a CSV
- Visor de memorias I²C con matriz HEX/ASCII, archivos BIN, bancos EEPROM,
  comparación, escritura por páginas y verificación posterior
- **Tooltips informativos** (NUEVO v2) - Aprende cada parámetro
- Recepción y envío en tiempo real
- Formatos de envío: `ASCII` y `HEX`
- Vista previa en HEX de los bytes exactos que se enviarán, incluyendo EOL TX
- Entrada HEX protegida: solo acepta dígitos `0-9`, `A-F` y espacios, y bloquea
  el envío cuando falta completar un byte
- Control manual de `RTS`, `DTR` y `BREAK`, con indicadores en vivo de
  `CTS`, `DSR`, `DCD` y `RI`
- Prueba UART TX→RX loopback con tramas binarias, timeout, conteo de errores y
  validación independiente de la configuración EOL
- Soporte de fin de línea TX/RX: `None`, `LF`, `CR`, `CR+LF`
- Monitor con timestamp, vista ASCII/HEX
- Historial de comandos
- Personalización de colores (RX/TX/Fondo) y tema claro/oscuro

Consulta [`docs/UART.md`](docs/UART.md) para el cableado de loopback, seguridad
eléctrica y significado de las señales de control.
Consulta [`docs/SPI.md`](docs/SPI.md) para el cableado MPSSE, significado de los
modos, tipos de transacción y pruebas rápidas SPI.

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
- En el panel `Send`, `Will send (HEX)` muestra también los bytes agregados por
  `EOL TX`; por ejemplo `AA 55` con `LF` se transmite como `AA 55 0A`.

### Monitoreo Avanzado
- **🔍 Búsqueda literal en tiempo real** con navegación y resaltado
- **📊 Estadísticas**: velocidad (B/s), RX total, TX total
- **🔔 Alertas** configurables por patrón (texto o regex)

### Productividad
- **⌨️ Atajos de teclado**: Ctrl+Enter (enviar), Ctrl+L (limpiar), Ctrl+K (conectar), Ctrl+F (buscar), etc.
- **F1-F5**: Comandos rápidos configurables
- Guardado automático de configuración en `config.json`

### Build y Distribución
- ✅ Ejecutables compilados para Linux: `dist/linux/SerialMonitor`
- 🔧 Script único para preparar, probar y compilar en Windows
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

Instrucciones completas en: [`docs/WINDOWS.md`](docs/WINDOWS.md)
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
Compilar con instrucciones en: [`docs/WINDOWS.md`](docs/WINDOWS.md)

## Documentación

### Para Usuarios
- **[`dist/linux/LEEME.md`](dist/linux/LEEME.md)** - Instrucciones Linux, permisos seriales

### Para Desarrolladores
- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** - Arquitectura y módulos
- **[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)** - Guía de desarrollo
- **[`docs/I2C.md`](docs/I2C.md)** - Uso y arquitectura de Scanner, Inspector,
  memorias, pantallas y secuencias I²C
- **[`docs/SPI.md`](docs/SPI.md)** - Transacciones, loopback, JEDEC, cableado y
  límites de la herramienta SPI
- **[`docs/USB_BRIDGES.md`](docs/USB_BRIDGES.md)** - Modelos detectados,
  capacidades, concurrencia y persistencia por interfaz
- **[`docs/WINDOWS.md`](docs/WINDOWS.md)** - Ejecución, driver FTDI/libusb,
  autoprueba y compilación reproducible en Windows
- **[`FEATURES.md`](FEATURES.md)** - Características detalladas
- **[`BUILD.md`](BUILD.md)** - Instrucciones de compilación

## Estructura del Proyecto

```
Serialpython/
├── main.py                          # Punto de entrada
├── app/                             # Código fuente
│   ├── serial_monitor.py            # Ventana principal (PyQt6)
│   ├── serial_worker.py             # Worker thread serial
│   ├── spi_bus.py                   # Validación/transacciones SPI
│   ├── spi_worker.py                # Worker PyFtdi SPI
│   ├── spi_session_panel.py         # Laboratorio SPI por interfaz
│   ├── config_manager.py            # Gestión de config
│   └── log_manager.py               # Gestión de logs
├── dist/
│   ├── linux/                       # ✅ Ejecutable Linux listo
│   │   ├── SerialMonitor            # Ejecutable
│   │   ├── LEEME.md                 # Instrucciones
│   │   ├── config.json
│   │   └── serial.png
│   └── windows/                     # Paquete generado en Windows
│       ├── SerialMonitor.exe
│       ├── config.json
│       └── LEEME-WINDOWS.md
├── docs/                            # 📚 Documentación técnica
│   ├── ARCHITECTURE.md
│   ├── SPI.md
│   ├── WINDOWS.md
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
- Guía Windows en `docs/WINDOWS.md`

⚙️ **Build Listo:**
- Ejecutable Linux funcional en `dist/linux/`
- Proyecto Windows listo para compilar

## Troubleshooting

### Adaptadores FTDI MPSSE e I²C en Ubuntu

La pestaña `USB Bridge` usa PyFtdi y escanea las direcciones I²C de 7 bits
`0x03` a `0x77`. Conecta `xDBUS0` a SCL y une `xDBUS1` con `xDBUS2` para
SDA; ambas líneas requieren resistencias pull-up.

`Transaction Lab` permite probar I²C crudo y funciones SMBus con historial.
`Device Inspector` trabaja con direcciones de dispositivo I²C de 7 bits. Su
pestaña `Register / Sensor` lee y escribe registros de 8 o 16 bits, decodifica
los bytes como decimal, HEX, octal, binario, ASCII y valor escalado, y puede
hacer polling. `Memory Viewer` lee matrices HEX/ASCII y realiza escrituras por
página con confirmación y verificación. La guía completa está en
[`docs/I2C.md`](docs/I2C.md).

`Display Test` ofrece diagnóstico rápido para pantallas SSD1306 de 128×64 y
128×32. Permite inicializar, limpiar, encender/apagar, invertir y enviar patrones
de píxeles, borde, cuadrícula y barras. La dirección `0x3C` se selecciona
automáticamente cuando aparece en el escaneo. No se debe usar este preset con
un controlador de pantalla diferente.

`Sequence Builder` permite construir y probar la inicialización de una pantalla
desconocida directamente desde su datasheet. Cada paso puede ser `Command`
(usa el prefijo de comando), `Data` (usa el prefijo de datos), `Raw` (envía los
bytes sin prefijo) o `Delay` (milisegundos). Los pasos pueden agregarse,
eliminarse, reordenarse, ejecutarse individualmente o como una secuencia
completa. SSD1306 se incluye como preset editable y la secuencia probada puede
exportarse como JSON o arreglos C.

Los perfiles de pantalla se administran como pestañas: pueden crearse,
duplicarse, renombrarse, cerrarse y guardarse como archivos
`.i2cdisplay.json`. El perfil `SSD1306 Example` conserva la configuración
funcional de ejemplo; los perfiles nuevos comienzan como `Custom / Unknown`.

Para SSD1306, `Display Test` también genera texto con tamaño de fuente
configurable o convierte imágenes PNG/JPG/BMP a un framebuffer monocromático.
La vista previa permite ajustar el umbral e invertir píxeles antes de enviarlos.
Estas funciones gráficas se deshabilitan conceptualmente para controladores
desconocidos porque cada familia organiza su memoria de forma diferente.
El perfil `SSD1306 Example` abre con una imagen de demostración y ofrece los
botones `Example text` y `Example image`; ambos generan un framebuffer listo
para previsualizar y enviar sin necesitar archivos externos.
La conversión de imágenes muestra el resultado binario exacto y activa por
defecto `Auto dark background`: si la mayoría de la imagen es clara, interpreta
el fondo blanco como píxeles apagados para evitar una pantalla completamente
encendida. La detección automática puede desactivarse y combinarse con
`Invert pixels` para casos especiales.
El modo `Floyd-Steinberg (best detail)` usa Pillow para aplicar escala de
grises, detección de fondo, recorte de contenido, autocontraste, enfoque,
redimensionado Lanczos y conversión Floyd–Steinberg a 1 bit. `Threshold
(sharp)` produce contornos sólidos. `Stretch to 128×64` muestra la imagen
completa usando toda la pantalla, aunque cambia su proporción; `Fit whole
image` conserva la proporción con espacios laterales; `Fill / crop` conserva
la proporción y llena la pantalla recortando parte de la imagen. El texto se
renderiza con fuente monoespaciada sin antialias.
La orientación puede configurarse como horizontal `128×64`, vertical en sentido
horario o vertical en sentido antihorario. Los modos verticales renderizan un
lienzo lógico de `64×128` y lo rotan al framebuffer físico `128×64`, por lo que
están pensados para una pantalla montada físicamente en vertical.

Si aparece `Access denied`, agrega una regla udev para el VID/PID FTDI
`0403:6011` y vuelve a conectar el dispositivo:

```text
SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6011", GROUP="plugdev", MODE="0664"
```

El canal A corresponde a la interfaz 1, B a la 2, etc. La aplicación detecta
los adaptadores compatibles y construye internamente la dirección USB; el
usuario no necesita conocer ni escribir una URL de PyFtdi.

En Windows, PyFtdi necesita un backend libusb. Para dispositivos FTDI de
varios canales se debe instalar el controlador libusb en el dispositivo
compuesto padre; esto reemplaza el controlador VCP de FTDI para ese dispositivo.

### Linux - Permisos de Puerto Serial

En Ubuntu los puertos `/dev/ttyUSB*` normalmente pertenecen al grupo
`dialout`. Cada usuario que vaya a utilizar UART debe ejecutar una sola vez:

```bash
sudo usermod -a -G dialout $USER
```

Después debe cerrar completamente su sesión de Ubuntu y volver a entrar. Se
puede verificar con `groups`: la lista debe incluir `dialout`. La aplicación
marca los puertos sin acceso con `no permission` y muestra estas instrucciones
antes de intentar conectarse.

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
