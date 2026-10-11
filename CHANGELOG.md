# Changelog

## Sin publicar

- Selectores de envío y visualización reunidos en el bloque «Send / Display».
- Vista UART ASCII, HEX o ambas, independiente del envío; los mensajes anteriores y el log exportado se reformatean conservando bytes y timestamps.
- La recompilación Linux conserva la configuración existente del usuario.
- Selector de puente USB visible solo cuando hay un puente detectado; la consola UART usa su selector Port.
- Refresco UART al conectar/desconectar dispositivos aunque la lista de puentes USB no cambie o falle libusb.
- Tema claro y oscuro uniforme, controles legibles y consola monoespaciada.
- Configuración UART y construcción de secuencias sin código duplicado.
- Búsqueda agrupada durante ráfagas de recepción, sin modificar el registro.
- Liberación de paneles al cambiar de adaptador y sondeo UART solo conectado.
- Iconos de controles incluidos en el ejecutable Linux.
- Áreas de trabajo con desplazamiento en ventanas pequeñas, sin superponer controles.

## v2.0

- Consola UART con envío ASCII/HEX, historial y búsqueda.
- Detección descriptiva de puertos seriales.
- Herramientas UART loopback, I²C, SPI y GPIO.
- Soporte para puentes FTDI con capacidades por interfaz.
- Build y distribución únicamente para Linux.
