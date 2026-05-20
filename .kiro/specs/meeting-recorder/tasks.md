# Plan de Implementación: Meeting Recorder

## Visión General

Implementación incremental del servicio Meeting Recorder para Fedora Silverblue. Se comienza con la estructura del proyecto y módulos base (configuración, excepciones, almacenamiento), luego se implementan los componentes de negocio (grabador, transcriptor, resumidor), se conectan mediante el pipeline, y finalmente se integra el servicio con el controlador del host y la infraestructura de contenedor. Lenguaje: Python 3.12+ con `uv` como gestor de paquetes.

## Tareas

- [x] 1. Estructura del proyecto e interfaces base
  - [x] 1.1 Crear estructura de directorios y configuración del proyecto
    - Crear directorio `meeting_recorder/` con `__init__.py` y `__main__.py`
    - Configurar `pyproject.toml` con dependencias: `openai-whisper`, `openai`, `hypothesis`, `pytest`
    - Configurar `uv` como gestor de paquetes con Python 3.12+
    - Crear directorio `tests/` con `__init__.py` y archivos de test vacíos
    - Crear directorios `scripts/` y `systemd/`
    - _Requisitos: 5.1, 8.1_

  - [x] 1.2 Implementar módulo de excepciones (`meeting_recorder/exceptions.py`)
    - Definir `MeetingRecorderError` como excepción base
    - Implementar jerarquía: `PipeWireConnectionError`, `RecordingError`, `TranscriptionError`, `InvalidModelError`, `SummaryError`, `ConfigurationError`, `StorageError`, `DiskSpaceError`, `PipelineTimeoutError`
    - Cada excepción con docstring descriptivo
    - _Requisitos: 1.4, 1.8, 3.6, 3.8, 4.6, 4.8, 6.5, 6.6, 7.5_

  - [x] 1.3 Implementar módulo de configuración (`meeting_recorder/config.py`)
    - Implementar `AppConfig` dataclass con campos: `openai_api_key`, `whisper_model`, `enable_cuda`, `storage_path`
    - Definir constante `VALID_MODELS = ("tiny", "base", "small", "medium", "large", "turbo")`
    - Implementar `from_env()` classmethod para leer variables de entorno: `OPENAI_API_KEY`, `WHISPER_MODEL`, `ENABLE_CUDA`, `STORAGE_PATH`/`MEETING_RECORDER_DATA_DIR`
    - Implementar `validate()` que retorna lista de errores (modelo inválido, API key vacía)
    - Valores por defecto: `whisper_model="base"`, `enable_cuda=False`, `storage_path=~/meeting-recorder-data/`
    - _Requisitos: 3.7, 3.8, 4.7, 4.8, 5.7_

  - [ ]* 1.4 Escribir test de propiedad para validación de modelo
    - **Propiedad 5: Validación de nombre de modelo**
    - Usar `hypothesis.strategies.text()` para generar cadenas arbitrarias
    - Verificar que `validate()` solo acepta modelos en `VALID_MODELS`
    - Verificar que cualquier cadena fuera de `VALID_MODELS` produce error de validación
    - **Valida: Requisitos 3.7, 3.8**

  - [ ]* 1.5 Escribir tests unitarios para configuración
    - Test de lectura correcta de variables de entorno
    - Test de valores por defecto cuando variables no están definidas
    - Test de validación con API key vacía
    - Test de validación con modelo inválido
    - Test de validación exitosa con configuración correcta
    - _Requisitos: 3.7, 3.8, 4.7, 4.8, 5.7_

