"""Servicio principal de Meeting Recorder.

Gestiona el estado de grabación (IDLE/RECORDING) y coordina
el grabador, pipeline y configuración.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from meeting_recorder.config import AppConfig
from meeting_recorder.exceptions import (
    ConfigurationError,
    MeetingRecorderError,
    PipeWireConnectionError,
)
from meeting_recorder.pipeline import ProcessingPipeline
from meeting_recorder.recorder import AudioRecorder
from meeting_recorder.storage import StorageManager
from meeting_recorder.summarizer import Summarizer
from meeting_recorder.transcriber import Transcriber

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    """Estado del servicio de grabación."""

    IDLE = "idle"
    RECORDING = "recording"


@dataclass
class ServiceResponse:
    """Respuesta del servicio en formato JSON.

    Attributes:
        status: Estado resultante ('recording_started', 'recording_stopped', 'error', 'status').
        message: Mensaje descriptivo.
        timestamp: Timestamp de la grabación (solo en recording_started/stopped).
        file: Nombre del archivo generado (solo en recording_stopped).
    """

    status: str
    message: str
    timestamp: str | None = None
    file: str | None = None

    def to_json(self) -> str:
        """Serializa la respuesta a JSON de una línea."""
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data, ensure_ascii=False)


class RecorderService:
    """Servicio principal que gestiona el ciclo de vida de las grabaciones.

    Args:
        storage: Gestor de almacenamiento.
        config: Configuración de la aplicación.
    """

    def __init__(self, storage: StorageManager, config: AppConfig) -> None:
        self._storage = storage
        self._config = config
        self._state = RecordingState.IDLE
        self._recorder: AudioRecorder | None = None
        self._pipeline: ProcessingPipeline | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_pipeline(self) -> ProcessingPipeline:
        """Crea o retorna el pipeline de procesamiento."""
        if self._pipeline is None:
            errors = self._config.validate()
            if errors:
                raise ConfigurationError("; ".join(errors))

            # Los modelos de Whisper se guardan en /data/models/ para persistir
            # entre reinicios del contenedor (el volumen /data está montado del host)
            models_dir = self._storage.base_path / "models"

            transcriber = Transcriber(
                model_name=self._config.whisper_model,
                use_cuda=self._config.enable_cuda,
                models_dir=models_dir,
            )
            summarizer = Summarizer(
                api_key=self._config.openai_api_key,
                model="gpt-5.4-nano",
            )
            self._pipeline = ProcessingPipeline(transcriber, summarizer)
        return self._pipeline

    def _get_recorder(self) -> AudioRecorder:
        """Crea o retorna el grabador de audio."""
        if self._recorder is None:
            self._recorder = AudioRecorder(self._storage)
        return self._recorder

    def toggle(self) -> ServiceResponse:
        """Alterna el estado de grabación entre IDLE y RECORDING.

        Si está en IDLE, inicia la grabación.
        Si está en RECORDING, detiene la grabación y lanza el pipeline.

        Returns:
            ServiceResponse con el nuevo estado y metadatos.
        """
        if self._state == RecordingState.IDLE:
            return self._start_recording()
        else:
            return self._stop_recording()

    def _start_recording(self) -> ServiceResponse:
        """Inicia la grabación de audio."""
        try:
            recorder = self._get_recorder()
            recorder.start()
            self._state = RecordingState.RECORDING
            timestamp = recorder._current_timestamp or ""
            logger.info("Grabación iniciada: %s", timestamp)
            return ServiceResponse(
                status="recording_started",
                message="Grabación iniciada",
                timestamp=timestamp,
            )
        except PipeWireConnectionError as e:
            logger.error("Error de PipeWire al iniciar grabación: %s", e)
            return ServiceResponse(status="error", message=str(e))
        except MeetingRecorderError as e:
            logger.error("Error al iniciar grabación: %s", e)
            return ServiceResponse(status="error", message=str(e))

    def _stop_recording(self) -> ServiceResponse:
        """Detiene la grabación y lanza el pipeline en segundo plano."""
        try:
            recorder = self._get_recorder()
            result = recorder.stop()
            self._state = RecordingState.IDLE

            # Lanzar pipeline en segundo plano
            self._launch_pipeline(result.file_path)

            logger.info("Grabación detenida: %s", result.file_path.name)
            return ServiceResponse(
                status="recording_stopped",
                message="Grabación detenida. Procesando en segundo plano...",
                timestamp=result.file_path.stem,
                file=result.file_path.name,
            )
        except MeetingRecorderError as e:
            logger.error("Error al detener grabación: %s", e)
            self._state = RecordingState.IDLE
            return ServiceResponse(status="error", message=str(e))

    def _launch_pipeline(self, audio_path: Path) -> None:
        """Lanza el pipeline de procesamiento en segundo plano."""
        try:
            pipeline = self._get_pipeline()
            # Ejecutar en un hilo separado con su propio event loop
            import threading

            def run_pipeline():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(pipeline.process(audio_path))
                finally:
                    loop.close()

            thread = threading.Thread(target=run_pipeline, daemon=True)
            thread.start()
            logger.info("Pipeline lanzado en segundo plano para '%s'.", audio_path.name)
        except ConfigurationError as e:
            logger.warning(
                "No se pudo lanzar el pipeline (configuración incompleta): %s", e
            )

    def status(self) -> RecordingState:
        """Retorna el estado actual del servicio."""
        return self._state

    def status_response(self) -> ServiceResponse:
        """Retorna el estado actual como ServiceResponse."""
        return ServiceResponse(
            status="status",
            message=f"Estado actual: {self._state.value}",
            timestamp=self._state.value,
        )
