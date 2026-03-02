# Serial Monitor - Nuevas Funcionalidades

## 🔍 1. Búsqueda en Monitor

**Ubicación**: Barra de búsqueda debajo del toolbar del monitor

**Características**:
- Búsqueda en tiempo real mientras escribes
- Resaltado automático de todas las coincidencias
- Navegación con botones ◀ y ▶ (o usar el texto resaltado)
- Contador de coincidencias
- Case-insensitive

**Uso**:
1. Escribe en el campo "🔍 Search"
2. Usa los botones de navegación para moverte entre resultados
3. Limpia el campo para quitar el resaltado

---

## 📌 2. Filtros de Visualización

**Ubicación**: Barra de filtros debajo de la búsqueda

**Características**:
- Filtra mensajes por texto o patrón
- Soporte para expresiones regulares (activa checkbox "Regex")
- Los mensajes filtrados se ocultan temporalmente (no se eliminan)
- Al limpiar el filtro, todos los mensajes reaparecen

**Uso**:
```
Normal: escribir "ERROR" muestra solo líneas con "ERROR"
Regex: escribir "^TX.*error" muestra líneas que empiezan con TX y contienen error
```

**Ejemplos útiles**:
- `ERROR|WARNING` - Muestra errores y advertencias
- `^RX` - Solo mensajes recibidos
- `\d{3,}` - Líneas con números de 3 o más dígitos

---

## 📊 3. Estadísticas de Transmisión

**Ubicación**: Toolbar superior del monitor

**Información mostrada**:
- **Speed**: Velocidad de transmisión (bytes/s)
- **RX**: Total de bytes recibidos
- **TX**: Total de bytes transmitidos

**Actualización**: Cada segundo automáticamente

---

## 🔔 4. Alertas/Notificaciones - INTERFAZ AMIGABLE

**Ubicación**: Botón "Manage Alerts" en el monitor

**Cómo agregar alertas (ahora es muy fácil)**:
1. Click en botón **🔔 Manage Alerts**
2. En el campo "Pattern", escribe el texto o regex a buscar
3. Activa "Use Regex" si quieres usar expresiones regulares
4. Click en "+ Add Alert"
5. Click en "💾 Save Configuration" para guardar

**Ejemplos de patrones**:
- `ERROR` - Detecta cualquier línea con ERROR
- `FATAL` - Detecta cualquier línea con FATAL
- `^.*CRITICAL.*$` - Regex para líneas que contienen CRITICAL

**Gestión**:
- Ver todas las alertas activas en la lista
- Delete: elimina una alerta (selecciona y haz click 🗑)
- Los cambios se guardan en `config.json` automáticamente

**Funcionamiento**:
- Cuando llega un mensaje que coincide con el patrón
- Muestra notificación en la barra de estado por 5 segundos
- Formato: `🔔 ALERT: <patrón>`

---

## 🔁 5. Variables en Comandos

**Ubicación**: Panel de secuencia de comandos

**Variables disponibles**:
- `{timestamp}` - Unix timestamp actual (ej: 1709280000)
- `{counter}` - Contador de comandos enviados en la secuencia (0, 1, 2...)
- `{random}` - Número aleatorio entre 0-999

**Ejemplo de uso**:
```
Comando original: SET_TIME {timestamp}
Enviado como:     SET_TIME 1709280000

Comando original: LOG_{counter}_{random}.txt
Enviado como:     LOG_5_347.txt
```

**Aplicaciones**:
- Testing con timestamps únicos
- Generación de IDs únicos
- Simulación de datos variables

---

## ▶️ 6. Enviar Comando Específico - NUEVA FUNCIONALIDAD

**Ubicación**: Cada fila de la tabla de secuencias

**Botón ▶ (Play)**:
- Envía ese comando específico SIN afectar el ciclo de secuencias
- Útil para probar un comando antes de ejecutar la secuencia completa
- No incrementa el contador de secuencia
- Expande variables ({timestamp}, {counter}, {random})
- Se ejecuta inmediatamente sin esperar

**Uso**:
1. Crea tus comandos en la tabla
2. Click en el botón **▶** de cualquier fila para enviarlo manualmente
3. Continúa con la secuencia normal cuando quieras

**Diferencia con "Start Sequence"**:
- ▶ (botón individual): Envía UN comando, luego se detiene
- Start Sequence: Envía TODOS los comandos en ciclo con intervalo

