"""Tests para el módulo resumidor (meeting_recorder/summarizer.py)."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from meeting_recorder.exceptions import ConfigurationError, SummaryError
from meeting_recorder.summarizer import Summarizer, SummaryResult


def _make_mock_openai_response(content: str) -> MagicMock:
    """Crea un mock de respuesta de la API de OpenAI."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def _make_bullet_content(n: int) -> str:
    """Genera contenido Markdown con n viñetas."""
    lines = ["## Resumen de la reunión", ""]
    for i in range(1, n + 1):
        lines.append(f"- Punto {i} de la reunión")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests unitarios
# ---------------------------------------------------------------------------

class TestSummarizerInit:
    def test_valid_api_key_does_not_raise(self):
        s = Summarizer(api_key="sk-test-key")
        assert s._api_key == "sk-test-key"

    def test_empty_api_key_raises_configuration_error(self):
        with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
            Summarizer(api_key="")

    def test_whitespace_api_key_raises_configuration_error(self):
        with pytest.raises(ConfigurationError):
            Summarizer(api_key="   ")

    def test_default_model_is_gpt4o_mini(self):
        s = Summarizer(api_key="sk-test")
        assert s._model == "gpt-4o-mini"

    def test_custom_model_stored(self):
        s = Summarizer(api_key="sk-test", model="gpt-4o")
        assert s._model == "gpt-4o"


class TestSummarizerSummarize:
    def test_saves_md_file_with_timestamp(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        summaries_dir.mkdir()

        content = _make_bullet_content(7)
        mock_response = _make_mock_openai_response(content)

        s = Summarizer(api_key="sk-test")
        with patch("meeting_recorder.summarizer.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            result = s.summarize("Transcripción de prueba", summaries_dir, "2025-01-15_09-30-00")

        assert result.file_path == summaries_dir / "2025-01-15_09-30-00.md"
        assert result.file_path.exists()

    def test_saved_file_is_in_summaries_dir(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        summaries_dir.mkdir()

        content = _make_bullet_content(5)
        mock_response = _make_mock_openai_response(content)

        s = Summarizer(api_key="sk-test")
        with patch("meeting_recorder.summarizer.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            result = s.summarize("Texto", summaries_dir, "2025-01-15_10-00-00")

        assert result.file_path.parent == summaries_dir
        assert result.file_path.suffix == ".md"

    def test_api_error_raises_summary_error(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        summaries_dir.mkdir()

        s = Summarizer(api_key="sk-test")
        with patch("meeting_recorder.summarizer.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("API error")
            mock_openai_cls.return_value = mock_client

            with pytest.raises(SummaryError):
                s.summarize("Texto", summaries_dir, "2025-01-15_10-00-00")

    def test_result_is_summary_result(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        summaries_dir.mkdir()

        content = _make_bullet_content(6)
        mock_response = _make_mock_openai_response(content)

        s = Summarizer(api_key="sk-test")
        with patch("meeting_recorder.summarizer.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            result = s.summarize("Texto", summaries_dir, "2025-01-15_10-00-00")

        assert isinstance(result, SummaryResult)

    def test_content_saved_to_file(self, tmp_path):
        summaries_dir = tmp_path / "summaries"
        summaries_dir.mkdir()

        content = _make_bullet_content(8)
        mock_response = _make_mock_openai_response(content)

        s = Summarizer(api_key="sk-test")
        with patch("meeting_recorder.summarizer.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            result = s.summarize("Texto", summaries_dir, "2025-01-15_10-00-00")

        saved = result.file_path.read_text(encoding="utf-8")
        assert saved == content


# ---------------------------------------------------------------------------
# Tests de propiedad (Hypothesis)
# ---------------------------------------------------------------------------

class TestSummaryBulletCountProperty:
    """Propiedad 7: Resumen contiene entre 5 y 15 viñetas."""

    @settings(max_examples=100)
    @given(st.integers(min_value=5, max_value=15))
    def test_bullet_count_between_5_and_15(self, tmp_path, n_bullets: int):
        """Para cualquier número de viñetas entre 5 y 15, el resumen las contiene."""
        summaries_dir = tmp_path / "summaries"
        summaries_dir.mkdir(exist_ok=True)

        content = _make_bullet_content(n_bullets)
        mock_response = _make_mock_openai_response(content)

        s = Summarizer(api_key="sk-test")
        with patch("meeting_recorder.summarizer.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            result = s.summarize("Texto de prueba", summaries_dir, f"2025-01-15_10-{n_bullets:02d}-00")

        # Contar viñetas en el archivo guardado
        saved_content = result.file_path.read_text(encoding="utf-8")
        bullet_lines = [line for line in saved_content.splitlines() if line.strip().startswith("- ")]
        assert 5 <= len(bullet_lines) <= 15, f"Se esperaban 5-15 viñetas, se encontraron {len(bullet_lines)}"


class TestSummaryLocationProperty:
    """Propiedad 8: Resumen es Markdown válido en directorio correcto."""

    @settings(max_examples=50)
    @given(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65),
            min_size=1,
            max_size=10,
        )
    )
    def test_summary_file_in_summaries_dir_with_md_extension(self, tmp_path, suffix: str):
        """Para cualquier timestamp, el resumen se guarda en summaries/ con extensión .md."""
        summaries_dir = tmp_path / "summaries"
        summaries_dir.mkdir(exist_ok=True)

        content = _make_bullet_content(7)
        mock_response = _make_mock_openai_response(content)
        timestamp = f"2025-01-15_10-00-{suffix[:2].zfill(2)}"

        s = Summarizer(api_key="sk-test")
        with patch("meeting_recorder.summarizer.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            result = s.summarize("Texto", summaries_dir, timestamp)

        assert result.file_path.parent == summaries_dir
        assert result.file_path.suffix == ".md"
        assert result.file_path.exists()
