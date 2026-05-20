"""Tests para el módulo de configuración (meeting_recorder/config.py)."""

import os
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from meeting_recorder.config import AppConfig, VALID_MODELS


# ---------------------------------------------------------------------------
# Tests unitarios
# ---------------------------------------------------------------------------

class TestAppConfigDefaults:
    def test_default_whisper_model(self):
        config = AppConfig()
        assert config.whisper_model == "base"

    def test_default_enable_cuda_false(self):
        config = AppConfig()
        assert config.enable_cuda is False

    def test_default_openai_api_key_empty(self):
        config = AppConfig()
        assert config.openai_api_key == ""

    def test_default_storage_path_in_home(self):
        config = AppConfig()
        assert "meeting-recorder-data" in str(config.storage_path)


class TestAppConfigFromEnv:
    def test_reads_openai_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        config = AppConfig.from_env()
        assert config.openai_api_key == "sk-test-key"

    def test_reads_whisper_model(self, monkeypatch):
        monkeypatch.setenv("WHISPER_MODEL", "small")
        config = AppConfig.from_env()
        assert config.whisper_model == "small"

    def test_reads_enable_cuda_true(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CUDA", "true")
        config = AppConfig.from_env()
        assert config.enable_cuda is True

    def test_reads_enable_cuda_false(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CUDA", "false")
        config = AppConfig.from_env()
        assert config.enable_cuda is False

    def test_reads_storage_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
        config = AppConfig.from_env()
        assert config.storage_path == tmp_path

    def test_reads_meeting_recorder_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("STORAGE_PATH", raising=False)
        monkeypatch.setenv("MEETING_RECORDER_DATA_DIR", str(tmp_path))
        config = AppConfig.from_env()
        assert config.storage_path == tmp_path

    def test_storage_path_takes_precedence_over_data_dir(self, monkeypatch, tmp_path):
        path_a = tmp_path / "a"
        path_b = tmp_path / "b"
        monkeypatch.setenv("STORAGE_PATH", str(path_a))
        monkeypatch.setenv("MEETING_RECORDER_DATA_DIR", str(path_b))
        config = AppConfig.from_env()
        assert config.storage_path == path_a

    def test_defaults_when_env_not_set(self, monkeypatch):
        for var in ("OPENAI_API_KEY", "WHISPER_MODEL", "ENABLE_CUDA", "STORAGE_PATH", "MEETING_RECORDER_DATA_DIR"):
            monkeypatch.delenv(var, raising=False)
        config = AppConfig.from_env()
        assert config.openai_api_key == ""
        assert config.whisper_model == "base"
        assert config.enable_cuda is False


class TestAppConfigValidate:
    def test_valid_config_returns_no_errors(self):
        config = AppConfig(openai_api_key="sk-test", whisper_model="base")
        assert config.validate() == []

    def test_empty_api_key_returns_error(self):
        config = AppConfig(openai_api_key="", whisper_model="base")
        errors = config.validate()
        assert len(errors) == 1
        assert "OPENAI_API_KEY" in errors[0]

    def test_whitespace_api_key_returns_error(self):
        config = AppConfig(openai_api_key="   ", whisper_model="base")
        errors = config.validate()
        assert any("OPENAI_API_KEY" in e for e in errors)

    def test_invalid_model_returns_error(self):
        config = AppConfig(openai_api_key="sk-test", whisper_model="invalid-model")
        errors = config.validate()
        assert len(errors) == 1
        assert "invalid-model" in errors[0]

    def test_invalid_model_error_lists_valid_models(self):
        config = AppConfig(openai_api_key="sk-test", whisper_model="gpt4")
        errors = config.validate()
        assert any(model in errors[0] for model in VALID_MODELS)

    def test_both_errors_returned_together(self):
        config = AppConfig(openai_api_key="", whisper_model="bad-model")
        errors = config.validate()
        assert len(errors) == 2

    @pytest.mark.parametrize("model", VALID_MODELS)
    def test_all_valid_models_pass(self, model):
        config = AppConfig(openai_api_key="sk-test", whisper_model=model)
        errors = config.validate()
        assert not any("modelo" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Tests de propiedad (Hypothesis)
# ---------------------------------------------------------------------------

class TestModelValidationProperty:
    """Propiedad 5: Validación de nombre de modelo."""

    @settings(max_examples=200)
    @given(st.text())
    def test_only_valid_models_accepted(self, model_name: str):
        """Para cualquier cadena, validate() solo acepta modelos en VALID_MODELS."""
        config = AppConfig(openai_api_key="sk-test", whisper_model=model_name)
        errors = config.validate()
        model_errors = [e for e in errors if "modelo" in e.lower() or "model" in e.lower() or model_name in e]

        if model_name in VALID_MODELS:
            assert not model_errors, f"Modelo válido '{model_name}' fue rechazado"
        else:
            assert model_errors, f"Modelo inválido '{model_name}' fue aceptado"
