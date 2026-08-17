# Adaptadores USB por capacidades

La pestaña `USB Bridge` no supone que el equipo conectado sea un FT4232. Al
actualizar la lista, identifica el producto y crea una pestaña por cada interfaz
real. Cada selector muestra únicamente los modos que ese chip soporta y que la
aplicación ya implementa.

## Matriz reconocida

| Familia | Interfaces | MPSSE I²C/SPI/JTAG | UART | GPIO detectado |
|---|---:|---|---|---|
| FT232R | 1 | No | A | A |
| FT-X (FT230X/231X/234X) | 1 | No | A | A |
| FT232H | 1 | A | A | A |
| FT2232C/D | 2 | SPI/JTAG en A y B; I²C no se anuncia | A y B | A y B |
| FT2232H | 2 | I²C/SPI/JTAG en A y B | A y B | A y B |
| FT4232H/HA/HP | 4 | A y B | A, B, C y D | A, B, C y D |

Actualmente existen paneles funcionales para `UART` e `I2C`. La detección ya
registra también `SPI`, `JTAG` y `GPIO`; aparecerán como modos seleccionables
cuando se añadan sus herramientas, sin cambiar la detección ni el administrador
de interfaces.

Un PID desconocido no recibe capacidades por aproximación: permanece en
`USB Serial / General`. Esto evita ofrecer I²C o JTAG a hardware que quizá no
tenga MPSSE.

FT2232C/D y FT2232H comparten PID. La detección consulta `bcdDevice` para
distinguirlos; si no puede leerlo, aplica las capacidades conservadoras C/D y
no anuncia I²C.

## Uso

1. Conecta el adaptador. La lista se actualiza automáticamente; `Refresh
   adapters` permite solicitar una comprobación inmediata.
2. Revisa la línea `Detected`, que enumera capacidades por interfaz.
3. Elige `UART` o `I2C` en cada interfaz habilitada.
4. Trabaja en las pestañas `Interface A`, `B`, etc. Las interfaces distintas
   conservan workers y configuración independientes.

No se permite cambiar de modo mientras la interfaz esté en uso. Los puertos VCP
de adaptadores reconocidos se retiran de `USB Serial / General` para impedir una
doble apertura accidental. Cuando se detecta al menos un puente compatible, la
aplicación muestra solamente `USB Bridge`; si no hay ninguno, muestra solamente
`USB Serial / General` para CH340, CP210x, PL2303, CDC/ACM y otros UART. El botón
`Refresh adapters` vuelve a evaluar esta selección.

La detección se ejecuta en segundo plano cada tres segundos para que una consulta
USB lenta no congele la ventana. La caché de enumeración de PyFtdi se invalida en
cada consulta, por lo que al sustituir un FT232R por un FT4232H se eliminan las
sesiones anteriores y se crean las cuatro interfaces del nuevo adaptador. Una
falla transitoria de libusb se informa sin destruir sesiones que sigan activas.

## Persistencia y extensibilidad

`usb_bridge_modes` guarda el modo por adaptador físico y
`usb_bridge_sessions` conserva los ajustes por adaptador, interfaz y protocolo.
Las claves antiguas `ft4232_*` se leen como migración para no perder una
configuración existente.

El catálogo está en `app/usb_bridge.py`; la UI consume descriptores genéricos.
Así se puede añadir después otro fabricante implementando un backend de
enumeración que produzca los mismos descriptores, sin convertir la interfaz en
publicidad de una marca.

## Controladores

En Linux, PyFtdi necesita acceso al dispositivo USB y UART necesita permiso para
`/dev/ttyUSB*`. En Windows, VCP y libusb deben asignarse con cuidado por
interfaz; instalar libusb sobre todo el dispositivo compuesto puede desactivar
los puertos COM. Consulta las instrucciones de instalación antes de cambiar un
driver.
