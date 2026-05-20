"""Tests para el módulo transcriptor (meeting_recorder/transcriber.py)."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from meeting_recorder.config import VALID_MODELS
from meeting_recorder.exceptions import InvalidModelError, TranscriptionError
from meeting_recorder.transcriber import Transcriber, TranscriptionResult


# ---------------------------------------------------------------------------
# Tests unitarios
# ---------------------------------------------------------------------------

class TestTranscriberInit:
    def test_valid_model_does_not_raise(self):
        t = Transcriber(model_name="base")
        assert t._model_name == "base"

    @pytest.mark.parametrize("model", VALID_MODELS)
    def test_all_valid_models_accepted(self, model):
        t = Transcriber(model_name=model)
        assert t._model_name == model

    def test_invalid_model_raises_invalid_model_error(self):
        with pytest.raises(InvalidModelError, match="gpt4"):
            Transcriber(model_name="gpt4")

    def test_empty_model_raises_invalid_model_error(self):
        with pytest.raises(InvalidModelError):
            Transcriber(model_name="")

    def test_cuda_flag_stored(self):
        t = Transcriber(model_name="base", use_cuda=True)
        assert t._use_cuda is True

    def test_default_cuda_is_false(self):
        t = Transcriber(model_name="base")
        assert t._use_cuda is False


class TestTranscriberTranscribe:
    def _make_wav(self, tmp_path: Path, name: str = "2025-01-15_09-30-00.wav") -> Path:
        """Crea un archivo WAV mínimo válido para tests."""
        wav_path = tmp_path / name
        # Cabecera WAV mínima (44 bytes) + datos vacíos
        import struct
        data_size = 0
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + data_size, b"WAVE",
            b"fmt ", 16, 1, 1, 16000, 32000, 2, 16,
            b"data", data_size,
        )
        wav_path.write_bytes(header)
        return wav_path

    def test_transcribe_nonexistent_file_raises(self, tmp_path):
        t = Transcriber(model_name="base")
        with pytest.raises(TranscriptionError, match="no existe"):
            t.transcribe(tmp_path / "nonexistent.wav", tmp_path)

    def test_transcribe_saves_txt_with_same_stem(self, tmp_path):
        wav = self._make_wav(tmp_path, "2025-01-15_09-30-00.wav")
        output_dir = tmp_path / "transcriptions"
        output_dir.mkdir()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "Hola mundo", "language": "es"}

        t = Transcriber(model_name="base")
        t._model = mock_model

        result = t.transcribe(wav, output_dir)

        assert result.file_path == output_dir / "2025-01-15_09-30-00.txt"
        assert result.file_path.exists()

    def test_transcribe_saves_utf8_content(self, tmp_path):
        wav = self._make_wav(tmp_path)
        output_dir = tmp_path / "transcriptions"
        output_dir.mkdir()

        text = "Reunión con José María: decisión sobre el presupuesto 2025 🎯"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": text, "language": "es"}

        t = Transcriber(model_name="base")
        t._model = mock_model

        result = t.transcribe(wav, output_dir)

        saved = result.file_path.read_text(encoding="utf-8")
        assert saved == text

    def test_transcribe_returns_language_detected(self, tmp_path):
        wav = self._make_wav(tmp_path)
        output_dir = tmp_path / "transcriptions"
        output_dir.mkdir()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "Hello", "language": "en"}

        t = Transcriber(model_name="base")
        t._model = mock_model

        result = t.transcribe(wav, output_dir)
        assert result.language_detected == "en"

    def test_transcribe_model_error_raises_transcription_error(self, tmp_path):
        wav = self._make_wav(tmp_path)
        output_dir = tmp_path / "transcriptions"
        output_dir.mkdir()

        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("CUDA out of memory")

        t = Transcriber(model_name="base")
        t._model = mock_model

        with pytest.raises(TranscriptionError):
            t.transcribe(wav, output_dir)

    def test_transcribe_result_is_transcription_result(self, tmp_path):
        wav = self._make_wav(tmp_path)
        output_dir = tmp_path / "transcriptions"
        output_dir.mkdir()

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "Test", "language": "es"}

        t = Transcriber(model_name="base")
        t._model = mock_model

        result = t.transcribe(wav, output_dir)
        assert isinstance(result, TranscriptionResult)


# ---------------------------------------------------------------------------
# Tests de propiedad (Hypothesis)
# ---------------------------------------------------------------------------

class TestTranscriptionUTF8Property:
    """Propiedad 6: Transcripción produce UTF-8 válido."""

    @settings(max_examples=100)
    @given(st.text(min_size=0, max_size=5000))
    def test_any_text_saved_as_valid_utf8(self, tmp_path, text: str):
        """Para cualquier texto (incluyendo Unicode, acentos, emojis), el archivo de salida es UTF-8 válido."""
        import struct

        # Crear WAV mínimo
        wav_path = tmp_path / "test.wav"
        data_size = 0
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + data_size, b"WAVE",
            b"fmt ", 16, 1, 1, 16000, 32000, 2, 16,
            b"data", data_size,
        )
        wav_path.write_bytes(header)

        output_dir = tmp_path / "transcriptions"
        output_dir.mkdir(exist_ok=True)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": text, "language": "es"}

        t = Transcriber(model_name="base")
        t._model = mock_model

        result = t.transcribe(wav_path, output_dir)

        # El archivo debe existir y ser UTF-8 válido
        assert result.file_path.exists()
        content = result.file_path.read_bytes()
        decoded = content.decode("utf-8")  # No debe lanzar UnicodeDecodeError
        assert decoded == text.strip()

        # El archivo debe estar en el directorio transcriptions/
        assert result.file_path.parent == output_dir
