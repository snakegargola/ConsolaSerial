# Serial Monitor

Aplicación Linux de escritorio para monitoreo y comunicación serial, construida
con Python, PyQt6, pyserial y PyFtdi.

## Características

- Consola UART para `/dev/ttyUSB*`, `/dev/ttyACM*` y otros puertos seriales.
- Configuración de baud rate, bits, paridad, stop bits y control de flujo.
- Envío ASCII/HEX, vista previa, historial, timestamps y búsqueda.
- Loopback UART y control de RTS, DTR y BREAK.
- Soporte de puentes FTDI para UART, I²C, SPI y GPIO.
- Inspectores, secuencias, memorias y exportación de resultados.

Consulta la documentación específica en `docs/`.

## Ejecutar en Linux

```bash
python3 -m venv GuisSerial
source GuisSerial/bin/activate
pip install -r requirements.txt
python main.py
```

Para acceso a puertos seriales, agrega el usuario al grupo `dialout` y vuelve a
iniciar sesión:

```bash
sudo usermod -a -G dialout $USER
```

## Compilar

```bash
pip install -r requirements-build.txt
bash scripts/build_linux.sh
```

El ejecutable queda en `dist/linux/SerialMonitor`.

## Pruebas

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -v -s tests
```

## Documentación

- `docs/LINUX.md`: instalación, permisos y solución de problemas.
- `docs/UART.md`: conexión y loopback UART.
- `docs/I2C.md`: herramientas I²C.
- `docs/SPI.md`: herramientas SPI.
- `docs/USB_BRIDGES.md`: puentes FTDI compatibles.
- `docs/ARCHITECTURE.md`: arquitectura del proyecto.
- `BUILD.md`: build Linux.
