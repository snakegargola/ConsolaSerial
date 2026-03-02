# Guía de Desarrollo

## Setup del Entorno

### Linux
```bash
# 1. Crear entorno virtual
python3 -m venv GuisSerial

# 2. Activar entorno
source GuisSerial/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar aplicación
./GuisSerial/bin/python main.py
```

### Windows
```powershell
# 1. Crear entorno virtual
python -m venv GuisSerial

# 2. Activar entorno
.\GuisSerial\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar aplicación
python main.py
```

## Estructura de Código

### Agregar Nueva Funcionalidad

1. **En serial_monitor.py** - Agregar UI si es necesario
2. **En serial_worker.py** - Si requiere I/O serial asincrónico
3. **En config_manager.py** - Si necesita persistencia
4. **En log_manager.py** - Si requiere logging especial

### Ejemplo: Agregar Nuevo Control

```python
# En _build_config_panel():
new_label = lbl("New Feature: 🔹")
new_label.setToolTip("Description of the feature")
grid.addWidget(new_label, r, 0)

self.new_control = QCheckBox("Enable")
self.new_control.setToolTip("What this does")
self.new_control.stateChanged.connect(self._on_feature_changed)
grid.addWidget(self.new_control, r, 1)

# Agregar método handler:
def _on_feature_changed(self):
    enabled = self.new_control.isChecked()
    self.config.set("new_feature", enabled)
```

## Styling PyQt6

### Colores del Tema
- **Dark Mode BG**: `#1C1C1C`
- **Dark Mode Text**: `#E0E0E0`
- **Light Mode BG**: `#FFFFFF`
- **Light Mode Text**: `#000000`
- **Accent**: `#2E8B57` (Connect button)

### Aplicar Estilo a Widget

```python
widget.setStyleSheet("""
    QWidget {
        background-color: #1C1C1C;
        color: #E0E0E0;
    }
    QPushButton {
        background-color: #2E8B57;
        color: white;
    }
""")
```

## Comunicación Serial Segura

### Thread-safe Communication
```python
# En SerialMonitorApp (main thread):
self.worker.port = port_name
self.worker.settings = {
    'baud': baud_rate,
    'parity': parity
}
# Worker thread procesa cambios de forma segura
```

### Manejo de Errores
```python
try:
    # operación serial
    pass
except serial.SerialException as e:
    self._handle_error(f"Serial error: {e}")
```

## Testing

### Simulación de Puerto Serial
```python
# Usar socat para crear puerto virtual
# Linux:
socat -d -d pty,raw,echo=0 pty,raw,echo=0

# Luego usar los puertos /dev/pts/X en ambas terminales
```

### Validación de Entrada
```python
def _validate_input(self, data):
    if not isinstance(data, (str, bytes)):
        return False
    if len(data) == 0:
        return False
    return True
```

## Performance

### Optimizaciones Implementadas
1. **Buffering de logs** - Se mantiene buffer completo en memoria
2. **QTimer para updates** - No se bloquea GUI
3. **Worker thread** - Serial I/O en thread separado
4. **Regex compilados** - Alertas usan regex compiladas

### Monitoreo
```python
# Estadísticas habilitadas automáticamente
# Ver: self._stats_rx_bytes, self._stats_tx_bytes
# Se actualizan cada 1 segundo
```

## Debugging

### Logs de Debug
```python
# Agregar print para debugging:
print(f"Debug: {variable}", file=sys.stderr)

# Ejecutar con output visible:
./GuisSerial/bin/python main.py 2>&1
```

### Inspector de Objetos
```python
# Ver propiedades de objeto
print(vars(obj))
print(dir(obj))
```

## Distribución de Cambios

1. Hacer cambios en código
2. Probar en desarrollo: `./GuisSerial/bin/python main.py`
3. Compilar ejecutable: `bash scripts/build_linux.sh`
4. Probar ejecutable: `./dist/linux/SerialMonitor`
5. Hacer commit: `git add . && git commit -m "v2: descripción"`

