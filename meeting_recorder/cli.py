"""Interfaz de línea de comandos del servicio Meeting Recorder.

Comandos disponibles:
    toggle  - Alterna el estado de grabación (inicio/parada)
    status  - Muestra el estado actual del servicio
    serve   - Mantiene el servicio activo como daemon (para el contenedor)

Arquitectura:
    El contenedor ejecuta `serve` como proceso principal (daemon). Este proceso
    gestiona la grabación y el pipeline, y escucha comandos en un socket Unix.
    Los comandos `toggle` y `status` (via `podman exec`) se conectan al socket
    del daemon para enviar comandos y recibir respuestas.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

from meeting_recorder.config import AppConfig
from meeting_recorder.service import RecorderService
from meeting_recorder.storage import StorageManager

logger = logging.getLogger(__name__)

# Socket Unix para comunicación entre daemon y comandos exec
_SOCKET_PATH = "/tmp/meeting-recorder.sock"


def _setup_logging() -> None:
    """Configura el logging básico a stderr."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _build_service() -> RecorderService:
    """Construye el servicio con configuración desde variables de entorno."""
    config = AppConfig.from_env()
    storage = StorageManager(config.storage_path)
    storage.validate_path()
    storage.ensure_directories()
    return RecorderService(storage, config)


def _send_command(command: str) -> str:
    """Envía un comando al daemon via socket Unix y retorna la respuesta."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(10)
        sock.connect(_SOCKET_PATH)
        sock.sendall((command + "\n").encode("utf-8"))
        # Leer respuesta
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        return data.decode("utf-8").strip()
    except (ConnectionRefusedError, FileNotFoundError):
        return json.dumps({
            "status": "error",
            "message": "El daemon no está activo. ¿Está el contenedor corriendo en modo serve?",
        })
    except socket.timeout:
        return json.dumps({
            "status": "error",
            "message": "Timeout esperando respuesta del daemon.",
        })
    finally:
        sock.close()


def cmd_toggle() -> None:
    """Envía comando toggle al daemon y escribe la respuesta a stdout."""
    response = _send_command("toggle")
    print(response, flush=True)


def cmd_status() -> None:
    """Envía comando status al daemon y escribe la respuesta a stdout."""
    response = _send_command("status")
    print(response, flush=True)


def cmd_serve(service: RecorderService) -> None:
    """Ejecuta el daemon que gestiona la grabación.

    Escucha comandos en un socket Unix. Los comandos toggle/status
    ejecutados via `podman exec` se conectan a este socket.
    """
    logger.info("Servicio Meeting Recorder iniciado en modo daemon.")
    print(
        json.dumps({"status": "ready", "message": "Servicio listo"}),
        flush=True,
    )

    # Limpiar socket anterior si existe
    socket_path = Path(_SOCKET_PATH)
    socket_path.unlink(missing_ok=True)

    # Crear socket Unix
    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(_SOCKET_PATH)
    server_sock.listen(5)
    server_sock.settimeout(1.0)  # Para poder verificar shutdown periódicamente

    shutdown = False

    def handle_signal(signum, frame):
        nonlocal shutdown
        logger.info("Recibida señal %s. Cerrando servicio...", signum)
        shutdown = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    def handle_client(conn: socket.socket, service: RecorderService) -> None:
        """Procesa un comando de un cliente conectado al socket."""
        try:
            conn.settimeout(5)
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk

            command = data.decode("utf-8").strip().lower()

            if command == "toggle":
                response = service.toggle()
                conn.sendall((response.to_json() + "\n").encode("utf-8"))
            elif command == "status":
                response = service.status_response()
                conn.sendall((response.to_json() + "\n").encode("utf-8"))
            else:
                error = json.dumps({"status": "error", "message": f"Comando desconocido: {command}"})
                conn.sendall((error + "\n").encode("utf-8"))
        except Exception as e:
            logger.error("Error procesando comando: %s", e)
            try:
                error = json.dumps({"status": "error", "message": str(e)})
                conn.sendall((error + "\n").encode("utf-8"))
            except Exception:
                pass
        finally:
            conn.close()

    logger.info("Escuchando comandos en %s", _SOCKET_PATH)

    try:
        while not shutdown:
            try:
                conn, _ = server_sock.accept()
                # Procesar cada cliente en un hilo para no bloquear
                thread = threading.Thread(
                    target=handle_client, args=(conn, service), daemon=True
                )
                thread.start()
            except socket.timeout:
                continue
            except OSError:
                if shutdown:
                    break
                raise
    finally:
        server_sock.close()
        socket_path.unlink(missing_ok=True)
        logger.info("Servicio Meeting Recorder detenido.")


def main(args: list[str] | None = None) -> int:
    """Punto de entrada principal del CLI.

    Args:
        args: Lista de argumentos. Si es None, usa sys.argv[1:].

    Returns:
        Código de salida (0 = éxito, 1 = error).
    """
    _setup_logging()

    if args is None:
        args = sys.argv[1:]

    command = args[0] if args else "serve"

    # toggle y status se comunican con el daemon via socket
    if command == "toggle":
        cmd_toggle()
        return 0
    elif command == "status":
        cmd_status()
        return 0

    # serve necesita construir el servicio completo
    if command == "serve":
        try:
            service = _build_service()
        except Exception as e:
            print(
                json.dumps({"status": "error", "message": f"Error al iniciar servicio: {e}"}),
                flush=True,
            )
            logger.error("Error al iniciar servicio: %s", e)
            return 1
        cmd_serve(service)
        return 0

    print(
        json.dumps({"status": "error", "message": f"Comando desconocido: {command}"}),
        flush=True,
    )
    return 1
