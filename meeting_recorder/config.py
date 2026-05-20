"""Configuración del sistema Meeting Recorder.

Lee la configuración desde variables de entorno y valida los valores.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


VALID_MODELS: tuple[str, ...] = ("tiny", "base", "small", "medium", "large", "turbo")


@dataclass
class AppConfig:
    """Configuración de la aplicación.

    Attributes:
        openai_api_key: Clave de API de OpenAI. Requerida para generar resúmenes.
        whisper_model: Nombre del modelo de Whisper a usar para transcripción.
        enable_cuda: Si True, usa GPU NVIDIA para acelerar la transcripción.
        storage_path: Ruta base donde se almacenan grabaciones, transcripciones y resúmenes.
    """

    openai_api_key: str = ""
    whisper_model: str = "base"
    enable_cuda: bool = False
    storage_path: Path = field(default_factory=lambda: Path.home() / "meeting-recorder-data")

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Crea una instancia de AppConfig leyendo variables de entorno.

        Variables de entorno soportadas:
            OPENAI_API_KEY: Clave de API de OpenAI.
            WHISPER_MODEL: Modelo de Whisper (tiny/base/small/medium/large/turbo).
            ENABLE_CUDA: 'true' para habilitar GPU NVIDIA, cualquier otro valor = False.
            STORAGE_PATH o MEETING_RECORDER_DATA_DIR: Ruta de almacenamiento.

        Returns:
            AppConfig con los valores leídos del entorno.
        """
        storage_raw = os.environ.get("STORAGE_PATH") or os.environ.get(
            "MEETING_RECORDER_DATA_DIR"
        )
        storage_path = (
            Path(storage_raw).expanduser()
            if storage_raw
            else Path.home() / "meeting-recorder-data"
        )

        return cls(
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            whisper_model=os.environ.get("WHISPER_MODEL", "base"),
            enable_cuda=os.environ.get("ENABLE_CUDA", "false").lower() == "true",
            storage_path=storage_path,
        )

    def validate(self) -> list[str]:
        """Valida la configuración y retorna una lista de errores.

        Returns:
            Lista de mensajes de error. Lista vacía significa configuración válida.
        """
        errors: list[str] = []

        if not self.openai_api_key or not self.openai_api_key.strip():
            errors.append(
                "OPENAI_API_KEY no está definida o está vacía. "
                "Es necesaria para generar resúmenes."
            )

        if self.whisper_model not in VALID_MODELS:
            errors.append(
                f"Modelo de Whisper '{self.whisper_model}' no es válido. "
                f"Valores válidos: {', '.join(VALID_MODELS)}"
            )

        return errors
