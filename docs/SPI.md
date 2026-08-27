# Herramienta SPI mediante USB Bridge

La pestaña `USB Bridge` ofrece un maestro SPI independiente en cada interfaz
MPSSE compatible. Dos interfaces físicas asignadas a SPI pueden trabajar al
mismo tiempo; una misma interfaz no puede ser UART, I²C y SPI simultáneamente.
El selector de modo se encarga de reservarla y evita aperturas dobles.

## Cableado

Para la interfaz elegida, `x` representa A, B, etc.:

| Señal SPI | Pin MPSSE | Dirección |
|---|---|---|
| SCLK | `xDBUS0` | FTDI → dispositivo |
| MOSI | `xDBUS1` | FTDI → dispositivo |
| MISO | `xDBUS2` | dispositivo → FTDI |
| `/CS0` | `xDBUS3` | FTDI → dispositivo |
| `/CS1`…`/CS4` | `xDBUS4`…`xDBUS7` | FTDI → dispositivo |

Une siempre GND. Comprueba que ambos equipos usan niveles eléctricos
compatibles; la herramienta no convierte 5 V a 3.3 V. Todas las señales `/CS`
son activas en bajo. Esta primera versión transmite palabras de 8 bits en orden
MSB-first.

## Configuración

- `Clock`: presets o un valor editable de 1 kHz a 30 MHz. El resultado muestra
  la frecuencia real elegida por PyFtdi. Empieza lento si el cableado es nuevo.
- `Mode`: combina polaridad y fase. Debe coincidir exactamente con el datasheet:
  modo 0 (CPOL=0, CPHA=0), 1 (0,1), 2 (1,0) o 3 (1,1). PyFtdi marca los
  modos 1 y 3 como no oficiales y algunos modos requieren un FTDI H-series;
  la aplicación reporta `MODE` si el controlador elegido no puede generarlo.
- `/CS lines`: reserva de una a cinco salidas consecutivas. `Selected /CS`
  elige cuál controla la transacción actual.
- `Dummy byte`: valor enviado por MOSI mientras el maestro genera reloj para
  leer. Los valores usuales son `00` y `FF`; el datasheet decide cuál usar.
- `Turbo`: reduce comprobaciones internas de PyFtdi. Conviene dejarlo apagado
  durante el diagnóstico inicial.

## Tipos de transacción

- `Write`: activa `/CS`, transmite TX y libera `/CS`.
- `Read`: transmite el byte dummy tantas veces como indique `RX length` y
  conserva simultáneamente los bytes de MISO.
- `Write → Read`: transmite el comando, mantiene `/CS` activo y luego genera
  los clocks de lectura. Es apropiado para muchos registros y memorias.
- `Full duplex`: cada clock transmite un bit MOSI y recibe uno MISO. Si RX es
  mayor que TX, completa MOSI con el byte dummy.

`MOSI on wire` muestra los bytes exactos que producirán reloj, incluidos los
dummies. La respuesta se presenta en HEX y ASCII. Cada ejecución guarda hora,
modo, reloj, `/CS`, TX, RX, estado y duración; el historial puede exportarse a
CSV o JSON.

## Perfiles y secuencias de comandos

`Command sequences` permite construir pruebas reproducibles sin modificar el
código. Cada fila puede ser `Write`, `Read`, `Write → Read`, `Full duplex` o
`Delay`, y conserva TX, longitud RX, byte dummy y espera posterior. La respuesta
puede validarse por igualdad exacta, igualdad con máscara o rechazando respuestas
completamente `00`/`FF`, útil para detectar un dispositivo desconectado.

Los perfiles `.spiprofile.json` son editables, versionados e independientes de
Qt y PyFtdi. Se incluyen puntos de partida de solo lectura para identificación
SPI NOR, lectura EEPROM 25xx y comandos de inicialización de pantallas. Los
presets no incluyen programación ni borrado para evitar modificar memorias por
accidente.

La plantilla de pantalla sirve para ordenar y validar comandos, pero una pantalla
real normalmente necesita pines `D/C` y `RESET`. La aplicación todavía no ejecuta
esas señales GPIO; el perfil lo indica explícitamente en lugar de asumir un
cableado que pudiera dañar el módulo.

Una secuencia completa o solamente la fila seleccionada puede repetirse. La
ejecución se detiene en la primera validación fallida y muestra `PASS/FAIL` por
paso. Los resultados se exportan como reporte JSON o CSV. Esto permite convertir
ejemplos del datasheet en pruebas de regresión.

## Inspector de registros

