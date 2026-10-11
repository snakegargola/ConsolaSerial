# Guía de desarrollo

## Entorno Linux

```bash
python3 -m venv GuisSerial
source GuisSerial/bin/activate
pip install -r requirements.txt
./GuisSerial/bin/python main.py
```

## Agregar funcionalidad

1. `app/serial_monitor.py`: interfaz y coordinación.
2. `app/serial_worker.py`: comunicación serial asíncrona.
3. `app/config_manager.py`: configuración persistente.
4. `app/log_manager.py`: logging especializado.

## Pruebas

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -v -s tests
```

## Build

```bash
bash scripts/build_linux.sh
```