- [x] 2. Módulo de almacenamiento
  - [x] 2.1 Implementar módulo de almacenamiento (`meeting_recorder/storage.py`)
    - Implementar `StorageManager` con `__init__(base_path: Path)`
    - Implementar propiedades: `recordings_dir`, `transcriptions_dir`, `summaries_dir`
    - Implementar `ensure_directories()` que crea `recordings/`, `transcriptions/`, `summaries/` con permisos de lectura/escritura
    - Implementar `generate_timestamp()` con formato `YYYY-MM-DD_HH-MM-SS` en zona horaria local
    - Implementar `check_disk_space(min_mb=50)` usando `shutil.disk_usage`
    - Lanzar `StorageError` si la ruta no es accesible o no se pueden crear directorios
    - Lanzar `DiskSpaceError` si espacio disponible < min_mb
    - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 2.2 Escribir test de propiedad para consistencia de timestamps
    - **Propiedad 3: Consistencia de nombres temporales entre artefactos**
    - Usar `hypothesis.strategies.datetimes()` para generar fechas arbitrarias
    - Verificar que el timestamp generado coincide con patrón `YYYY-MM-DD_HH-MM-SS`
    - Verificar que el formato es parseable y reversible
    - **Valida: Requisitos 1.5, 3.5, 4.5, 6.3**

  - [ ]* 2.3 Escribir test de propiedad para creación de directorios
    - **Propiedad 9: Creación de estructura de directorios**
    - Usar directorios temporales con `tmp_path` de pytest
    - Verificar que `ensure_directories()` crea exactamente `recordings/`, `transcriptions/`, `summaries/`
    - Verificar permisos de lectura y escritura en cada subdirectorio
    - **Valida: Requisitos 6.1, 6.2**

  - [ ]* 2.4 Escribir tests unitarios para almacenamiento
    - Test de creación de directorios en ruta válida
    - Test de error cuando ruta no es accesible
    - Test de verificación de espacio en disco suficiente
    - Test de verificación de espacio en disco insuficiente (lanza `DiskSpaceError`)
    - Test de formato de timestamp
    - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 3. Checkpoint - Verificar módulos base
  - Asegurar que todos los tests pasan, preguntar al usuario si surgen dudas.

- [x] 4. Módulo grabador de audio
  - [x] 4.1 Implementar módulo grabador (`meeting_recorder/recorder.py`)
    - Implementar `AudioRecorder` con dependencia de `StorageManager`
    - Implementar `start()`: lanzar dos subprocesos `pw-record` (micrófono y monitor del sink)
    - Implementar descubrimiento de nodos PipeWire con `pw-cli list-objects`
    - Implementar `stop()`: detener subprocesos, mezclar con `ffmpeg -filter_complex amix=inputs=2:normalize=1`
    - Convertir resultado a WAV 16kHz, 16-bit, mono
    - Implementar `is_recording()` para consultar estado
    - Implementar verificación de espacio en disco durante grabación
    - Implementar degradación elegante: si una fuente no está disponible, continuar con la otra
    - Lanzar `PipeWireConnectionError` si no puede conectar a ninguna fuente
    - Lanzar `DiskSpaceError` si espacio < 50 MB
    - Timeout de 3 segundos para finalización en `stop()`
    - _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [ ]* 4.2 Escribir test de propiedad para formato WAV
    - **Propiedad 1: Formato WAV de salida válido**
    - Generar buffers de audio aleatorios con `hypothesis.strategies.binary(min_size=100, max_size=10000)`
    - Verificar que el archivo WAV resultante tiene: 16000 Hz, 16-bit, 1 canal (mono)
    - Verificar cabeceras RIFF/fmt/data válidas
    - **Valida: Requisitos 1.3, 1.7**

  - [ ]* 4.3 Escribir test de propiedad para normalización de mezcla
    - **Propiedad 2: Normalización de mezcla de audio**
    - Generar pares de buffers de audio con amplitudes diferentes
    - Verificar que la mezcla produce niveles equivalentes (diferencia máxima 3 dB entre fuentes)
    - **Valida: Requisito 1.2**

  - [ ]* 4.4 Escribir tests unitarios para grabador
    - Test de inicio de grabación con ambas fuentes disponibles
    - Test de grabación con una sola fuente (degradación elegante)
    - Test de detención y generación de archivo WAV
    - Test de error cuando PipeWire no está disponible
    - Test de detención por espacio en disco insuficiente
    - Test de timeout de 3 segundos en stop()
    - _Requisitos: 1.1, 1.4, 1.6, 1.7, 1.8_

