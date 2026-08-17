# Herramientas I²C mediante USB Bridge

La pestaña `USB Bridge` concentra todas las funciones I²C. La aplicación
detecta adaptadores FTDI con interfaz MPSSE, permite elegir una interfaz capaz y usa direcciones de
dispositivo de 7 bits (`0x03`–`0x77`). Cada sesión ejecuta una sola operación
I²C a la vez para evitar que sus herramientas intenten controlar el mismo
canal. Dos interfaces asignadas a I²C tienen sesiones independientes y sí
pueden trabajar simultáneamente.

## Flujo recomendado

1. Asigna una interfaz compatible a `I2C` y selecciona 100 kHz para la primera prueba.
2. Abre `Scanner` y busca el dispositivo.
3. Haz clic sobre una dirección verde; se seleccionará en `Transaction Lab` y
   también quedará disponible en las demás herramientas.
4. Prueba primero una lectura o transacción combinada en `Transaction Lab`.
5. Consulta el datasheet antes de escribir. Identifica dirección del registro,
   número de bytes, orden de bytes y formato del valor.

## Ajustes comunes del bus

Todas las herramientas de la sesión comparten estos ajustes:

- `Clock`: presets desde 10 kHz hasta 1 MHz o un valor editable entre 1 kHz y
  3.4 MHz. El escáner y el laboratorio muestran la frecuencia real obtenida.
- `Retries`: reintentos admitidos por PyFtdi, de 1 a 16.
- `Clock stretching`: permite esperar cuando el esclavo mantiene SCL bajo.
  Requiere conectar también `xDBUS7` a SCL; no debe activarse sin ese cableado.

El cableado MPSSE normal es `xDBUS0=SCL` y `xDBUS1+xDBUS2=SDA`, con resistencias
pull-up externas. La `x` corresponde a la interfaz elegida.

## Transaction Lab

### Raw I²C

Permite escritura, lectura, escritura seguida por `repeated START` y lectura, y
pruebas de ACK en dirección de lectura o escritura. Los bytes se capturan como
HEX. Cada resultado conserva timestamp, dirección, TX, RX, estado (`ACK`,
`NACK`, `TIMEOUT`, `USB` o `INVALID`) y duración. El historial puede exportarse
como CSV o JSON.

### SMBus

Incluye Quick, Send/Receive Byte, Byte Data, Word Data, Process Call y Block
Read/Write. Los words se transmiten little-endian y los bloques se limitan a
32 bytes. `PEC CRC-8` agrega o verifica el Packet Error Code; un PEC incorrecto
se reporta como error. No se debe activar PEC si el dispositivo no lo documenta.

### Diagnóstico y recuperación

`Check SCL/SDA` comprueba el estado esperado en reposo: ambas líneas en HIGH.
`Recover bus` emite hasta nueve pulsos de SCL y una condición STOP para intentar
liberar un esclavo que dejó SDA en LOW. La rutina nunca fuerza un HIGH: solo
conduce LOW o libera el pin a las resistencias pull-up. Desconecta otros maestros
antes de usarla.

## Register / Sensor

Esta herramienta ejecuta una lectura o escritura con registro de 8 o 16 bits.
Una lectura muestra al mismo tiempo:

- bytes originales;
- decimal sin signo y con signo;
- hexadecimal, octal y binario;
- ASCII imprimible;
- valor escalado con unidad;
- fórmula segura y campo de bits con etiqueta opcional.

La conversión sigue siempre este orden:

```text
bytes → byte order → right shift → mask/value bits
      → signed/unsigned → scale → offset
```

Esto permite trasladar directamente una fórmula lineal del datasheet. Si el
manual indica `temperatura = valor × 0.0625`, se usa `Scale = 0.0625`. Si los
datos útiles ocupan 12 bits alineados a la izquierda, se usan `Read bytes = 2`,
`Right shift = 4` y `Value bits = 12`.

Para conversiones no lineales, `Formula` admite aritmética limitada con `x`
(valor ya escalado), `raw`, `unsigned` y `signed`, además de `abs`, `min`,
`max`, `round`, `sqrt` y `pow`. No ejecuta código Python. `Bit field` acepta un
bit (`3`) o un rango inclusivo (`7:5`), y `Enum` traduce valores mediante pares
como `0=Sleep,1=Active`.

Se incluyen dos presets demostrativos:

- `TMP102 temperature`: registro `0x00`, 12 bits con signo, resolución
  `0.0625 °C/LSB`.
- `LM75 temperature`: registro `0x00`, 9 bits con signo, resolución
  `0.5 °C/LSB`.

Hay que confirmar el preset con el datasheet de la variante exacta. Sensores
con compensación mediante varios registros de calibración pueden necesitar un
cálculo externo aunque la fórmula cubra conversiones sencillas.

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
- escala, offset, fórmula y unidad;
- campo de bits y enumeración;
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

Para EEPROM como 24C04/08/16, `Address bits in slave address` divide el rango en
bancos y suma el número de banco a la dirección I²C base. `Bank size` debe salir
del datasheet. También se puede rellenar el buffer con un byte y comparar la
lectura contra un BIN; las diferencias quedan resaltadas.

> **Precaución:** una dirección interna o un tamaño de página incorrectos
> pueden sobrescribir o envolver datos en una EEPROM. Empieza con una lectura y
> prueba escrituras sobre una zona descartable.

## Límites explícitos

- PyFtdi expone direcciones I²C de 7 bits; esta versión no emula direcciones de
  10 bits.
- El mapa de registros y la fórmula de un sensor deben obtenerse del datasheet.
- La recuperación no corrige ausencia de pull-ups, niveles incompatibles ni un
  dispositivo dañado.
- Una función SMBus solo debe usarse si el dispositivo la documenta.

## Organización del código

- `app/i2c_device_inspector.py`: interfaz y validación para registros, sensores
  y memorias; no accede directamente al USB.
- `app/i2c_transaction_lab.py`: Raw I²C, SMBus, diagnóstico e historial.
- `app/i2c_bus.py`: ajustes compartidos, validación, errores y PEC.
- `app/i2c_formula.py`: fórmulas limitadas, bits y enumeraciones.
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
