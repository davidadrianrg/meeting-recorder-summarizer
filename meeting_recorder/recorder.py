"""Grabación de audio del sistema mediante PipeWire.

Captura simultáneamente el micrófono (fuente de entrada) y el monitor
del sink (salida de aplicaciones como Teams), mezcla ambas fuentes con
ffmpeg y guarda el resultado como WAV 16kHz mono.
"""

from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from meeting_recorder.exceptions import DiskSpaceError, PipeWireConnectionError, RecordingError
from meeting_recorder.storage import StorageManager

logger = logging.getLogger(__name__)

# Parámetros de audio objetivo
_SAMPLE_RATE = 16000
_CHANNELS = 1
_BIT_DEPTH = "s16le"  # PCM 16-bit little-endian


@dataclass
class RecordingResult:
    """Resultado de una grabación.

    Attributes:
        file_path: Ruta al archivo WAV mezclado y convertido.
        duration_seconds: Duración aproximada de la grabación en segundos.
        sources_captured: Lista de fuentes capturadas ('microphone', 'monitor').
    """

    file_path: Path
    duration_seconds: float
    sources_captured: list[str] = field(default_factory=list)


def _find_pipewire_nodes() -> dict[str, str | None]:
    """Descubre los nodos de PipeWire disponibles.

    Busca el nodo de micrófono (fuente de entrada) y el monitor del sink
    (salida de aplicaciones) usando pw-cli.

    Returns:
        Diccionario con claves 'microphone' y 'monitor', valores son los
        nombres de nodo o None si no se encontraron.
    """
    nodes: dict[str, str | None] = {"microphone": None, "monitor": None}

    try:
        result = subprocess.run(
            ["pw-cli", "list-objects"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return nodes

        # Buscar nodos de tipo Source (micrófono) y Source/Monitor (monitor del sink)
        current_node: dict = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if "node.name" in line:
                name = line.split("=", 1)[-1].strip().strip('"')
                current_node["name"] = name
            if "media.class" in line:
                media_class = line.split("=", 1)[-1].strip().strip('"')
                current_node["class"] = media_class

                if media_class == "Audio/Source" and nodes["microphone"] is None:
                    nodes["microphone"] = current_node.get("name")
                elif media_class == "Audio/Source/Virtual" and nodes["monitor"] is None:
                    nodes["monitor"] = current_node.get("name")
                elif "Monitor" in media_class and nodes["monitor"] is None:
                    nodes["monitor"] = current_node.get("name")

                current_node = {}

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return nodes


class AudioRecorder:
    """Graba audio del sistema capturando micrófono y salida de aplicaciones.

    Args:
        storage: Gestor de almacenamiento para determinar rutas y verificar espacio.
    """

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage
        self._mic_process: subprocess.Popen | None = None
        self._monitor_process: subprocess.Popen | None = None
        self._start_time: float | None = None
        self._current_timestamp: str | None = None
        self._sources_captured: list[str] = []
        self._disk_check_thread: threading.Thread | None = None
        self._stop_disk_check = threading.Event()

    def is_recording(self) -> bool:
        """Retorna True si hay una grabación activa."""
        return self._mic_process is not None or self._monitor_process is not None

    def start(self) -> None:
        """Inicia la grabación capturando micrófono y monitor del sink.

        Lanza dos procesos pw-record en paralelo. Si una fuente no está
        disponible, continúa con la otra y registra una advertencia.

        Raises:
            PipeWireConnectionError: Si no se puede conectar a ninguna fuente de audio.
            RecordingError: Si ya hay una grabación activa.
            DiskSpaceError: Si el espacio en disco es inferior a 50 MB.
        """
        if self.is_recording():
            raise RecordingError("Ya hay una grabación activa.")

        # Verificar espacio en disco antes de empezar
        self._storage.check_disk_space(min_mb=50)

        # Verificar que pw-record está disponible
        if not shutil.which("pw-record"):
            raise PipeWireConnectionError(
                "pw-record no está disponible. "
                "Instala pipewire-utils dentro del contenedor."
            )

        self._current_timestamp = self._storage.generate_timestamp()
        self._sources_captured = []

        nodes = _find_pipewire_nodes()
        mic_node = nodes.get("microphone")
        monitor_node = nodes.get("monitor")

        tmp_dir = self._storage.recordings_dir

        # Iniciar captura de micrófono
        mic_file = tmp_dir / f"{self._current_timestamp}_mic_tmp.wav"
        if mic_node:
            try:
                self._mic_process = subprocess.Popen(
                    ["pw-record", "--target", mic_node, str(mic_file)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                self._sources_captured.append("microphone")
                logger.info("Capturando micrófono desde nodo '%s'.", mic_node)
            except OSError as e:
                logger.warning("No se pudo iniciar captura de micrófono: %s", e)
        else:
            # Intentar sin especificar nodo (usa el predeterminado)
            try:
                self._mic_process = subprocess.Popen(
                    ["pw-record", str(mic_file)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                self._sources_captured.append("microphone")
                logger.info("Capturando micrófono (nodo predeterminado).")
            except OSError as e:
                logger.warning("No se pudo iniciar captura de micrófono: %s", e)

        # Iniciar captura del monitor (salida de aplicaciones)
        monitor_file = tmp_dir / f"{self._current_timestamp}_monitor_tmp.wav"
        if monitor_node:
            try:
                self._monitor_process = subprocess.Popen(
                    ["pw-record", "--target", monitor_node, str(monitor_file)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                self._sources_captured.append("monitor")
                logger.info("Capturando monitor desde nodo '%s'.", monitor_node)
            except OSError as e:
                logger.warning("No se pudo iniciar captura del monitor: %s", e)

        if not self._sources_captured:
            raise PipeWireConnectionError(
                "No se pudo conectar a ninguna fuente de audio de PipeWire. "
                "Verifica que PipeWire está activo y el socket está montado."
            )

        if "microphone" not in self._sources_captured:
            logger.warning("Grabando solo con monitor (sin micrófono).")
        if "monitor" not in self._sources_captured:
            logger.warning("Grabando solo con micrófono (sin monitor de aplicaciones).")

        self._start_time = time.monotonic()

        # Iniciar hilo de verificación de espacio en disco
        self._stop_disk_check.clear()
        self._disk_check_thread = threading.Thread(
            target=self._monitor_disk_space, daemon=True
        )
        self._disk_check_thread.start()

        logger.info(
            "Grabación iniciada: %s (fuentes: %s)",
            self._current_timestamp,
            ", ".join(self._sources_captured),
        )

    def stop(self) -> RecordingResult:
        """Detiene la grabación y mezcla las fuentes en un único archivo WAV.

        Detiene los procesos pw-record, mezcla los archivos temporales con
        ffmpeg y convierte el resultado a WAV 16kHz mono.

        Returns:
            RecordingResult con la ruta del archivo final y metadatos.

        Raises:
            RecordingError: Si no hay grabación activa o falla la mezcla.
        """
        if not self.is_recording():
            raise RecordingError("No hay ninguna grabación activa.")

        # Detener verificación de espacio
        self._stop_disk_check.set()

        duration = time.monotonic() - (self._start_time or time.monotonic())
        timestamp = self._current_timestamp or self._storage.generate_timestamp()
        tmp_dir = self._storage.recordings_dir

        # Detener procesos de captura con timeout de 3 segundos
        for proc, name in [
            (self._mic_process, "micrófono"),
            (self._monitor_process, "monitor"),
        ]:
            if proc is not None:
                try:
                    proc.send_signal(signal.SIGINT)
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    logger.warning("Proceso de %s no terminó en 3s, forzando cierre.", name)
                    proc.kill()
                    proc.wait()
                except OSError:
                    pass

        self._mic_process = None
        self._monitor_process = None

        # Rutas de archivos temporales
        mic_file = tmp_dir / f"{timestamp}_mic_tmp.wav"
        monitor_file = tmp_dir / f"{timestamp}_monitor_tmp.wav"
        output_file = self._storage.recordings_dir / f"{timestamp}.wav"

        # Mezclar fuentes disponibles con ffmpeg
        try:
            self._mix_audio(mic_file, monitor_file, output_file)
        except Exception as e:
            raise RecordingError(f"Error al mezclar fuentes de audio: {e}") from e
        finally:
            # Limpiar archivos temporales
            for tmp_file in (mic_file, monitor_file):
                if tmp_file.exists():
                    tmp_file.unlink(missing_ok=True)

        sources = list(self._sources_captured)
        self._sources_captured = []
        self._current_timestamp = None
        self._start_time = None

        logger.info(
            "Grabación detenida. Archivo: '%s' (%.1fs, fuentes: %s)",
            output_file.name,
            duration,
            ", ".join(sources),
        )

        return RecordingResult(
            file_path=output_file,
            duration_seconds=duration,
            sources_captured=sources,
        )

    def _mix_audio(
        self,
        mic_file: Path,
        monitor_file: Path,
        output_file: Path,
    ) -> None:
        """Mezcla los archivos de audio temporales en un único WAV 16kHz mono.

        Si solo hay una fuente disponible, la convierte directamente.
        Si hay dos fuentes, las mezcla con amix normalizando los niveles.

        Args:
            mic_file: Archivo WAV del micrófono (puede no existir).
            monitor_file: Archivo WAV del monitor (puede no existir).
            output_file: Ruta de salida del archivo mezclado.

        Raises:
            RecordingError: Si ffmpeg no está disponible o falla la mezcla.
        """
        if not shutil.which("ffmpeg"):
            raise RecordingError(
                "ffmpeg no está disponible. "
                "Instala ffmpeg dentro del contenedor."
            )

        mic_exists = mic_file.exists() and mic_file.stat().st_size > 0
        monitor_exists = monitor_file.exists() and monitor_file.stat().st_size > 0

        if not mic_exists and not monitor_exists:
            raise RecordingError(
                "No se encontraron archivos de audio temporales para mezclar."
            )

        if mic_exists and monitor_exists:
            # Mezclar ambas fuentes con normalización
            cmd = [
                "ffmpeg", "-y",
                "-i", str(mic_file),
                "-i", str(monitor_file),
                "-filter_complex", "amix=inputs=2:normalize=1",
                "-ac", str(_CHANNELS),
                "-ar", str(_SAMPLE_RATE),
                "-c:a", "pcm_s16le",
                str(output_file),
            ]
        else:
            # Solo una fuente disponible
            source = mic_file if mic_exists else monitor_file
            cmd = [
                "ffmpeg", "-y",
                "-i", str(source),
                "-ac", str(_CHANNELS),
                "-ar", str(_SAMPLE_RATE),
                "-c:a", "pcm_s16le",
                str(output_file),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RecordingError(
                f"ffmpeg falló al mezclar audio: {result.stderr[-500:]}"
            )

    def _monitor_disk_space(self) -> None:
        """Hilo que verifica el espacio en disco cada 10 segundos durante la grabación."""
        while not self._stop_disk_check.wait(timeout=10):
            try:
                self._storage.check_disk_space(min_mb=50)
            except DiskSpaceError as e:
                logger.error("Espacio en disco insuficiente durante grabación: %s", e)
                # Detener la grabación de forma ordenada
                if self.is_recording():
                    try:
                        self.stop()
                    except Exception:
                        pass
                break