- [x] 5. Módulo transcriptor
  - [x] 5.1 Implementar módulo transcriptor (`meeting_recorder/transcriber.py`)
    - Implementar `Transcriber` con parámetros `model_name` y `use_cuda`
    - Validar nombre de modelo contra `VALID_MODELS` en `__init__`, lanzar `InvalidModelError` si inválido
    - Implementar `transcribe(audio_path: Path, output_dir: Path) -> TranscriptionResult`
    - Usar `whisper.load_model()` y `model.transcribe()` para transcripción
    - Guardar resultado como `.txt` UTF-8 con mismo prefijo temporal que la grabación
    - Lanzar `TranscriptionError` si el archivo de audio no existe o la transcripción falla
    - _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ]* 5.2 Escribir test de propiedad para transcripción UTF-8
    - **Propiedad 6: Transcripción produce UTF-8 válido**
    - Usar `hypothesis.strategies.text()` con caracteres Unicode, acentos, emojis
    - Verificar que el archivo de salida es UTF-8 válido
    - Verificar que el archivo se ubica en el directorio `transcriptions/`
    - **Valida: Requisito 3.4**

  - [ ]* 5.3 Escribir tests unitarios para transcriptor
    - Test de carga de modelo válido (mock de whisper)
    - Test de error con modelo inválido (`InvalidModelError`)
    - Test de transcripción exitosa con mock de whisper
    - Test de error cuando archivo de audio no existe
    - Test de nombre de archivo de salida con prefijo temporal correcto
    - _Requisitos: 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 6. Módulo resumidor
  - [x] 6.1 Implementar módulo resumidor (`meeting_recorder/summarizer.py`)
    - Implementar `Summarizer` con `api_key` y `model` (default: `gpt-4o-mini`)
    - Validar que `api_key` no está vacía en `__init__`, lanzar `ConfigurationError` si vacía
    - Implementar `summarize(transcription_text: str, output_dir: Path, timestamp: str) -> SummaryResult`
    - Construir prompt que solicite 5-15 viñetas en español con decisiones, tareas y temas
    - Usar cliente OpenAI con timeout de 60 segundos
    - Guardar resultado como `.md` en directorio de resúmenes
    - Lanzar `SummaryError` si la API falla o no responde en tiempo
    - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 6.2 Escribir test de propiedad para formato de resumen
    - **Propiedad 7: Resumen contiene entre 5 y 15 viñetas**
    - Generar textos de transcripción con `hypothesis.strategies.text(min_size=50)`
    - Verificar que el resumen generado (mock de API) contiene entre 5 y 15 bullet points
    - **Valida: Requisito 4.3**

  - [ ]* 6.3 Escribir test de propiedad para ubicación de resumen
    - **Propiedad 8: Resumen es Markdown válido en directorio correcto**
    - Verificar que el archivo de salida tiene extensión `.md`
    - Verificar que el archivo se ubica en el directorio `summaries/`
    - **Valida: Requisito 4.4**

  - [ ]* 6.4 Escribir tests unitarios para resumidor
    - Test de error con API key vacía (`ConfigurationError`)
    - Test de resumen exitoso con mock de OpenAI
    - Test de timeout de API (60 segundos)
    - Test de formato de viñetas en Markdown (5-15 bullets)
    - Test de nombre de archivo con prefijo temporal correcto
    - _Requisitos: 4.3, 4.4, 4.5, 4.6, 4.8_

- [x] 7. Checkpoint - Verificar componentes de negocio
  - Asegurar que todos los tests pasan, preguntar al usuario si surgen dudas.