---

## ⌨️ 7. Atajos de Teclado

| Atajo | Acción |
|-------|--------|
| `Ctrl+Enter` | Enviar comando |
| `Ctrl+L` | Limpiar monitor |
| `Ctrl+K` | Conectar/Desconectar |
| `Ctrl+S` | Guardar configuración |
| `Ctrl+F` | Enfocar búsqueda |
| `F1-F5` | Comandos rápidos (configurables) |

### Comandos Rápidos (F1-F5)

**Configuración**: Editar archivo `config.json`

```json
{
  "quick_commands": {
    "F1": "RESET",
    "F2": "STATUS",
    "F3": "GET_VERSION",
    "F4": "START",
    "F5": "STOP"
  }
}
```

Al presionar F1-F5, el comando se carga en el campo de envío y se transmite automáticamente.

---

## 💾 8. Exportar/Importar Secuencias

**Ubicación**: Panel de secuencia de comandos

**Botones**:
- **📤 Export**: Guarda la secuencia actual en un archivo
- **📥 Import**: Carga una secuencia desde un archivo

**Formato del archivo** (`.seq` o `.json`):
```json
{
  "commands": [
    "INIT",
    "SET_MODE 1",
    "START"
  ],
  "interval": 1.5,
  "mode": "Restart"
}
```

**Uso**:
1. Crea y configura una secuencia
2. Click en "📤 Export"
3. Guarda con extensión `.seq` o `.json`
4. Comparte el archivo con tu equipo
5. Importa con "📥 Import" en cualquier momento

**Aplicaciones**:
- Guardar secuencias de prueba
- Compartir configuraciones de testing
- Tener múltiples secuencias predefinidas

---

## 🎯 Flujo Recomendado para Testing

### Paso 1: Configurar Alertas (muy fácil ahora)
1. Click en "🔔 Manage Alerts"
2. Agrega patrones para detectar errores/fallos
3. Click "Save"

### Paso 2: Crear Secuencia de Prueba
1. Agregar comandos en la lista
2. Usar variables para datos únicos: `{timestamp}`, `{counter}`
3. Usar botón ▶ para probar comandos individuales

### Paso 3: Ejecutar Secuencia
1. Click "Start Sequence"
2. Observar resultados en monitor
3. Las alertas aparecerán si hay coincidencias

### Paso 4: Guardar para Reutilizar
1. Click "📤 Export" para guardar secuencia
2. Compartir con equipo o guardar para luego

---

## 💡 Ejemplos Prácticos

### Testing de Firmware

```json
// config.json - Alertas para errores
{
  "alerts": [
    {"pattern": "ERROR", "regex": false},
    {"pattern": "FATAL", "regex": false},
    {"pattern": "^.*TIMEOUT.*$", "regex": true}
  ],
  "quick_commands": {
    "F1": "VERSION",
    "F2": "RESET",
    "F3": "STATUS"
  }
}
```

### Secuencia de Prueba con Variables

```
Comando 1: SET_ID {timestamp}
Comando 2: START_TEST {counter}
Comando 3: WAIT 2
Comando 4: GET_RESULT
```

Cada vez que ejecutes, los comandos tendrán valores únicos.

---

## 📝 Notas

- **Buffer de log completo**: Los filtros no eliminan mensajes, solo los ocultan
- **Estadísticas**: Se reinician al desconectar
- **Contador de secuencia**: Se reinicia al detener la secuencia
- **Botón ▶**: Puedes usarlo sin estar en modo secuencia (aunque no esté corriendo)
- **Alertas**: Ahora configurables desde UI sin editar `config.json`

---

## ⚙️ Configuración Avanzada

### config.json Completo

```json
{
  "port": "/dev/ttyUSB0",
  "baud": 115200,
  "sequence_commands": ["RESET", "SET_ID {timestamp}", "START", "STATUS"],
  "sequence_interval": 2.0,
  "sequence_mode": "Restart",
  "alerts": [
    {"pattern": "ERROR", "regex": false, "sound": false},
    {"pattern": "^CRITICAL", "regex": true, "sound": false}
  ],
  "quick_commands": {
    "F1": "RESET",
    "F2": "STATUS",
    "F3": "GET_VERSION",
    "F4": "START",
    "F5": "STOP"
  }
}
```

---

¡Disfruta tu Serial Monitor mejorado! 🚀
