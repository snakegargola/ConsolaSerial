# Build de Linux

## Requisitos

- Python 3.12+
- Dependencias del proyecto instaladas
- Dependencias de build:

```bash
pip install -r requirements.txt
pip install -r requirements-build.txt
```

## Compilar

```bash
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
```

El resultado queda en `dist/linux/SerialMonitor`, junto con `config.json`,
`serial.png`, `LEEME.md` y el reporte de autoprueba.

El script ejecuta `SerialMonitor --self-test` y valida PyQt, PyFtdi, PyUSB,
libusb y el grafo completo de la aplicación antes de entregar el binario.

El acceso a puertos seriales y adaptadores FTDI en Linux requiere los permisos
descritos en [`docs/LINUX.md`](docs/LINUX.md).
