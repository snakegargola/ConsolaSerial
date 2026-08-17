# Herramientas UART

La consola `USB Serial / General` y cada interfaz UART dentro de `USB Bridge`
incluyen el mismo panel de control físico y diagnóstico. Cada sesión conserva
sus propios valores y puede trabajar al mismo tiempo que las demás.

## Señales de control

- `RTS` y `DTR` controlan sus salidas lógicas. En dispositivos con señales
  activas en bajo, "asserted" corresponde al nivel eléctrico bajo indicado por
  nombres como `RTS#` o `DTR#`.
- `RTS` queda deshabilitado cuando se selecciona `RTS/CTS`, porque en ese modo
  el controlador serial administra la señal automáticamente.
- `Send BREAK` mantiene TX en condición BREAK durante 250 ms mediante un timer;
  no duerme ni bloquea la interfaz gráfica.
- `CTS`, `DSR`, `DCD` y `RI` se consultan dos veces por segundo. `●` significa
  asserted, `○` deasserted y `?` indica que el puerto no está conectado o que el
  driver no ofrece ese estado.

Algunas tarjetas usan `DTR` para reiniciar su microcontrolador. Revisa el
esquema antes de cambiarlo. La configuración inicial conserva el comportamiento
habitual de pyserial: `RTS` y `DTR` asserted. Los estados elegidos se configuran
antes de abrir el puerto para reducir pulsos de reset innecesarios.

## Prueba TX→RX loopback

1. Con el puerto desconectado, une `TX` con `RX` en la misma interfaz UART.
2. Conecta el puerto desde la aplicación.
3. Elige cantidad de tramas, bytes de payload y timeout por trama.
4. Pulsa `Run TX→RX loopback`.

La prueba manda una trama binaria distinta por secuencia, con magic, longitud y
CRC-32. Solo envía una trama a la vez y espera su eco exacto antes de continuar.
La recepción se toma antes de aplicar `EOL RX`, por lo que funciona aunque la
trama contenga bytes `LF`, `CR` o datos no imprimibles.

El resultado informa:

- tramas correctas y tramas con timeout;
- bytes TX y RX;
- bytes inesperados recibidos antes o entre ecos;
- duración total.

`PASS` exige todas las tramas exactas y cero bytes inesperados. La prueba se
detiene de forma segura al desconectar el adaptador. Auto-send y Command
Sequence deben estar detenidos para no mezclar tráfico con el diagnóstico.

## Seguridad eléctrica y limitaciones

El FTDI trabaja con UART de nivel lógico según la alimentación/configuración de
la tarjeta. No conectes directamente señales RS-232 de voltaje positivo/negativo
a un pin TTL/CMOS; utiliza un transceptor adecuado. Si el loopback atraviesa un
circuito externo, comparte GND y verifica primero el nivel de voltaje.

El panel valida el camino físico TX/RX y el driver del sistema, pero no sustituye
una prueba del protocolo del dispositivo. Los contadores de framing, parity y
overrun no se exponen de forma uniforme por pyserial en Windows y Linux, por lo
que no se inventan métricas que el controlador no pueda entregar.

## Implementación

- `serial_worker.py` posee el puerto y ofrece operaciones thread-safe para
  RTS/DTR/BREAK y entradas de módem.
- `uart_loopback.py` genera y verifica tramas sin depender de Qt ni hardware.
- `uart_tools_widget.py` contiene el panel, timers y la máquina de prueba.
- `serial_monitor.py` conecta el panel con la consola General y las sesiones del
  workspace USB Bridge.
