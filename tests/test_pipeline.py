"""Tests para el módulo pipeline (meeting_recorder/pipeline.py)."""

import asyncio
import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from meeting_recorder.exceptions import PipelineTimeoutError, TranscriptionError
from meeting_recorder.pipeline import ProcessingPipeline
from meeting_recorder.summarizer import SummaryResult
from meeting_recorder.transcriber import TranscriptionResult


def _make_wav(path: Path) -> Path:
    """Crea un archivo WAV mínimo válido."""
    data_size = 0
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, 1, 16000, 32000, 2, 16,
        b"data", data_size,
    )
    path.write_bytes(header)
    return path


def _make_pipeline(tmp_path: Path, transcription_text: str = "Texto de prueba") -> tuple:
    """Crea un pipeline con mocks de transcriptor y resumidor."""
    # Estructura de directorios
    recordings_dir = tmp_path / "recordings"
    transcriptions_dir = tmp_path / "transcriptions"
    summaries_dir = tmp_path / "summaries"
    for d in (recordings_dir, transcriptions_dir, summaries_dir):
        d.mkdir(parents=True, exist_ok=True)

    audio_path = recordings_dir / "2025-01-15_09-30-00.wav"
    _make_wav(audio_path)

    txt_path = transcriptions_dir / "2025-01-15_09-30-00.txt"
    txt_path.write_text(transcription_text, encoding="utf-8")

    md_path = summaries_dir / "2025-01-15_09-30-00.md"

    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = TranscriptionResult(
        text=transcription_text,
        file_path=txt_path,
        language_detected="es",
    )

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = SummaryResult(
        content="## Resumen\n\n- Punto 1\n- Punto 2",
        file_path=md_path,
        bullet_count=2,
    )

    pipeline = ProcessingPipeline(mock_transcriber, mock_summarizer)
    return pipeline, audio_path, mock_transcriber, mock_summarizer


# ---------------------------------------------------------------------------
# Tests unitarios
# ---------------------------------------------------------------------------

class TestPipelineSequentialExecution:
    def test_transcription_called_before_summary(self, tmp_path):
        """La transcripción debe completarse antes de llamar al resumidor."""
        call_order = []

        pipeline, audio_path, mock_transcriber, mock_summarizer = _make_pipeline(tmp_path)

        original_transcribe = mock_transcriber.transcribe
        original_summarize = mock_summarizer.summarize

        def track_transcribe(*args, **kwargs):
            call_order.append("transcribe")
            return original_transcribe(*args, **kwargs)

        def track_summarize(*args, **kwargs):
            call_order.append("summarize")
            return original_summarize(*args, **kwargs)

        mock_transcriber.transcribe = track_transcribe
        mock_summarizer.summarize = track_summarize

        asyncio.run(pipeline.process(audio_path))

        assert call_order == ["transcribe", "summarize"], \
            f"Orden incorrecto: {call_order}"

    def test_summary_receives_transcription_text(self, tmp_path):
        """El resumidor debe recibir el texto producido por el transcriptor."""
        pipeline, audio_path, mock_transcriber, mock_summarizer = _make_pipeline(
            tmp_path, transcription_text="Texto específico de la reunión"
        )

        asyncio.run(pipeline.process(audio_path))

        call_args = mock_summarizer.summarize.call_args
        assert call_args is not None
        # El primer argumento posicional es el texto de transcripción
        assert "Texto específico de la reunión" in call_args[0]

    def test_transcription_failure_skips_summary(self, tmp_path):
        """Si la transcripción falla, no se debe llamar al resumidor."""
        pipeline, audio_path, mock_transcriber, mock_summarizer = _make_pipeline(tmp_path)
        mock_transcriber.transcribe.side_effect = TranscriptionError("Fallo de prueba")

        asyncio.run(pipeline.process(audio_path))

        mock_summarizer.summarize.assert_not_called()

    def test_active_count_zero_when_idle(self, tmp_path):
        pipeline, _, _, _ = _make_pipeline(tmp_path)
        assert pipeline.active_count() == 0

    def test_active_count_increments_during_processing(self, tmp_path):
        """active_count debe ser > 0 mientras se procesa."""
        counts_during = []

        pipeline, audio_path, mock_transcriber, mock_summarizer = _make_pipeline(tmp_path)

        original_transcribe = mock_transcriber.transcribe

        def slow_transcribe(*args, **kwargs):
            counts_during.append(pipeline.active_count())
            return original_transcribe(*args, **kwargs)

        mock_transcriber.transcribe = slow_transcribe

        asyncio.run(pipeline.process(audio_path))

        assert any(c > 0 for c in counts_during), "active_count nunca fue > 0 durante el procesamiento"

    def test_active_count_returns_to_zero_after_processing(self, tmp_path):
        pipeline, audio_path, _, _ = _make_pipeline(tmp_path)
        asyncio.run(pipeline.process(audio_path))
        assert pipeline.active_count() == 0


