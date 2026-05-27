"""Pipeline de procesamiento automático: transcripción → resumen → renombrado.

Ejecuta el pipeline de forma asíncrona en segundo plano cuando se detiene
una grabación. Permite hasta 3 pipelines concurrentes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import shutil
from pathlib import Path

from meeting_recorder.exceptions import PipelineTimeoutError, TranscriptionError
from meeting_recorder.summarizer import Summarizer
from meeting_recorder.transcriber import Transcriber

logger = logging.getLogger(__name__)

_STEP_TIMEOUT_SECONDS = 7200
_MAX_CONCURRENT = 3


def _send_notification(title: str, body: str) -> None:
    """Envía una notificación de escritorio al usuario.

    Intenta usar notify-send con el DBUS del host. Si no está disponible,
    imprime a stdout como fallback.
    """
    # Intentar con notify-send (funciona si DBUS_SESSION_BUS_ADDRESS está disponible)
    if shutil.which("notify-send"):
        env = os.environ.copy()
        # Buscar el socket de DBUS en el runtime dir montado del host
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        bus_path = f"unix:path={xdg_runtime}/bus"
        if xdg_runtime and Path(f"{xdg_runtime}/bus").exists():
            env["DBUS_SESSION_BUS_ADDRESS"] = bus_path

        try:
            subprocess.run(
                ["notify-send", "--expire-time=5000", title, body],
                timeout=3,
                check=False,
                env=env,
            )
            return
        except Exception:
            pass

    # Fallback: imprimir a stdout
    print(f"[NOTIFICATION] {title}: {body}", flush=True)


def _rename_session_files(
    audio_path: Path,
    transcription_path: Path,
    summary_path: Path,
    title_slug: str,
    timestamp: str,
) -> tuple[Path, Path, Path]:
    """Renombra los archivos de una sesión con un nombre descriptivo.

    El formato final es: YYYY-MM-DD_titulo-descriptivo.ext
    Solo usa la fecha (sin hora) para mantener los nombres legibles.

    Args:
        audio_path: Ruta actual del archivo de audio.
        transcription_path: Ruta actual de la transcripción.
        summary_path: Ruta actual del resumen.
        title_slug: Slug del título generado por la IA.
        timestamp: Timestamp original (YYYY-MM-DD_HH-MM-SS).

    Returns:
        Tupla con las nuevas rutas (audio, transcripción, resumen).
    """
    if not title_slug:
        return audio_path, transcription_path, summary_path

    # Extraer solo la fecha del timestamp (YYYY-MM-DD)
    date_part = timestamp[:10] if len(timestamp) >= 10 else timestamp
    new_base = f"{date_part}_{title_slug}"

    new_paths = []
    for old_path in (audio_path, transcription_path, summary_path):
        if old_path.exists():
            new_path = old_path.parent / f"{new_base}{old_path.suffix}"
            # Evitar colisiones: si ya existe, añadir sufijo numérico
            if new_path.exists() and new_path != old_path:
                counter = 1
                while new_path.exists():
                    new_path = old_path.parent / f"{new_base}-{counter}{old_path.suffix}"
                    counter += 1
            try:
                old_path.rename(new_path)
                logger.info("Renombrado: '%s' → '%s'", old_path.name, new_path.name)
                new_paths.append(new_path)
            except OSError as e:
                logger.warning("No se pudo renombrar '%s': %s", old_path.name, e)
                new_paths.append(old_path)
        else:
            new_paths.append(old_path)

    return tuple(new_paths)  # type: ignore


class ProcessingPipeline:
    """Pipeline asíncrono de transcripción y resumen.

    Args:
        transcriber: Instancia del transcriptor de Whisper.
        summarizer: Instancia del resumidor de OpenAI.
    """

    def __init__(self, transcriber: Transcriber, summarizer: Summarizer) -> None:
        self._transcriber = transcriber
        self._summarizer = summarizer
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
        self._active_count = 0

    def active_count(self) -> int:
        """Retorna el número de pipelines actualmente en ejecución."""
        return self._active_count

    async def process(self, audio_path: Path) -> None:
        """Procesa un archivo de audio: transcripción → resumen → renombrado.

        Ejecuta los pasos secuencialmente. Si la transcripción falla,
        no se ejecuta el resumen. Respeta el límite de 3 pipelines concurrentes.

        Args:
            audio_path: Ruta al archivo WAV a procesar.
        """
        async with self._semaphore:
            self._active_count += 1
            try:
                await self._run_pipeline(audio_path)
            finally:
                self._active_count -= 1

    async def _run_pipeline(self, audio_path: Path) -> None:
        """Ejecuta los pasos del pipeline con timeout por paso."""
        timestamp = audio_path.stem
        transcriptions_dir = audio_path.parent.parent / "transcriptions"
        summaries_dir = audio_path.parent.parent / "summaries"

        logger.info("Iniciando pipeline para '%s'.", audio_path.name)

        # Paso 1: Transcripción
        try:
            transcription_result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self._transcriber.transcribe,
                    audio_path,
                    transcriptions_dir,
                ),
                timeout=_STEP_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            msg = f"Transcripción de '{audio_path.name}' excedió {_STEP_TIMEOUT_SECONDS}s."
            logger.error(msg)
            _send_notification(
                "Meeting Recorder - Error",
                f"Timeout en transcripción: {audio_path.name}",
            )
            raise PipelineTimeoutError(msg)
        except TranscriptionError as e:
            logger.error("Error en transcripción de '%s': %s", audio_path.name, e)
            _send_notification(
                "Meeting Recorder - Error",
                f"Falló la transcripción: {audio_path.name}",
            )
            return  # No continuar con el resumen

        logger.info("Transcripción completada para '%s'.", audio_path.name)

        # Paso 2: Resumen
        try:
            summary_result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    self._summarizer.summarize,
                    transcription_result.text,
                    summaries_dir,
                    timestamp,
                ),
                timeout=_STEP_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            msg = f"Resumen de '{audio_path.name}' excedió {_STEP_TIMEOUT_SECONDS}s."
            logger.error(msg)
            _send_notification(
                "Meeting Recorder - Error",
                f"Timeout en resumen: {audio_path.name}",
            )
            raise PipelineTimeoutError(msg)
        except Exception as e:
            logger.error("Error al generar resumen de '%s': %s", audio_path.name, e)
            _send_notification(
                "Meeting Recorder - Error",
                f"Falló el resumen: {audio_path.name}",
            )
            return

        # Paso 3: Renombrar archivos con título descriptivo
        title_slug = summary_result.title
        if title_slug:
            _rename_session_files(
                audio_path=audio_path,
                transcription_path=transcription_result.file_path,
                summary_path=summary_result.file_path,
                title_slug=title_slug,
                timestamp=timestamp,
            )
            display_name = title_slug.replace("-", " ").title()
        else:
            display_name = timestamp

        logger.info("Pipeline completado para '%s'.", audio_path.name)

        # Notificación de escritorio al usuario
        _send_notification(
            "✅ Meeting Recorder",
            f"Resumen disponible: {display_name}",
        )

    def schedule(self, audio_path: Path) -> asyncio.Task:
        """Programa el procesamiento de un archivo de audio en segundo plano.

        Args:
            audio_path: Ruta al archivo WAV a procesar.

        Returns:
            Task de asyncio que ejecuta el pipeline.
        """
        loop = asyncio.get_event_loop()
        return loop.create_task(self.process(audio_path))
