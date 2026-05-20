#!/usr/bin/env bash
# hotkey_controller.sh - Controlador de atajo de teclado para Meeting Recorder Summarizer
#
# Se ejecuta en el host (Fedora Silverblue) cuando el usuario presiona Ctrl+Shift+R.
# Envía el comando 'toggle' al contenedor Podman y muestra notificaciones de escritorio.
#
# Uso:
#   ./hotkey_controller.sh          # Toggle grabación
#   ./hotkey_controller.sh status   # Consultar estado

set -euo pipefail

CONTAINER_NAME="meeting-recorder-summarizer"
TIMEOUT=5
COMMAND="${1:-toggle}"

# Verificar que podman está disponible
if ! command -v podman &>/dev/null; then
    notify-send --expire-time=3000 \
        "Meeting Recorder Summarizer - Error" \
        "podman no está disponible en el sistema." 2>/dev/null || true
    echo '{"status":"error","message":"podman no disponible"}' >&2
    exit 1
fi

# Verificar que el contenedor está en ejecución
if ! podman ps --format "{{.Names}}" 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
    notify-send --expire-time=3000 \
        "Meeting Recorder Summarizer - Error" \
        "El servicio de grabación no está activo. Inicia el contenedor primero." 2>/dev/null || true
    echo '{"status":"error","message":"Contenedor no está en ejecución"}' >&2
    exit 1
fi

# Enviar comando al contenedor con timeout
RESPONSE=$(timeout "${TIMEOUT}" podman exec "${CONTAINER_NAME}" \
    python -m meeting_recorder "${COMMAND}" 2>/dev/null) || {
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 124 ]; then
        notify-send --expire-time=3000 \
            "Meeting Recorder Summarizer - Error" \
            "El contenedor no respondió en ${TIMEOUT} segundos." 2>/dev/null || true
        echo '{"status":"error","message":"Timeout: contenedor no respondió"}' >&2
    else
        notify-send --expire-time=3000 \
            "Meeting Recorder Summarizer - Error" \
            "Error al comunicarse con el contenedor." 2>/dev/null || true
        echo '{"status":"error","message":"Error de comunicación con el contenedor"}' >&2
    fi
    exit 1
}

# Parsear respuesta JSON
STATUS=$(echo "${RESPONSE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
MESSAGE=$(echo "${RESPONSE}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))" 2>/dev/null || echo "")

# Mostrar notificación según el estado
case "${STATUS}" in
    recording_started)
        notify-send --expire-time=3000 \
            "🔴 Meeting Recorder Summarizer" \
            "Grabación activa" 2>/dev/null || true
        ;;
    recording_stopped)
        notify-send --expire-time=3000 \
            "⏹ Meeting Recorder Summarizer" \
            "Grabación detenida. Procesando en segundo plano..." 2>/dev/null || true
        ;;
    error)
        notify-send --expire-time=3000 \
            "Meeting Recorder Summarizer - Error" \
            "${MESSAGE}" 2>/dev/null || true
        ;;
    status)
        notify-send --expire-time=3000 \
            "Meeting Recorder Summarizer" \
            "${MESSAGE}" 2>/dev/null || true
        ;;
    *)
        notify-send --expire-time=3000 \
            "Meeting Recorder Summarizer" \
            "${MESSAGE:-Respuesta desconocida del servicio}" 2>/dev/null || true
        ;;
esac

# Imprimir respuesta para depuración
echo "${RESPONSE}"
