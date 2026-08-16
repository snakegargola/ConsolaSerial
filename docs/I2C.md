# Herramientas I²C mediante USB Bridge

La pestaña `USB Bridge` concentra todas las funciones I²C. La aplicación
detecta adaptadores FTDI con interfaz MPSSE, permite elegir una interfaz capaz y usa direcciones de
dispositivo de 7 bits (`0x03`–`0x77`). Solo una operación I²C se ejecuta a la
vez para evitar que Scanner, Device Inspector, Display Test y Sequence Builder
intenten controlar el mismo canal simultáneamente.

## Flujo recomendado

1. Asigna una interfaz compatible a `I2C` y selecciona 100 kHz para la primera prueba.
2. Abre `Scanner` y busca el dispositivo.
3. Haz clic sobre una dirección verde; se copiará a las dos herramientas de
   `Device Inspector`.
4. Consulta el datasheet antes de escribir. Identifica dirección del registro,
   número de bytes, orden de bytes y formato del valor.

## Register / Sensor

Esta herramienta ejecuta una lectura o escritura con registro de 8 o 16 bits.
Una lectura muestra al mismo tiempo:

- bytes originales;
- decimal sin signo y con signo;
- hexadecimal, octal y binario;
- ASCII imprimible;
- valor escalado con unidad.

La conversión sigue siempre este orden:

```text
bytes → byte order → right shift → mask/value bits
      → signed/unsigned → scale → offset
```

Esto permite trasladar directamente una fórmula lineal del datasheet. Si el
manual indica `temperatura = valor × 0.0625`, se usa `Scale = 0.0625`. Si los
datos útiles ocupan 12 bits alineados a la izquierda, se usan `Read bytes = 2`,
`Right shift = 4` y `Value bits = 12`.

Se incluyen dos presets demostrativos:

- `TMP102 temperature`: registro `0x00`, 12 bits con signo, resolución
  `0.0625 °C/LSB`.
- `LM75 temperature`: registro `0x00`, 9 bits con signo, resolución
  `0.5 °C/LSB`.

Hay que confirmar el preset con el datasheet de la variante exacta. Sensores
con compensación mediante coeficientes —por ejemplo algunos sensores de
presión/humedad— no pueden convertirse correctamente con una escala lineal.

`Live polling` repite la lectura sin congelar la interfaz y muestra cantidad de
muestras, mínimo, máximo y promedio. Para escribir se puede capturar el valor
como bytes HEX, decimal, hexadecimal, octal, binario o ASCII. La cantidad de
bytes debe coincidir con `Read bytes`.

## Register Map

`Register Map` convierte una tabla del datasheet en un perfil reutilizable. El
encabezado define el nombre, la dirección I²C, el ancho de las direcciones de
registro y su orden de bytes. Cada fila define:

- nombre y dirección del registro;
- cantidad de bytes y acceso `R`, `W` o `RW`;
- endian de los datos, signo, bits útiles, shift y máscara;
- escala, offset y unidad;
- últimos bytes recibidos y valor convertido.

`Read selected` consulta una fila. `Read all` recorre en orden todos los
registros marcados como legibles utilizando una sola transacción a la vez.
`Poll Read all` repite el mapa completo y conserva las muestras, que pueden
exportarse a CSV con timestamp. `Write selected` acepta los mismos formatos de
entrada del inspector sencillo y siempre solicita confirmación.

Los botones `Save profile` y `Load profile` usan archivos
`.i2cmap.json`. El archivo contiene un identificador de esquema y versión para
detectar perfiles incompatibles, y se valida completamente antes de usarlo.
`TMP102 example` carga un mapa funcional de cuatro registros que sirve como
referencia editable.

## Memory Viewer

Está pensado para EEPROM y memorias con puntero interno de 8 o 16 bits.

- `Start address`: primera posición que se leerá o escribirá.
- `Address size`: ancho del puntero interno; no es la dirección I²C de 7 bits.
- `Length`: bytes que se leerán.
- `Page size`: tamaño físico de página indicado por el fabricante.
- `Write delay`: tiempo de ciclo de escritura indicado por el fabricante.

La lectura aparece como una matriz hexadecimal de 16 columnas y una vista
ASCII. Puede guardarse como `.bin`, o cargarse un `.bin` para editarlo y
escribirlo. `Write + verify` pide confirmación, divide automáticamente los datos
sin cruzar páginas y vuelve a leer el rango. Si un byte no coincide, informa la
dirección, el valor esperado y el leído.

> **Precaución:** una dirección interna o un tamaño de página incorrectos
> pueden sobrescribir o envolver datos en una EEPROM. Empieza con una lectura y
> prueba escrituras sobre una zona descartable.

## Organización del código

- `app/i2c_device_inspector.py`: interfaz y validación para registros, sensores
  y memorias; no accede directamente al USB.
- `app/i2c_register_map.py`: modelos validados y formato JSON versionado.
- `app/i2c_register_map_widget.py`: editor, ejecución secuencial, polling y CSV.
- `app/i2c_value_codec.py`: conversión pura entre bytes y representaciones.
- `app/i2c_worker.py`: operaciones FTDI en threads, escaneo, transacciones,
  memoria, SSD1306 y secuencias.
- `app/display_image_converter.py`: conversión exclusiva de imágenes SSD1306.
- `app/serial_monitor.py`: integra señales, selección de canal y exclusión de
  operaciones.

Las conversiones y el cálculo de páginas tienen pruebas en `tests/` y pueden
ejecutarse con:

```bash
.venv/bin/python -m unittest discover -s tests -v
```
