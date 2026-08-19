# Instalación y uso en Windows

## Ejecutar el paquete publicado

El paquete ZIP contiene:

- `SerialMonitor.exe`: aplicación autónoma, sin instalar Python;
- `config.json`: configuración inicial editable;
- `runtime-self-test.json`: resultado de la autoprueba ejecutada al compilar;
- `LEEME-WINDOWS.md`: esta guía.

Para UART general basta con conectar el adaptador, conservar su driver VCP y
abrir `SerialMonitor.exe`. CH340, CP210x, PL2303, CDC/ACM y los COM FTDI se
muestran como puertos seriales normales.

## Requisito adicional para I²C y SPI por FTDI

El ejecutable ya incluye PyFtdi, PyUSB y la DLL de libusb. Windows también
necesita un driver libusb en el dispositivo FTDI; una DLL dentro del programa
no puede sustituir ese driver del sistema.

La guía oficial de PyFtdi recomienda:

1. Descarga y abre Zadig.
2. Activa `Options > List All Devices`.
3. Para un FT2232/FT4232 compuesto, desactiva
   `Options > Ignore Hubs or Composite Parents`.
4. Selecciona el dispositivo padre, cuyo nombre **no** termina en
   `(Interface N)`. Verifica VID `0403` y el PID antes de cambiar nada.
5. Selecciona `libusb-win32` —la recomendación oficial de PyFtdi, no `WinUSB`—
   y pulsa `Replace Driver`.
6. Desconecta y vuelve a conectar el adaptador; después usa `Refresh adapters`.

No cambies el driver de otro dispositivo por accidente. Crea antes un punto de
restauración si el equipo se usa para producción.

### Importante para FT4232 y los puertos COM

El driver libusb permite que PyFtdi controle MPSSE para I²C/SPI. Dependiendo de
la versión de Windows y del driver FTDI, cambiar el dispositivo compuesto puede
hacer que sus puertos VCP dejen de aparecer como COM. Por ello, la combinación
simultánea de MPSSE y UART VCP en el mismo FT4232 depende del driver instalado y
no puede garantizarse únicamente desde la aplicación.

Si necesitas recuperar los COM, restaura `FTDI CDM / USB Serial Converter`
desde el Administrador de dispositivos o reinstala el controlador oficial
FTDI. Con VCP restaurado volverá UART; para I²C/SPI será necesario restablecer
el driver libusb. No reemplaces drivers repetidamente con una transacción
abierta.

## Autoprueba del ejecutable

La compilación ya ejecuta esta prueba y cancela el paquete si falta una DLL.
También puede repetirse desde PowerShell o CMD:

```powershell
SerialMonitor.exe --self-test mi-reporte.json
Get-Content .\mi-reporte.json
```

`"ok": true` confirma que PyQt6, PySerial, Pillow, PyFtdi y PyUSB cargaron, y
que la biblioteca nativa incluida expone `libusb_init`. No confirma el driver
Zadig ni el cableado porque la prueba deliberadamente no inicializa ni abre
ningún dispositivo USB.

## Compilar desde cero en Windows

Instala Python 3.12 o posterior de 64 bits. Desde la raíz del repositorio abre
PowerShell y ejecuta una sola orden:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_windows.ps1
```

El script crea `.venv`, instala dependencias, ejecuta todas las pruebas, genera
el `.exe`, comprueba su backend libusb y deja el paquete en `dist\windows`.
Desde CMD puede usarse `scripts\prepare_windows.bat`.

## Diagnóstico rápido

- `No supported adapter detected`: pulsa `Refresh adapters`; si UART sí aparece
  como COM, falta el driver libusb necesario para MPSSE.
- `No backend available`: usa una compilación que haya pasado la autoprueba y
  confirma que no se separó el `.exe` de los archivos del paquete.
- `Access denied` o dispositivo ocupado: cierra terminales, herramientas FTDI,
  IDEs y cualquier otra instancia de Serial Monitor.
- El adaptador aparece pero no responde: verifica GND, nivel lógico, interfaz,
  modo SPI, reloj, `/CS` o resistencias pull-up I²C.

## Referencias

- [Instalación oficial de PyFtdi](https://eblot.github.io/pyftdi/installation.html)
- [Solución oficial de errores PyFtdi/libusb](https://eblot.github.io/pyftdi/troubleshooting.html)
- [Paquete portable libusb-package](https://pypi.org/project/libusb-package/)
