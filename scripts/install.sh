#!/usr/bin/env bash
# install.sh - Instalador del servicio Meeting Recorder en Fedora Silverblue
#
# Instala el servicio Podman como servicio systemd de usuario y registra
# el atajo de teclado Ctrl+Shift+R en GNOME.
#
# Uso:
#   ./scripts/install.sh [--build]   # --build construye la imagen antes de instalar

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"
CONTAINER_NAME="meeting-recorder-summarizer"
DATA_DIR="${MEETING_RECORDER_DATA_DIR:-${HOME}/meeting-recorder-summarizer-data}"
QUADLET_DIR="${HOME}/.config/containers/systemd"
HOTKEY_SCRIPT="${SCRIPT_DIR}/hotkey_controller.sh"
BUILD_IMAGE=false

# Parsear argumentos
for arg in "$@"; do
    case $arg in
        --build) BUILD_IMAGE=true ;;
    esac
done

echo "=== Instalando Meeting Recorder ==="
echo "Directorio del proyecto : ${PROJECT_DIR}"
echo "Directorio de datos     : ${DATA_DIR}"
echo ""

# 1. Verificar dependencias del host
echo "[1/5] Verificando dependencias..."

if ! command -v podman &>/dev/null; then
    echo "ERROR: podman no está instalado." >&2
    exit 1
fi

if ! command -v notify-send &>/dev/null; then
    echo "  AVISO: notify-send no disponible. Las notificaciones no funcionarán."
fi

if ! systemctl --user is-active --quiet pipewire 2>/dev/null; then
    echo "  AVISO: PipeWire no está activo. Verifica con: systemctl --user status pipewire"
fi

echo "  OK"

# 2. Construir imagen del contenedor (opcional)
if [ "${BUILD_IMAGE}" = true ]; then
    echo ""
    echo "[2/5] Construyendo imagen del contenedor..."
    podman build -t "${CONTAINER_NAME}:latest" "${PROJECT_DIR}"
    echo "  OK"
else
    echo ""
    echo "[2/5] Omitiendo construcción de imagen (usa --build para construirla)."
    echo "  Para construir manualmente: podman build -t ${CONTAINER_NAME} ${PROJECT_DIR}"
fi

# 3. Crear directorio de datos
echo ""
echo "[3/5] Creando estructura de directorios en '${DATA_DIR}'..."
mkdir -p "${DATA_DIR}/recordings" "${DATA_DIR}/transcriptions" "${DATA_DIR}/summaries"
echo "  OK"

# 4. Instalar archivo Quadlet y registrar atajo de teclado
echo ""
echo "[4/5] Instalando servicio systemd (Quadlet) y atajo de teclado..."

# Instalar Quadlet
mkdir -p "${QUADLET_DIR}"
cp "${PROJECT_DIR}/systemd/meeting-recorder-summarizer.container" "${QUADLET_DIR}/"
echo "  Quadlet instalado en: ${QUADLET_DIR}/meeting-recorder-summarizer.container"

# Recargar systemd
systemctl --user daemon-reload

# Hacer los scripts ejecutables
chmod +x "${HOTKEY_SCRIPT}"
chmod +x "${SCRIPT_DIR}/install.sh"

# Registrar atajo de teclado en GNOME
SHORTCUT_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/meeting-recorder-summarizer/"

gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"${SHORTCUT_PATH}" \
    name "Meeting Recorder - Toggle" 2>/dev/null || true
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"${SHORTCUT_PATH}" \
    command "${HOTKEY_SCRIPT}" 2>/dev/null || true
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:"${SHORTCUT_PATH}" \
    binding "<Control><Shift>r" 2>/dev/null || true

# Añadir a la lista de atajos personalizados
EXISTING_SHORTCUTS=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "@as []")
if ! echo "${EXISTING_SHORTCUTS}" | grep -q "meeting-recorder-summarizer"; then
    NEW_SHORTCUTS=$(echo "${EXISTING_SHORTCUTS}" | python3 -c "
import sys, ast
raw = sys.stdin.read().strip().replace('@as ', '')
try:
    shortcuts = ast.literal_eval(raw)
except Exception:
    shortcuts = []
path = '${SHORTCUT_PATH}'
if path not in shortcuts:
    shortcuts.append(path)
print(repr(shortcuts).replace(\"'\", '\"'))
" 2>/dev/null || echo "[\"${SHORTCUT_PATH}\"]")
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "${NEW_SHORTCUTS}" 2>/dev/null || true
fi

echo "  Atajo Ctrl+Shift+R registrado."
echo "  OK"

# 5. Habilitar servicio
echo ""
echo "[5/5] Habilitando servicio systemd..."
if systemctl --user enable --now "${CONTAINER_NAME}.service" 2>/dev/null; then
    echo "  Servicio habilitado e iniciado."
else
    echo "  AVISO: No se pudo habilitar el servicio automáticamente."
    echo "  Asegúrate de haber construido la imagen primero:"
    echo "    podman build -t ${CONTAINER_NAME} ${PROJECT_DIR}"
    echo "  Luego inicia el servicio:"
    echo "  systemctl --user start ${CONTAINER_NAME}.service"
fi
echo "  OK"

echo ""
echo "=== Instalación completada ==="
echo ""
echo "Configuración necesaria:"
echo "  Crea el archivo de entorno con tu API key de OpenAI:"
echo "    echo 'OPENAI_API_KEY=sk-...' > ~/.config/meeting-recorder-summarizer.env"
echo "    chmod 600 ~/.config/meeting-recorder-summarizer.env"
echo ""
echo "Uso:"
echo "  Ctrl+Shift+R  →  Iniciar/detener grabación"
echo "  Los archivos se guardan en: ${DATA_DIR}"
echo ""
echo "Gestión del servicio:"
echo "  systemctl --user status ${CONTAINER_NAME}.service"
echo "  journalctl --user -u ${CONTAINER_NAME}.service -f"
