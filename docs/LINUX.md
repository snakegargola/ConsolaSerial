# Serial Monitor en Linux

## Ejecución rápida

Extrae el paquete, abre una terminal dentro de su carpeta y ejecuta:

```bash
chmod +x SerialMonitor
./SerialMonitor
```

No es necesario instalar Python. `config.json` contiene la configuración
inicial y puede conservarse junto al ejecutable.

## Acceso al FTDI y puertos seriales

Agrega tu usuario al grupo que controla los puertos seriales y vuelve a iniciar
sesión:

```bash
sudo usermod -aG dialout "$USER"
```

Para I2C, SPI y GPIO mediante PyFtdi también pueden requerirse reglas `udev`
para autorizar el dispositivo USB. Si el FTDI aparece pero no se puede abrir,
revisa los permisos del dispositivo y que ningún driver o programa lo esté
utilizando.

## Bibliotecas del sistema

En Ubuntu/Debian, si la aplicación informa que falta una biblioteca gráfica o
USB, instala las dependencias de ejecución:

```bash
sudo apt-get install libegl1 libgl1 libusb-1.0-0 libxkbcommon-x11-0
```

El archivo `runtime-self-test.json` confirma las dependencias incluidas durante
la compilación.