class TestPipelineConcurrency:
    def test_max_concurrent_pipelines(self, tmp_path):
        """No deben ejecutarse más de 3 pipelines simultáneamente."""
        max_concurrent_seen = []
        current_concurrent = [0]

        def make_slow_transcribe(pipeline):
            def slow_transcribe(*args, **kwargs):
                current_concurrent[0] += 1
                max_concurrent_seen.append(current_concurrent[0])
                import time; time.sleep(0.01)
                current_concurrent[0] -= 1
                return TranscriptionResult(
                    text="texto",
                    file_path=args[1] / f"{args[0].stem}.txt",
                    language_detected="es",
                )
            return slow_transcribe

        # Crear 5 archivos de audio
        recordings_dir = tmp_path / "recordings"
        transcriptions_dir = tmp_path / "transcriptions"
        summaries_dir = tmp_path / "summaries"
        for d in (recordings_dir, transcriptions_dir, summaries_dir):
            d.mkdir(parents=True, exist_ok=True)

        audio_files = []
        for i in range(5):
            p = recordings_dir / f"2025-01-15_09-{i:02d}-00.wav"
            _make_wav(p)
            audio_files.append(p)

        mock_transcriber = MagicMock()
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = SummaryResult(
            content="## Resumen\n\n- Punto",
            file_path=summaries_dir / "test.md",
            bullet_count=1,
        )

        pipeline = ProcessingPipeline(mock_transcriber, mock_summarizer)
        mock_transcriber.transcribe = make_slow_transcribe(pipeline)

        async def run_all():
            tasks = [pipeline.process(f) for f in audio_files]
            await asyncio.gather(*tasks)

        asyncio.run(run_all())

        assert max(max_concurrent_seen) <= 3, \
            f"Se ejecutaron {max(max_concurrent_seen)} pipelines simultáneos (máximo: 3)"


class TestPipelineTimeout:
    def test_timeout_raises_pipeline_timeout_error(self, tmp_path):
        """Un paso que excede 120s debe lanzar PipelineTimeoutError."""
        recordings_dir = tmp_path / "recordings"
        transcriptions_dir = tmp_path / "transcriptions"
        summaries_dir = tmp_path / "summaries"
        for d in (recordings_dir, transcriptions_dir, summaries_dir):
            d.mkdir(parents=True, exist_ok=True)

        audio_path = recordings_dir / "2025-01-15_09-30-00.wav"
        _make_wav(audio_path)

        mock_transcriber = MagicMock()
        mock_summarizer = MagicMock()

        pipeline = ProcessingPipeline(mock_transcriber, mock_summarizer)

        # Parchear el timeout a 0.01s para que el test sea rápido
        import meeting_recorder.pipeline as pipeline_module
        original_timeout = pipeline_module._STEP_TIMEOUT_SECONDS

        async def run():
            pipeline_module._STEP_TIMEOUT_SECONDS = 0.01
            try:
                # Hacer que transcribe tarde más que el timeout
                async def slow_transcribe():
                    await asyncio.sleep(1)
                    return None

                with patch.object(
                    asyncio,
                    "wait_for",
                    side_effect=asyncio.TimeoutError,
                ):
                    with pytest.raises(PipelineTimeoutError):
                        await pipeline._run_pipeline(audio_path)
            finally:
                pipeline_module._STEP_TIMEOUT_SECONDS = original_timeout

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Tests de propiedad (Hypothesis)
# ---------------------------------------------------------------------------

class TestPipelineSequentialProperty:
    """Propiedad 10: Ejecución secuencial del pipeline."""

    @settings(max_examples=30)
    @given(st.text(min_size=1, max_size=500))
    def test_summary_always_receives_transcription_output(self, tmp_path, transcription_text: str):
        """Para cualquier texto de transcripción, el resumidor recibe exactamente ese texto."""
        pipeline, audio_path, mock_transcriber, mock_summarizer = _make_pipeline(
            tmp_path, transcription_text=transcription_text
        )

        asyncio.run(pipeline.process(audio_path))

        if mock_summarizer.summarize.called:
            call_args = mock_summarizer.summarize.call_args[0]
            assert call_args[0] == transcription_text


class TestPipelineConcurrencyProperty:
    """Propiedad 11: Límite de pipelines concurrentes."""

    @settings(max_examples=10)
    @given(st.integers(min_value=1, max_value=10))
    def test_never_exceeds_max_concurrent(self, tmp_path, n_requests: int):
        """Para cualquier número de solicitudes, nunca hay más de 3 pipelines simultáneos."""
        max_seen = [0]
        current = [0]

        recordings_dir = tmp_path / "recordings"
        transcriptions_dir = tmp_path / "transcriptions"
        summaries_dir = tmp_path / "summaries"
        for d in (recordings_dir, transcriptions_dir, summaries_dir):
            d.mkdir(parents=True, exist_ok=True)

        audio_files = []
        for i in range(n_requests):
            p = recordings_dir / f"2025-01-15_09-{i:02d}-00.wav"
            _make_wav(p)
            audio_files.append(p)

        def counting_transcribe(*args, **kwargs):
            current[0] += 1
            max_seen[0] = max(max_seen[0], current[0])
            result = TranscriptionResult(
                text="texto",
                file_path=args[1] / f"{args[0].stem}.txt",
                language_detected="es",
            )
            current[0] -= 1
            return result

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe = counting_transcribe
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = SummaryResult(
            content="## Resumen\n\n- Punto",
            file_path=summaries_dir / "test.md",
            bullet_count=1,
        )

        pipeline = ProcessingPipeline(mock_transcriber, mock_summarizer)

        async def run_all():
            tasks = [pipeline.process(f) for f in audio_files]
            await asyncio.gather(*tasks)

        asyncio.run(run_all())

        assert max_seen[0] <= 3, \
            f"Se ejecutaron {max_seen[0]} pipelines simultáneos con {n_requests} solicitudes"