- [x] 8. Módulo pipeline
  - [x] 8.1 Implementar módulo pipeline (`meeting_recorder/pipeline.py`)
    - Implementar `ProcessingPipeline` con `transcriber` y `summarizer` como dependencias
    - Implementar `process(audio_path: Path)` como método async: transcripción → resumen secuencial
    - Implementar control de concurrencia con `asyncio.Semaphore(3)` para máximo 3 pipelines simultáneos
    - Implementar timeout de 120 segundos por paso usando `asyncio.wait_for`
    - Si transcripción falla, omitir resumen y registrar error
    - Implementar `active_count()` para consultar pipelines en ejecución
    - Lanzar `PipelineTimeoutError` si un paso excede 120 segundos
    - Enviar notificación al completar o fallar (via stdout para que el host la capture)
    - _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 8.2 Escribir test de propiedad para ejecución secuencial
    - **Propiedad 10: Ejecución secuencial del pipeline**
    - Verificar que la transcripción completa antes de iniciar el resumen
    - Verificar que el resumen recibe el texto producido por la transcripción
    - Usar mocks con timestamps para validar orden de ejecución
    - **Valida: Requisito 7.1**

  - [ ]* 8.3 Escribir test de propiedad para límite de concurrencia
    - **Propiedad 11: Límite de pipelines concurrentes**
    - Generar entre 1 y 10 solicitudes simultáneas con `hypothesis.strategies.integers(min_value=1, max_value=10)`
    - Verificar que nunca hay más de 3 pipelines ejecutándose al mismo tiempo
    - Usar `asyncio` para simular concurrencia real
    - **Valida: Requisito 7.2**

  - [ ]* 8.4 Escribir tests unitarios para pipeline
    - Test de ejecución secuencial exitosa (transcripción → resumen)
    - Test de fallo en transcripción omite resumen
    - Test de timeout en un paso (120 segundos, lanza `PipelineTimeoutError`)
    - Test de concurrencia máxima (3 pipelines)
    - Test de notificación al completar exitosamente
    - Test de notificación al fallar
    - _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 9. Servicio principal y CLI
  - [x] 9.1 Implementar servicio principal (`meeting_recorder/service.py`)
    - Implementar `RecordingState` enum con valores `IDLE` y `RECORDING`
    - Implementar `ServiceResponse` dataclass con `status` y `message`
    - Implementar `RecorderService` con `StorageManager` y `AppConfig` como dependencias
    - Implementar `toggle()` que alterna entre `IDLE` y `RECORDING`
    - En toggle a RECORDING: validar config, verificar espacio, iniciar grabador, retornar `ServiceResponse`
    - En toggle a IDLE: detener grabador, lanzar pipeline async, retornar `ServiceResponse`
    - Implementar `status()` que retorna el estado actual
    - Formato de respuesta: JSON de una línea via stdout
    - _Requisitos: 2.1, 2.2, 2.3_

  - [x] 9.2 Implementar CLI y entry point (`meeting_recorder/cli.py` y `__main__.py`)
    - Implementar comando `toggle`: instanciar servicio y ejecutar toggle
    - Implementar comando `status`: consultar estado actual
    - Implementar comando `serve`: mantener el servicio activo esperando comandos
    - Crear `__main__.py` como entry point: `python -m meeting_recorder`
    - Salida JSON para comunicación con el script del host
    - Manejar excepciones y retornar JSON de error
    - _Requisitos: 2.1, 2.2, 2.3, 5.5_

  - [ ]* 9.3 Escribir test de propiedad para alternancia de estado
    - **Propiedad 4: Alternancia de estado de grabación**
    - Usar `hypothesis.strategies.integers(min_value=1, max_value=100)` para N toggles
    - Verificar que estado es RECORDING si N impar, IDLE si N par
    - Comenzar siempre desde estado IDLE
    - **Valida: Requisito 2.1**

  - [ ]* 9.4 Escribir tests unitarios para servicio y CLI
    - Test de toggle desde IDLE a RECORDING
    - Test de toggle desde RECORDING a IDLE (lanza pipeline)
    - Test de respuesta JSON válida con campos status y message
    - Test de status retorna estado correcto
    - Test de manejo de errores retorna JSON de error
    - _Requisitos: 2.1, 2.2, 2.3_

- [x] 10. Checkpoint - Verificar servicio completo
  - Asegurar que todos los tests pasan, preguntar al usuario si surgen dudas.

