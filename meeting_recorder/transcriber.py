"""Transcripción de audio usando el modelo local de Whisper.

Convierte archivos WAV a texto plano usando openai-whisper.
El resultado se guarda como .txt UTF-8 en el directorio de transcripciones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from meeting_recorder.config import VALID_MODELS
from meeting_recorder.exceptions import InvalidModelError, TranscriptionError

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Resultado de una transcripción.

    Attributes:
        text: Texto transcrito completo.
        file_path: Ruta al archivo .txt guardado.
        language_detected: Idioma detectado por Whisper, o None si no se detectó.
    """

    text: str
    file_path: Path
    language_detected: str | None


class Transcriber:
    """Transcribe archivos de audio usando Whisper local.

    Args:
        model_name: Nombre del modelo de Whisper. Debe ser uno de:
            tiny, base, small, medium, large, turbo.
        use_cuda: Si True, usa GPU NVIDIA para acelerar la transcripción.
        models_dir: Directorio donde se descargan y cachean los modelos.
            Si es None, usa el directorio por defecto de Whisper (~/.cache/whisper).
            En el contenedor se pasa /data/models/ para persistir entre reinicios.

    Raises:
        InvalidModelError: Si model_name no es un modelo válido.
    """

    def __init__(
        self,
        model_name: str = "base",
        use_cuda: bool = False,
        models_dir: Path | None = None,
    ) -> None:
        if model_name not in VALID_MODELS:
            raise InvalidModelError(
                f"Modelo '{model_name}' no es válido. "
                f"Modelos disponibles: {', '.join(VALID_MODELS)}"
            )
        self._model_name = model_name
        self._use_cuda = use_cuda
        self._models_dir = models_dir
        self._model = None  # Carga diferida

    def _load_model(self) -> None:
        """Carga el modelo de Whisper si no está cargado.

        La primera vez descarga el modelo desde internet (solo ocurre una vez).
        Las siguientes veces lo carga desde el caché local en models_dir.
        """
        if self._model is None:
            import whisper

            device = "cuda" if self._use_cuda else "cpu"

            # Preparar directorio de modelos si se especificó
            download_root = None
            if self._models_dir is not None:
                self._models_dir.mkdir(parents=True, exist_ok=True)
                download_root = str(self._models_dir)

            logger.info(
                "Cargando modelo Whisper '%s' en dispositivo '%s'%s...",
                self._model_name,
                device,
                f" (caché: {download_root})" if download_root else "",
            )
            self._model = whisper.load_model(
                self._model_name,
                device=device,
                download_root=download_root,
            )
            logger.info("Modelo Whisper '%s' cargado correctamente.", self._model_name)

    def transcribe(self, audio_path: Path, output_dir: Path) -> TranscriptionResult:
        """Transcribe un archivo de audio y guarda el resultado como .txt UTF-8.

        El nombre del archivo de salida usa el mismo prefijo temporal que el
        archivo de audio de entrada (sin extensión).

        Args:
            audio_path: Ruta al archivo WAV de entrada.
            output_dir: Directorio donde se guardará el archivo .txt.

        Returns:
            TranscriptionResult con el texto, ruta del archivo y idioma detectado.

        Raises:
            TranscriptionError: Si el archivo de audio no existe, no es legible,
                o la transcripción falla por cualquier motivo.
        """
        if not audio_path.exists():
            raise TranscriptionError(
                f"El archivo de audio '{audio_path}' no existe."
            )

        if not audio_path.is_file():
            raise TranscriptionError(
                f"La ruta '{audio_path}' no es un archivo válido."
            )

        try:
            self._load_model()
        except Exception as e:
            raise TranscriptionError(
                f"No se pudo cargar el modelo de Whisper '{self._model_name}': {e}"
            ) from e

        try:
            logger.info("Transcribiendo '%s'...", audio_path.name)
            result = self._model.transcribe(
                str(audio_path),
                language="es",  # Reuniones principalmente en español
                verbose=False,
            )
        except Exception as e:
            raise TranscriptionError(
                f"Error al transcribir '{audio_path.name}': {e}"
            ) from e

        text = result.get("text", "").strip()
        language = result.get("language")

        # Guardar como .txt con el mismo prefijo temporal que la grabación
        output_path = output_dir / f"{audio_path.stem}.txt"
        try:
            output_path.write_text(text, encoding="utf-8")
        except OSError as e:
            raise TranscriptionError(
                f"No se pudo guardar la transcripción en '{output_path}': {e}"
            ) from e

        logger.info("Transcripción guardada en '%s'.", output_path)
        return TranscriptionResult(
            text=text,
            file_path=output_path,
            language_detected=language,
        )
