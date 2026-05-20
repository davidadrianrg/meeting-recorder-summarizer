"""Tests para el servicio principal (meeting_recorder/service.py)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from meeting_recorder.config import AppConfig
from meeting_recorder.exceptions import PipeWireConnectionError
from meeting_recorder.recorder import RecordingResult
from meeting_recorder.service import RecorderService, RecordingState, ServiceResponse
from meeting_recorder.storage import StorageManager


def _make_service(tmp_path: Path) -> RecorderService:
    """Crea un RecorderService con storage real y config mínima."""
    config = AppConfig(
        openai_api_key="sk-test",
        whisper_model="base",
        enable_cuda=False,
        storage_path=tmp_path,
    )
    storage = StorageManager(tmp_path)
    storage.ensure_directories()
    return RecorderService(storage, config)


# ---------------------------------------------------------------------------
# Tests unitarios
# ---------------------------------------------------------------------------

class TestServiceToggle:
    def test_initial_state_is_idle(self, tmp_path):
        service = _make_service(tmp_path)
        assert service.status() == RecordingState.IDLE

    def test_toggle_from_idle_starts_recording(self, tmp_path):
        service = _make_service(tmp_path)

        mock_recorder = MagicMock()
        mock_recorder._current_timestamp = "2025-01-15_09-30-00"
        service._recorder = mock_recorder

        response = service.toggle()

        assert response.status == "recording_started"
        assert service.status() == RecordingState.RECORDING
        mock_recorder.start.assert_called_once()

    def test_toggle_from_recording_stops_recording(self, tmp_path):
        service = _make_service(tmp_path)

        # Poner en estado RECORDING
        mock_recorder = MagicMock()
        mock_recorder._current_timestamp = "2025-01-15_09-30-00"
        mock_recorder.stop.return_value = RecordingResult(
            file_path=tmp_path / "recordings" / "2025-01-15_09-30-00.wav",
            duration_seconds=60.0,
            sources_captured=["microphone", "monitor"],
        )
        service._recorder = mock_recorder
        service._state = RecordingState.RECORDING

        response = service.toggle()

        assert response.status == "recording_stopped"
        assert service.status() == RecordingState.IDLE
        mock_recorder.stop.assert_called_once()

    def test_pipewire_error_returns_error_response(self, tmp_path):
        service = _make_service(tmp_path)

        mock_recorder = MagicMock()
        mock_recorder.start.side_effect = PipeWireConnectionError("PipeWire no disponible")
        service._recorder = mock_recorder

        response = service.toggle()

        assert response.status == "error"
        assert "PipeWire" in response.message
        assert service.status() == RecordingState.IDLE

    def test_state_returns_to_idle_after_error(self, tmp_path):
        service = _make_service(tmp_path)

        mock_recorder = MagicMock()
        mock_recorder.start.side_effect = PipeWireConnectionError("Error")
        service._recorder = mock_recorder

        service.toggle()
        assert service.status() == RecordingState.IDLE


class TestServiceResponse:
    def test_response_to_json_contains_status(self):
        r = ServiceResponse(status="recording_started", message="OK")
        data = json.loads(r.to_json())
        assert data["status"] == "recording_started"

    def test_response_to_json_contains_message(self):
        r = ServiceResponse(status="recording_started", message="Grabación iniciada")
        data = json.loads(r.to_json())
        assert data["message"] == "Grabación iniciada"

    def test_response_to_json_excludes_none_fields(self):
        r = ServiceResponse(status="recording_started", message="OK")
        data = json.loads(r.to_json())
        assert "timestamp" not in data
        assert "file" not in data

    def test_response_to_json_includes_timestamp_when_set(self):
        r = ServiceResponse(
            status="recording_started",
            message="OK",
            timestamp="2025-01-15_09-30-00",
        )
        data = json.loads(r.to_json())
        assert data["timestamp"] == "2025-01-15_09-30-00"

    def test_response_to_json_is_valid_json(self):
        r = ServiceResponse(status="error", message="Algo falló")
        json_str = r.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_response_to_json_is_single_line(self):
        r = ServiceResponse(status="recording_stopped", message="OK", file="test.wav")
        json_str = r.to_json()
        assert "\n" not in json_str


class TestServiceStatus:
    def test_status_response_contains_state(self, tmp_path):
        service = _make_service(tmp_path)
        response = service.status_response()
        assert response.status == "status"
        assert "idle" in response.message.lower()

    def test_status_response_after_toggle_shows_recording(self, tmp_path):
        service = _make_service(tmp_path)

        mock_recorder = MagicMock()
        mock_recorder._current_timestamp = "2025-01-15_09-30-00"
        service._recorder = mock_recorder

        service.toggle()
        response = service.status_response()
        assert "recording" in response.message.lower()


# ---------------------------------------------------------------------------
# Tests de propiedad (Hypothesis)
# ---------------------------------------------------------------------------

class TestToggleStateAlternationProperty:
    """Propiedad 4: Alternancia de estado de grabación."""

    @settings(max_examples=100)
    @given(st.integers(min_value=1, max_value=50))
    def test_state_alternates_correctly(self, tmp_path, n_toggles: int):
        """Para N toggles desde IDLE, el estado final es RECORDING si N es impar, IDLE si N es par."""
        service = _make_service(tmp_path)

        # Mock del grabador para evitar PipeWire real
        mock_recorder = MagicMock()
        mock_recorder._current_timestamp = "2025-01-15_09-30-00"
        mock_recorder.stop.return_value = RecordingResult(
            file_path=tmp_path / "recordings" / "2025-01-15_09-30-00.wav",
            duration_seconds=1.0,
            sources_captured=["microphone"],
        )
        service._recorder = mock_recorder

        # Deshabilitar el pipeline para no necesitar OpenAI
        with patch.object(service, "_launch_pipeline"):
            for _ in range(n_toggles):
                service.toggle()

        expected_state = RecordingState.RECORDING if n_toggles % 2 == 1 else RecordingState.IDLE
        assert service.status() == expected_state, \
            f"Después de {n_toggles} toggles, se esperaba {expected_state.value}, " \
            f"se obtuvo {service.status().value}"