`Register inspector` construye tramas para sensores, ADC, DAC y periféricos que
usan registros. El opcode o los bits de lectura/escritura se combinan con el
primer byte de dirección; también se configuran ancho de dirección, bytes dummy,
tamaño, endian, signo, escala, offset y unidad. La herramienta muestra los bytes
reales y el valor convertido, reutilizando el mismo codec probado por I²C.
Los perfiles `.spireg.json` guardan el framing y la conversión. El polling
mantiene muestras con mínimo, máximo y promedio y permite exportarlas a CSV.

`Register map` mantiene una tabla completa de registros con nombre, dirección,
acceso, endian, signo, escala, offset y unidad. Puede leer una fila o todas con
una sola apertura del controlador, hacer polling, exportar muestras CSV y guardar
el mapa como `.spimap.json`. El mapa activo se conserva por interfaz.

Las secuencias aceptan variables HEX seguras en TX: `{counter}` inserta el
contador de paso, `{random}` un byte aleatorio, `{timestamp}` cuatro bytes big
endian y `{last_rx}` la respuesta del paso anterior. También disponen de timeout
global y botón `Stop`; una espera larga se interrumpe inmediatamente y una
transferencia USB activa termina antes de detenerse.

## Memorias SPI

`Memory` soporta geometrías editables para SPI NOR, EEPROM 25xx y FRAM. Incluye:

- identificación JEDEC y encabezado SFDP;
- decodificación SFDP de capacidad y tamaño de página cuando están publicados;
- detección SFDP del ancho de dirección y tipos opcode/tamaño de borrado;
- lectura por rango con vista HEX/ASCII y archivos BIN;
- edición controlada del buffer en HEX antes de programar;
- comparación de la lectura o buffer contra otro archivo BIN;
- programación dividida sin cruzar páginas;
- `Write Enable`, polling del registro de estado y timeout;
- lectura posterior y verificación byte por byte;
- borrado de sector alineado.

`Read status` muestra BUSY, Write Enable Latch y los bits cubiertos por la máscara
de protección. Antes de programar o borrar, el worker vuelve a leer el estado y
rechaza la operación con `PROTECTED` si alguno está activo. La máscara es editable
porque la posición y significado de BP/SRP cambia entre fabricantes; `00` desactiva
esta comprobación y sólo debe usarse después de consultar el datasheet.

Programar o borrar requiere confirmación explícita. Los comandos, ancho de
dirección, capacidad, página, sector y máscara BUSY deben verificarse contra el
datasheet exacto. Una geometría incorrecta puede modificar otra región o dejar
la memoria ocupada. La identificación y lectura son el flujo inicial recomendado.
Para memorias mayores de 16 MiB debe seleccionarse el ancho y los opcodes de tres
o cuatro bytes que indique SFDP/datasheet; algunos chips usan modo 4-byte y otros
comandos dedicados como `13h`, `12h` y `21h`.

Los ajustes del inspector, memoria y repetición de secuencias se conservan por
adaptador e interfaz mediante la configuración del workspace USB Bridge.

## Pruebas rápidas

### Loopback

Desconecta primero el dispositivo bajo prueba y conecta `xDBUS1` (MOSI) con
`xDBUS2` (MISO). `Run loopback` envía el patrón completo en full-duplex y marca
`PASS` sólo si cada byte recibido coincide. No verifica un esclavo SPI: verifica
el adaptador, el reloj y la ruta de datos.

### JEDEC ID

`Read JEDEC ID` envía `9F`, mantiene `/CS` y lee tres bytes usando `FF` como
dummy. Es un atajo para memorias flash compatibles con ese comando. Una
respuesta no identifica cualquier sensor SPI y valores `00 00 00` o `FF FF FF`
suelen indicar modo, `/CS`, alimentación o cableado incorrectos.

## Errores y límites

- `MODE` indica normalmente un modo CPHA no soportado por el chip.
- `USB` cubre backend libusb, permisos, dispositivo retirado o una interfaz ya
  ocupada; la siguiente transacción vuelve a abrir el controlador limpiamente.
- `TIMEOUT` indica que la operación USB no terminó en el tiempo esperado.
- SPI no incluye direccionamiento universal ni ACK. El formato de comandos,
  registros y respuesta siempre proviene del datasheet del dispositivo.
- No se ofrecen todavía `/CS` activo-alto, LSB-first ni palabras distintas de
  8 bits, para no presentar opciones que el backend actual no garantiza.

En Linux, PyFtdi necesita permisos libusb sobre el adaptador. En Windows, la
interfaz MPSSE debe usar un driver libusb compatible; no reemplaces a ciegas el
driver VCP de todas las interfaces de un dispositivo compuesto.
