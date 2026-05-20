"""Generación de resúmenes de reuniones usando la API de OpenAI.

Envía la transcripción a gpt-4o-mini y genera un resumen en formato
Markdown con bullet points sobre decisiones, tareas y temas discutidos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from meeting_recorder.exceptions import ConfigurationError, SummaryError

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """\
Eres un asistente especializado en resumir reuniones de trabajo.
A continuación tienes la transcripción de una reunión de Teams.

Genera un resumen en español con entre 5 y 15 viñetas (bullet points) que incluyan:
- Decisiones tomadas durante la reunión
- Tareas asignadas y responsables (si se mencionan)
- Temas principales discutidos
- Próximos pasos o fechas importantes (si se mencionan)

Formato de salida (Markdown):
## Resumen de la reunión

- [viñeta 1]
- [viñeta 2]
...

Transcripción:
{transcription}
"""


@dataclass
class SummaryResult:
    """Resultado de la generación de un resumen.

    Attributes:
        content: Contenido Markdown del resumen.
        file_path: Ruta al archivo .md guardado.
        bullet_count: Número de viñetas en el resumen.
    """

    content: str
    file_path: Path
    bullet_count: int


class Summarizer:
    """Genera resúmenes de reuniones usando la API de OpenAI.

    Args:
        api_key: Clave de API de OpenAI. No puede estar vacía.
        model: Modelo de OpenAI a usar. Por defecto 'gpt-4o-mini'.

    Raises:
        ConfigurationError: Si api_key está vacía o no definida.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        if not api_key or not api_key.strip():
            raise ConfigurationError(
                "OPENAI_API_KEY no está definida o está vacía. "
                "Es necesaria para generar resúmenes."
            )
        self._api_key = api_key
        self._model = model

    def summarize(
        self,
        transcription_text: str,
        output_dir: Path,
        timestamp: str,
    ) -> SummaryResult:
        """Genera un resumen de la transcripción y lo guarda como .md.

        Args:
            transcription_text: Texto de la transcripción a resumir.
            output_dir: Directorio donde se guardará el archivo .md.
            timestamp: Prefijo temporal (YYYY-MM-DD_HH-MM-SS) para el nombre del archivo.

        Returns:
            SummaryResult con el contenido, ruta del archivo y número de viñetas.

        Raises:
            SummaryError: Si la API de OpenAI no responde en 60 segundos o retorna error.
        """
        try:
            from openai import OpenAI
        except ImportError as e:
            raise SummaryError(
                "La librería 'openai' no está instalada. "
                "Ejecuta: uv add openai"
            ) from e

        client = OpenAI(api_key=self._api_key, timeout=60.0)

        prompt = _SUMMARY_PROMPT.format(transcription=transcription_text)

        try:
            logger.info("Generando resumen con modelo '%s'...", self._model)
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as e:
            raise SummaryError(
                f"Error al llamar a la API de OpenAI: {e}"
            ) from e

        content = response.choices[0].message.content or ""
        bullet_count = content.count("\n-")

        output_path = output_dir / f"{timestamp}.md"
        try:
            output_path.write_text(content, encoding="utf-8")
        except OSError as e:
            raise SummaryError(
                f"No se pudo guardar el resumen en '{output_path}': {e}"
            ) from e

        logger.info("Resumen guardado en '%s' (%d viñetas).", output_path, bullet_count)
        return SummaryResult(
            content=content,
            file_path=output_path,
            bullet_count=bullet_count,
        )
