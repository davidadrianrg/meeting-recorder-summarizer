# Meeting Recorder Summarizer

Herramienta de grabación automática de reuniones para **Fedora Silverblue**. Graba el audio del sistema (micrófono + salida de aplicaciones como Teams), transcribe con Whisper local y genera resúmenes con bullet points usando la API de OpenAI.

## Requisitos del sistema

| Componente | Requisito |
|------------|-----------|
| Sistema operativo | Fedora Silverblue 40+ |
| Servidor de audio | PipeWire (incluido por defecto) |
| Contenedor | Podman 4.0+ (incluido por defecto) |
| Escritorio | GNOME (para atajos de teclado y notificaciones) |
| API key | OpenAI API key (para resúmenes) |

> **Nota**: La transcripción con Whisper funciona completamente en local sin conexión a internet. Solo el paso de resumen requiere la API de OpenAI.

## Estructura de archivos generados

```
~/meeting-recorder-summarizer-data/
├── recordings/          # Grabaciones de audio (.wav)
│   └── 2025-01-15_09-30-00.wav
├── transcriptions/      # Transcripciones de texto (.txt)
│   └── 2025-01-15_09-30-00.txt
├── summaries/           # Resúmenes en Markdown (.md)
│   └── 2025-01-15_09-30-00.md
└── models/              # Modelos de Whisper (se descargan automáticamente)
    └── base.pt
```

Los archivos de una misma sesión comparten el mismo prefijo temporal (`YYYY-MM-DD_HH-MM-SS`).

## Instalación rápida

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd meeting-recorder-summarizer
```

### 2. Configurar la API key de OpenAI

Crea el archivo de entorno que el servicio leerá directamente:

```bash
mkdir -p ~/.config
echo "OPENAI_API_KEY=sk-tu-clave-aqui" > ~/.config/meeting-recorder-summarizer.env
chmod 600 ~/.config/meeting-recorder-summarizer.env
```

> **Nota**: El archivo tiene permisos `600` para que solo tu usuario pueda leerlo.

### 3. Construir la imagen del contenedor

```bash
podman build -t meeting-recorder-summarizer .
```

### 4. Ejecutar el instalador

```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

El instalador:
- Crea la estructura de directorios en `~/meeting-recorder-summarizer-data/`
- Instala el servicio systemd (Quadlet) en `~/.config/containers/systemd/`
- Registra el atajo de teclado `Ctrl+Shift+R` en GNOME
- Habilita e inicia el servicio automáticamente

O en un solo paso (construye la imagen e instala):

```bash
./scripts/install.sh --build
```

## Uso

### Atajo de teclado

| Acción | Atajo |
|--------|-------|
| Iniciar/detener grabación | `Ctrl+Shift+R` |

Al presionar el atajo:
- **Primera vez**: Inicia la grabación. Aparece una notificación "🔴 Grabación activa".
- **Segunda vez**: Detiene la grabación. La transcripción y el resumen se generan automáticamente en segundo plano. Aparece una notificación cuando el resumen está listo.

### Gestión del servicio

```bash
# Ver estado del servicio
systemctl --user status meeting-recorder-summarizer.service

# Iniciar manualmente
systemctl --user start meeting-recorder-summarizer.service

# Detener
systemctl --user stop meeting-recorder-summarizer.service

# Ver logs
journalctl --user -u meeting-recorder-summarizer.service -f
```

### Comandos directos al contenedor

```bash
# Consultar estado
podman exec meeting-recorder-summarizer python -m meeting_recorder status

# Toggle manual (sin atajo de teclado)
podman exec meeting-recorder-summarizer python -m meeting_recorder toggle
```

## Variables de entorno

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `OPENAI_API_KEY` | Clave de API de OpenAI | (requerida) |
| `WHISPER_MODEL` | Modelo de Whisper para transcripción | `base` |
| `ENABLE_CUDA` | Habilitar GPU NVIDIA para transcripción | `false` |
| `STORAGE_PATH` | Ruta de almacenamiento dentro del contenedor | `/data` |
| `MEETING_RECORDER_DATA_DIR` | Ruta de almacenamiento en el host | `~/meeting-recorder-summarizer-data/` |

### Modelos de Whisper disponibles

