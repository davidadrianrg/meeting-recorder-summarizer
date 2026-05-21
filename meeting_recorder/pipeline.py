"""Pipeline de procesamiento automático: transcripción → resumen.

Ejecuta el pipeline de forma asíncrona en segundo plano cuando se detiene
una grabación. Permite hasta 3 pipelines concurrentes.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from meeting_recorder.exceptions import PipelineTimeoutError, TranscriptionError
from meeting_recorder.summarizer import Summarizer
from meeting_recorder.transcriber import Transcriber

logger = logging.getLogger(__name__)

_STEP_TIMEOUT_SECONDS = 7200
_MAX_CONCURRENT = 3


def _send_notification(title: str, body: str) -> None:
    """Envía una notificación de escritorio usando notify-send.

    Funciona en el host si DBUS_SESSION_BUS_ADDRESS está disponible.
    En el contenedor, imprime a stdout para que el controlador del host la capture.
    """
    import subprocess
    import shutil

    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "--expire-time=5000", title, body],
                timeout=3,
                check=False,
            )
        except Exception:
            pass
    # Siempre imprimir a stdout para que el host pueda capturarlo
    print(f"[NOTIFICATION] {title}: {body}", flush=True)


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
        """Procesa un archivo de audio: transcripción → resumen.

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
            await asyncio.wait_for(
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

        logger.info("Pipeline completado para '%s'.", audio_path.name)
        _send_notification(
            "Meeting Recorder",
            f"Resumen disponible: {timestamp}",
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