- [x] 11. Controlador del host y scripts
  - [x] 11.1 Implementar script controlador del host (`scripts/hotkey_controller.sh`)
    - Script bash que registra atajo `Ctrl+Shift+R` via `gsettings` o `dconf`
    - Ejecutar `podman exec meeting-recorder python -m meeting_recorder toggle` al activar atajo
    - Parsear respuesta JSON del contenedor
    - Mostrar notificación con `notify-send` según estado (activo/inactivo/error) durante 3 segundos
    - Timeout de 5 segundos para respuesta del contenedor
    - Manejar caso de contenedor no disponible o no ejecutándose
    - _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 11.2 Implementar script de instalación (`scripts/install.sh`)
    - Copiar archivo Quadlet a `~/.config/containers/systemd/`
    - Registrar atajo de teclado en GNOME via `gsettings`
    - Crear directorio de datos si no existe
    - Ejecutar `systemctl --user daemon-reload` y habilitar servicio
    - Verificar que PipeWire está activo
    - _Requisitos: 5.5, 5.6_

  - [x] 11.3 Eliminar archivos Windows y limpiar proyecto
    - Eliminar `run.bat`, `activate_comfy.ps1` y cualquier archivo `.bat`/`.ps1`/`.cmd`
    - Revisar y eliminar referencias a rutas Windows en código existente
    - Verificar que `check_ffmpeg.py` usa búsqueda en PATH sin rutas absolutas ni `.exe`
    - Asegurar que todos los scripts usan exclusivamente rutas POSIX
    - _Requisitos: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 11.4 Escribir test de propiedad para ausencia de rutas Windows
    - **Propiedad 12: Ausencia de rutas Windows en código fuente**
    - Escanear todos los archivos `.py` y `.sh` del proyecto
    - Verificar que no contienen letras de unidad (`C:\`), backslash como delimitador de ruta, ni `.exe`
    - Usar regex para detectar patrones Windows
    - **Valida: Requisitos 8.2, 8.3**

- [x] 12. Infraestructura de contenedor
  - [x] 12.1 Crear Containerfile
    - Base: `fedora:41`
    - Instalar: `python3.12`, `pipewire`, `pipewire-utils`, `ffmpeg`
    - Copiar `uv` desde imagen oficial `ghcr.io/astral-sh/uv:latest`
    - Copiar `pyproject.toml` y ejecutar `uv sync --frozen`
    - Copiar código fuente `meeting_recorder/`
    - Entrypoint: `uv run python -m meeting_recorder`
    - CMD: `serve`
    - _Requisitos: 5.1, 5.3_

  - [x] 12.2 Crear archivo Quadlet (`systemd/meeting-recorder.container`)
    - Configurar volúmenes: datos del host (`%h/meeting-recorder-data:/data:Z`) y socket PipeWire (`%t/pipewire-0:/tmp/pipewire-0`)
    - Configurar variables de entorno: `OPENAI_API_KEY`, `WHISPER_MODEL`, `ENABLE_CUDA`, `STORAGE_PATH`
    - Configurar reinicio automático: `Restart=on-failure`, `StartLimitBurst=3`, `StartLimitIntervalSec=60`
    - Configurar `WantedBy=default.target` para inicio con sesión de usuario
    - Soporte opcional CUDA via variable de entorno
    - _Requisitos: 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 12.3 Actualizar README.md con documentación del proyecto
    - Documentar requisitos del sistema: Fedora Silverblue, PipeWire
    - Documentar instalación y configuración paso a paso
    - Documentar variables de entorno y sus valores por defecto
    - Documentar uso (atajo de teclado, estructura de archivos de salida)
    - Usar exclusivamente rutas POSIX en toda la documentación
    - _Requisitos: 8.5_

- [x] 13. Checkpoint final - Verificar integración completa
  - Asegurar que todos los tests pasan, preguntar al usuario si surgen dudas.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints aseguran validación incremental
- Los tests de propiedades validan propiedades universales de correctitud (12 propiedades definidas en diseño)
- Los tests unitarios validan ejemplos específicos y casos borde
- El proyecto usa `uv` como gestor de paquetes y `pytest` + `hypothesis` para testing
- Los mocks son necesarios para tests de OpenAI API y PipeWire (no disponibles en CI)
- Cada test de propiedad usa `@settings(max_examples=100)` como mínimo

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["4.1", "5.1", "6.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "5.2", "5.3", "6.2", "6.3", "6.4"] },
    { "id": 5, "tasks": ["8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3", "8.4", "9.1"] },
    { "id": 7, "tasks": ["9.2"] },
    { "id": 8, "tasks": ["9.3", "9.4"] },
    { "id": 9, "tasks": ["11.1", "11.2", "11.3", "12.1", "12.2", "12.3"] },
    { "id": 10, "tasks": ["11.4"] }
  ]
}
```