| Modelo | Tamaño | Velocidad | Precisión |
|--------|--------|-----------|-----------|
| `tiny` | 39 MB | Muy rápido | Básica |
| `base` | 74 MB | Rápido | Buena (recomendado) |
| `small` | 244 MB | Moderado | Mejor |
| `medium` | 769 MB | Lento | Alta |
| `large` | 1550 MB | Muy lento | Muy alta |
| `turbo` | 809 MB | Rápido | Alta |

El modelo se descarga automáticamente la primera vez que se usa y se guarda en
`~/meeting-recorder-summarizer-data/models/` para reutilizarse en reinicios posteriores.

Para cambiar el modelo, edita `~/.config/containers/systemd/meeting-recorder-summarizer.container`:

```ini
Environment=WHISPER_MODEL=small
```

Luego reinicia el servicio:

```bash
systemctl --user restart meeting-recorder-summarizer.service
```

### Habilitar GPU NVIDIA (opcional)

Si tienes una GPU NVIDIA y el NVIDIA Container Toolkit instalado:

```ini
Environment=ENABLE_CUDA=true
```

## Desarrollo

### Configurar entorno de desarrollo

```bash
# Instalar uv si no está disponible
curl -LsSf https://astral.sh/uv/install.sh | sh

# Crear entorno virtual e instalar dependencias
uv sync --dev

# Activar entorno
source .venv/bin/activate
```

### Ejecutar tests

```bash
# Todos los tests
uv run pytest tests/ -v

# Solo tests unitarios (sin property-based)
uv run pytest tests/ -v -k "not Property"

# Solo tests de propiedades (Hypothesis)
uv run pytest tests/ -v -k "Property"

# Test específico
uv run pytest tests/test_config.py -v
```

### Estructura del proyecto

```
meeting-recorder-summarizer/
├── Containerfile                              # Imagen del contenedor
├── pyproject.toml                             # Dependencias Python (uv)
├── README.md
├── check_ffmpeg.py                            # Utilidad de diagnóstico de ffmpeg
├── scripts/
│   ├── hotkey_controller.sh                   # Script del host para el atajo de teclado
│   └── install.sh                             # Instalador del servicio
├── systemd/
│   └── meeting-recorder-summarizer.container  # Quadlet para Podman (systemd)
├── meeting_recorder/
│   ├── __init__.py
│   ├── __main__.py                            # Entry point: python -m meeting_recorder
│   ├── cli.py                                 # Comandos: toggle, status, serve
│   ├── config.py                              # Configuración desde variables de entorno
│   ├── exceptions.py                          # Jerarquía de excepciones
│   ├── pipeline.py                            # Pipeline async: transcripción → resumen
│   ├── recorder.py                            # Grabación de audio via PipeWire
│   ├── service.py                             # Servicio principal (estado IDLE/RECORDING)
│   ├── storage.py                             # Gestión de directorios y timestamps
│   ├── summarizer.py                          # Resúmenes con OpenAI API
│   └── transcriber.py                         # Transcripción con Whisper local
└── tests/
    ├── test_config.py
    ├── test_pipeline.py
    ├── test_service.py
    ├── test_storage.py
    ├── test_summarizer.py
    ├── test_transcriber.py
    └── test_windows_cleanup.py
```

## Solución de problemas

### La grabación no inicia

1. Verifica que el contenedor está corriendo:
   ```bash
   podman ps | grep meeting-recorder-summarizer
   ```

2. Verifica que PipeWire está activo:
   ```bash
   systemctl --user status pipewire
   ```

3. Verifica que el socket de PipeWire está montado en el contenedor:
   ```bash
   podman exec meeting-recorder-summarizer ls /tmp/pipewire-0
   ```

### La transcripción es lenta

El modelo `base` es el equilibrio recomendado entre velocidad y precisión. Para reuniones largas (>1 hora), considera usar `small` o habilitar CUDA si tienes GPU NVIDIA.

### El resumen no se genera

Verifica que la API key está configurada:
```bash
podman exec meeting-recorder-summarizer python -m meeting_recorder status
```

Si aparece un error de configuración, revisa `~/.config/environment.d/meeting-recorder-summarizer.conf`.

### El atajo de teclado no funciona

Verifica que el atajo está registrado en GNOME:
```bash
gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings
```

Si no aparece, ejecuta de nuevo el instalador:
```bash
./scripts/install.sh
```
