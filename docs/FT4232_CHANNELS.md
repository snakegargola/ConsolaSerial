# FT4232H dentro del workspace USB Bridge

La pestaña `USB Bridge` representa cada interfaz USB del FT4232H como una
sesión independiente. Cambiar de pestaña no detiene las demás: un UART puede
seguir recibiendo mientras otro transmite y ambos buses I²C ejecutan operaciones
en paralelo.

## Capacidades actuales

| Canal | Modos disponibles ahora | Interfaz FTDI |
|---|---|---:|
| A | UART o I²C | 1 |
| B | UART o I²C | 2 |
| C | UART | 3 |
| D | UART | 4 |

Las combinaciones principales son:

- A UART + B UART: cuatro consolas UART simultáneas.
- A I²C + B UART: un bus I²C y tres UART.
- A UART + B I²C: tres UART y un bus I²C.
- A I²C + B I²C: dos cajas I²C completas y dos UART.

Los canales A/B están preparados en el administrador de recursos para añadir
SPI, JTAG y GPIO posteriormente. Esos modos aún no aparecen en la interfaz.

## Uso

1. Selecciona el adaptador FT4232H detectado.
2. Selecciona `UART` o `I2C` para las interfaces A y B.
3. Abre `USB Bridge` y entra a `Interface A`, `B`, `C` o `D`.
4. Cada UART tiene puerto, baud rate, monitor, secuencias, historial, colores,
   estadísticas y conexión propios.
5. Cada I²C posee Scanner, Device Inspector, Display Test y Sequence Builder
   completos, con su propio worker y bloqueo interno.

No se permite cambiar el modo de A/B mientras su sesión está conectada o tiene
una operación activa. Primero hay que desconectar UART o esperar/detener I²C.

`USB Serial / General` permite trabajar con adaptadores y puertos seriales que
no pertenecen al FT4232H: CH340, CP210x, PL2303, CDC/ACM, puertos COM y otros.
Las cuatro interfaces del FT4232 detectado se excluyen de esa lista y aparecen
en `USB Bridge`, evitando abrir accidentalmente el mismo puerto dos veces. Para
que la selección sea inequívoca, al detectar un puente compatible se oculta la
pestaña General; vuelve a mostrarse cuando ya no hay un puente detectado.

## Persistencia

La configuración se guarda por adaptador e interfaz en `usb_bridge_sessions` dentro de
`config.json`. Baud rate, EOL, historial, secuencias y preferencias de A no
sobrescriben las de B/C/D. Los dos buses I²C también conservan dispositivo y
frecuencia por separado.

## Arquitectura

- `UsbBridgeInterfaceManager` mantiene modo y propietario por interfaz.
- `UartSessionPanel` reutiliza la consola serial completa con un `SerialWorker`
  exclusivo.
- `I2cSessionPanel` reutiliza la caja I²C completa con un worker exclusivo.
- `ScopedConfig` presenta una sección de configuración independiente a cada
  sesión sin duplicar `ConfigManager`.

La exclusión ocurre por canal, no por aplicación. Scanner y Display Test no
pueden competir dentro de A, pero una operación de A no bloquea B, C ni D.

## Sistemas operativos

En Ubuntu, cada UART necesita permisos sobre su `/dev/ttyUSB*`; la regla USB de
PyFtdi sigue siendo necesaria para los canales MPSSE. En Windows, la combinación
UART/MPSSE depende de que el controlador seleccionado para cada interfaz
conserve VCP en los canales UART y permita acceso libusb en los canales usados
por PyFtdi. Esta combinación debe validarse durante el empaquetado de Windows.
