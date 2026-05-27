# Containerfile - Meeting Recorder Summarizer
# Imagen basada en Fedora 41 con PipeWire, ffmpeg y Python 3.12
#
# Construcción:
#   podman build -t meeting-recorder-summarizer .
#
# Ejecución manual (para pruebas):
#   podman run --rm -it --userns keep-id \
#     -v ~/meeting-recorder-summarizer-data:/data \
#     -v $XDG_RUNTIME_DIR:/run/user/host \
#     -e XDG_RUNTIME_DIR=/run/user/host \
#     -e PULSE_SERVER=unix:/run/user/host/pulse/native \
#     -e OPENAI_API_KEY=sk-... \
#     meeting-recorder-summarizer
#
# Estructura del volumen /data (montado desde ~/meeting-recorder-summarizer-data/ del host):
#   /data/recordings/       - Grabaciones de audio (.wav)
#   /data/transcriptions/   - Transcripciones de texto (.txt)
#   /data/summaries/        - Resúmenes en Markdown (.md)
#   /data/models/           - Modelos de Whisper descargados (persisten entre reinicios)

FROM fedora:41

# Instalar dependencias del sistema
RUN dnf install -y \
    python3.12 \
    pipewire \
    pipewire-utils \
    pipewire-pulseaudio \
    pulseaudio-utils \
    ffmpeg \
    libnotify \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# Instalar uv (gestor de paquetes Python)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copiar archivos de configuración de dependencias primero (mejor cache de capas)
COPY pyproject.toml README.md ./

# Copiar código fuente (necesario para que hatchling resuelva el paquete)
COPY meeting_recorder/ meeting_recorder/

# Instalar dependencias Python con uv (CPU por defecto, sin CUDA)
RUN uv sync --no-dev

# Hacer /app accesible para cualquier usuario (necesario con --userns keep-id)
RUN chmod -R a+rwX /app

# Directorio de datos montado desde el host.
VOLUME ["/data"]

# Variables de entorno
ENV WHISPER_MODEL=base
ENV ENABLE_CUDA=false
ENV STORAGE_PATH=/data

# Punto de entrada - usar Python directamente del venv (evita que uv necesite caché)
ENTRYPOINT ["/app/.venv/bin/python", "-m", "meeting_recorder"]

# Comando por defecto: modo daemon esperando comandos
CMD ["serve"]
