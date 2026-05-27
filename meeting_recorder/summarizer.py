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
Eres un asistente experto en análisis de reuniones de trabajo. Tu tarea es generar un resumen estructurado y accionable a partir de la transcripción de una reunión.

Analiza la transcripción y genera un resumen en español con las siguientes secciones (omite las secciones que no apliquen):

## Resumen de la reunión

### Contexto
Describe brevemente el propósito de la reunión y los participantes mencionados (si se identifican).

### Decisiones tomadas
- Lista las decisiones concretas que se acordaron durante la reunión.

### Tareas y compromisos
- Lista las tareas asignadas, indicando el responsable si se menciona, y la fecha límite si se establece.
- Formato: [Responsable (si se conoce)] — Tarea — [Fecha límite (si se menciona)]

### Puntos clave discutidos
- Resume los temas principales que se trataron, priorizando los más relevantes.

### Próximos pasos
- Indica las acciones inmediatas o la fecha de la próxima reunión si se menciona.

### Dudas o puntos pendientes
- Lista cualquier tema que quedó sin resolver o que requiere seguimiento.

Reglas:
- Genera entre 5 y 20 viñetas en total entre todas las secciones.
- Sé conciso pero específico. Evita generalidades vagas.
- Si la transcripción tiene errores de reconocimiento de voz, interpreta el contexto para corregirlos.
- Si no puedes identificar participantes, omite los nombres y enfócate en el contenido.
- Usa lenguaje profesional y directo.

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

    def __init__(self, api_key: str, model: str = "gpt-5.4-nano") -> None:
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
