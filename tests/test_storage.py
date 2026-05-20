"""Tests para el módulo de almacenamiento (meeting_recorder/storage.py)."""

import os
import re
from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import datetimes

from meeting_recorder.exceptions import DiskSpaceError, StorageError
from meeting_recorder.storage import StorageManager


# ---------------------------------------------------------------------------
# Tests unitarios
# ---------------------------------------------------------------------------

class TestStorageManagerDirectories:
    def test_creates_recordings_dir(self, tmp_path):
        sm = StorageManager(tmp_path)
        sm.ensure_directories()
        assert (tmp_path / "recordings").is_dir()

    def test_creates_transcriptions_dir(self, tmp_path):
        sm = StorageManager(tmp_path)
        sm.ensure_directories()
        assert (tmp_path / "transcriptions").is_dir()

    def test_creates_summaries_dir(self, tmp_path):
        sm = StorageManager(tmp_path)
        sm.ensure_directories()
        assert (tmp_path / "summaries").is_dir()

    def test_idempotent_when_dirs_exist(self, tmp_path):
        sm = StorageManager(tmp_path)
        sm.ensure_directories()
        sm.ensure_directories()  # Segunda llamada no debe fallar
        assert (tmp_path / "recordings").is_dir()

    def test_recordings_dir_property(self, tmp_path):
        sm = StorageManager(tmp_path)
        assert sm.recordings_dir == tmp_path / "recordings"

    def test_transcriptions_dir_property(self, tmp_path):
        sm = StorageManager(tmp_path)
        assert sm.transcriptions_dir == tmp_path / "transcriptions"

    def test_summaries_dir_property(self, tmp_path):
        sm = StorageManager(tmp_path)
        assert sm.summaries_dir == tmp_path / "summaries"

    def test_dirs_are_writable(self, tmp_path):
        sm = StorageManager(tmp_path)
        sm.ensure_directories()
        for d in (sm.recordings_dir, sm.transcriptions_dir, sm.summaries_dir):
            assert os.access(d, os.W_OK)

    def test_dirs_are_readable(self, tmp_path):
        sm = StorageManager(tmp_path)
        sm.ensure_directories()
        for d in (sm.recordings_dir, sm.transcriptions_dir, sm.summaries_dir):
            assert os.access(d, os.R_OK)


class TestStorageManagerTimestamp:
    def test_timestamp_format(self, tmp_path):
        sm = StorageManager(tmp_path)
        ts = sm.generate_timestamp()
        pattern = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$"
        assert re.match(pattern, ts), f"Timestamp '{ts}' no coincide con YYYY-MM-DD_HH-MM-SS"

    def test_timestamp_is_parseable(self, tmp_path):
        sm = StorageManager(tmp_path)
        ts = sm.generate_timestamp()
        # Debe poder parsearse de vuelta a datetime
        dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
        assert isinstance(dt, datetime)

    def test_two_timestamps_are_different_or_equal(self, tmp_path):
        """Dos timestamps generados en el mismo segundo son iguales; en segundos distintos, distintos."""
        sm = StorageManager(tmp_path)
        ts1 = sm.generate_timestamp()
        ts2 = sm.generate_timestamp()
        # Ambos deben tener el formato correcto
        pattern = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$"
        assert re.match(pattern, ts1)
        assert re.match(pattern, ts2)


class TestStorageManagerDiskSpace:
    def test_sufficient_space_returns_true(self, tmp_path):
        sm = StorageManager(tmp_path)
        # 1 MB mínimo — casi siempre habrá más espacio disponible
        result = sm.check_disk_space(min_mb=1)
        assert result is True

    def test_excessive_min_mb_raises_disk_space_error(self, tmp_path):
        sm = StorageManager(tmp_path)
        # Pedir 999 TB — siempre fallará
        with pytest.raises(DiskSpaceError):
            sm.check_disk_space(min_mb=999_000_000)

    def test_disk_space_error_message_contains_available_mb(self, tmp_path):
        sm = StorageManager(tmp_path)
        with pytest.raises(DiskSpaceError, match="MB"):
            sm.check_disk_space(min_mb=999_000_000)


class TestStorageManagerValidatePath:
    def test_valid_path_does_not_raise(self, tmp_path):
        sm = StorageManager(tmp_path)
        sm.validate_path()  # No debe lanzar excepción

    def test_creates_path_if_not_exists(self, tmp_path):
        new_path = tmp_path / "new" / "nested" / "dir"
        sm = StorageManager(new_path)
        sm.validate_path()
        assert new_path.is_dir()


# ---------------------------------------------------------------------------
# Tests de propiedad (Hypothesis)
# ---------------------------------------------------------------------------

class TestTimestampConsistencyProperty:
    """Propiedad 3: Consistencia de nombres temporales entre artefactos."""

    @settings(max_examples=200)
    @given(datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2099, 12, 31)))
    def test_timestamp_matches_pattern(self, dt: datetime):
        """Para cualquier datetime, el formato YYYY-MM-DD_HH-MM-SS es válido y parseable."""
        ts = dt.strftime("%Y-%m-%d_%H-%M-%S")
        pattern = r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$"
        assert re.match(pattern, ts), f"Timestamp '{ts}' no coincide con el patrón"
        # Debe ser reversible
        parsed = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
        assert parsed.year == dt.year
        assert parsed.month == dt.month
        assert parsed.day == dt.day
        assert parsed.hour == dt.hour
        assert parsed.minute == dt.minute
        assert parsed.second == dt.second


class TestDirectoryCreationProperty:
    """Propiedad 9: Creación de estructura de directorios."""

    @settings(max_examples=20)
    @given(st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65), min_size=1, max_size=20))
    def test_ensure_directories_creates_exactly_three_subdirs(self, tmp_path, suffix: str):
        """Para cualquier ruta base válida, ensure_directories crea exactamente recordings/, transcriptions/, summaries/."""
        base = tmp_path / f"data_{suffix}"
        sm = StorageManager(base)
        sm.ensure_directories()

        expected = {"recordings", "transcriptions", "summaries"}
        actual = {d.name for d in base.iterdir() if d.is_dir()}
        assert actual == expected, f"Directorios creados: {actual}, esperados: {expected}"

        # Todos deben ser escribibles y legibles
        for d in base.iterdir():
            if d.is_dir():
                assert os.access(d, os.W_OK | os.R_OK)
