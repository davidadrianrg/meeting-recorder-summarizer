"""Gestión del almacenamiento de grabaciones, transcripciones y resúmenes.

Crea y mantiene la estructura de directorios:
    <base>/recordings/       - Archivos WAV de grabaciones
    <base>/transcriptions/   - Archivos TXT de transcripciones
    <base>/summaries/        - Archivos MD de resúmenes
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from meeting_recorder.exceptions import DiskSpaceError, StorageError


class StorageManager:
    """Gestiona la estructura de directorios y convenciones de nombres.

    Args:
        base_path: Ruta base donde se crearán los subdirectorios.

    Raises:
        StorageError: Si la ruta no es accesible o no se pueden crear los directorios.
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path.expanduser().resolve()

    @property
    def base_path(self) -> Path:
        """Ruta base del almacenamiento."""
        return self._base_path

    @property
    def recordings_dir(self) -> Path:
        """Directorio de grabaciones de audio."""
        return self._base_path / "recordings"

    @property
    def transcriptions_dir(self) -> Path:
        """Directorio de transcripciones de texto."""
        return self._base_path / "transcriptions"

    @property
    def summaries_dir(self) -> Path:
        """Directorio de resúmenes en Markdown."""
        return self._base_path / "summaries"

    def ensure_directories(self) -> None:
        """Crea la estructura de directorios si no existe.

        Crea recordings/, transcriptions/ y summaries/ bajo la ruta base,
        con permisos de lectura y escritura para el usuario del proceso.

        Raises:
            StorageError: Si la ruta base no es accesible o no se pueden crear
                los directorios por falta de permisos u otro error.
        """
        try:
            for directory in (
                self.recordings_dir,
                self.transcriptions_dir,
                self.summaries_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)
                # Verificar que el directorio es escribible
                if not os.access(directory, os.W_OK | os.R_OK):
                    raise StorageError(
                        f"El directorio '{directory}' no tiene permisos de lectura/escritura."
                    )
        except StorageError:
            raise
        except PermissionError as e:
            raise StorageError(
                f"Sin permisos para crear directorios en '{self._base_path}': {e}"
            ) from e
        except OSError as e:
            raise StorageError(
                f"No se pudo crear la estructura de directorios en '{self._base_path}': {e}"
            ) from e

    def generate_timestamp(self) -> str:
        """Genera un timestamp en formato YYYY-MM-DD_HH-MM-SS en zona horaria local.

        Returns:
            Cadena con el timestamp, por ejemplo: '2025-01-15_09-30-00'
        """
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    def check_disk_space(self, min_mb: int = 50) -> bool:
        """Verifica que hay suficiente espacio en disco disponible.

        Args:
            min_mb: Espacio mínimo requerido en megabytes. Por defecto 50 MB.

        Returns:
            True si hay suficiente espacio disponible.

        Raises:
            DiskSpaceError: Si el espacio disponible es inferior a min_mb.
        """
        try:
            usage = shutil.disk_usage(self._base_path if self._base_path.exists() else Path("/"))
            available_mb = usage.free / (1024 * 1024)
            if available_mb < min_mb:
                raise DiskSpaceError(
                    f"Espacio en disco insuficiente: {available_mb:.1f} MB disponibles, "
                    f"se requieren al menos {min_mb} MB."
                )
            return True
        except DiskSpaceError:
            raise
        except OSError as e:
            raise StorageError(f"No se pudo verificar el espacio en disco: {e}") from e

    def validate_path(self) -> None:
        """Verifica que la ruta base es accesible con permisos de escritura.

        Raises:
            StorageError: Si la ruta no existe y no se puede crear, o no tiene
                permisos de escritura.
        """
        try:
            # Intentar crear la ruta base si no existe
            self._base_path.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise StorageError(
                f"Sin permisos para acceder a la ruta '{self._base_path}': {e}"
            ) from e
        except OSError as e:
            raise StorageError(
                f"La ruta '{self._base_path}' no es accesible: {e}"
            ) from e

        if not os.access(self._base_path, os.W_OK):
            raise StorageError(
                f"La ruta '{self._base_path}' no tiene permisos de escritura."
            )
