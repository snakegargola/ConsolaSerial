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
