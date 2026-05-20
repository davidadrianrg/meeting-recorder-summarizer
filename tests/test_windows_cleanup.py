"""Tests para verificar la ausencia de dependencias Windows en el código fuente.

Propiedad 12: Ausencia de rutas Windows en código fuente.
"""

import re
from pathlib import Path

import pytest

# Directorio raíz del proyecto
PROJECT_ROOT = Path(__file__).parent.parent

# Patrones que indican dependencias Windows
WINDOWS_PATTERNS = [
    (r"[A-Za-z]:\\", "Ruta con letra de unidad Windows (ej: C:\\)"),
    (r"\.exe\b", "Referencia a binario .exe"),
    (r"\\\\", "Separador de ruta Windows (doble backslash)"),
    (r"Scripts\\activate", "Ruta de activación de venv Windows"),
    (r"\.venv\\", "Ruta de venv con separador Windows"),
]

# Archivos a excluir del análisis (tests propios, etc.)
EXCLUDED_FILES = {
    "test_windows_cleanup.py",  # Este mismo archivo menciona los patrones
}

# Directorios a excluir
EXCLUDED_DIRS = {".git", "__pycache__", ".kiro", ".venv", "venv"}


def _get_source_files() -> list[Path]:
    """Retorna todos los archivos .py y .sh del proyecto, excluyendo directorios ignorados."""
    files = []
    for pattern in ("**/*.py", "**/*.sh"):
        for f in PROJECT_ROOT.glob(pattern):
            # Excluir directorios ignorados
            if any(excluded in f.parts for excluded in EXCLUDED_DIRS):
                continue
            # Excluir archivos específicos
            if f.name in EXCLUDED_FILES:
                continue
            files.append(f)
    return sorted(files)


class TestNoWindowsDependencies:
    """Propiedad 12: Ausencia de rutas Windows en código fuente."""

    def test_no_windows_drive_letters(self):
        """No debe haber rutas con letras de unidad Windows (C:\\, D:\\, etc.)."""
        violations = []
        for filepath in _get_source_files():
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            for line_num, line in enumerate(content.splitlines(), 1):
                if re.search(r"[A-Za-z]:\\", line):
                    violations.append(f"{filepath.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")

        assert not violations, (
            f"Se encontraron {len(violations)} referencias a rutas Windows:\n"
            + "\n".join(violations[:10])
        )

    def test_no_exe_references_in_python_files(self):
        """No debe haber referencias a binarios .exe en archivos Python."""
        violations = []
        for filepath in _get_source_files():
            if filepath.suffix != ".py":
                continue
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            for line_num, line in enumerate(content.splitlines(), 1):
                if re.search(r"\.exe\b", line) and not line.strip().startswith("#"):
                    violations.append(f"{filepath.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")

        assert not violations, (
            f"Se encontraron {len(violations)} referencias a .exe:\n"
            + "\n".join(violations[:10])
        )

    def test_no_windows_bat_files(self):
        """No debe haber archivos .bat en el proyecto."""
        bat_files = [
            f for f in PROJECT_ROOT.glob("**/*.bat")
            if not any(excluded in f.parts for excluded in EXCLUDED_DIRS)
        ]
        assert not bat_files, (
            f"Se encontraron archivos .bat: {[str(f.relative_to(PROJECT_ROOT)) for f in bat_files]}"
        )

    def test_no_powershell_files(self):
        """No debe haber archivos .ps1 en el proyecto."""
        ps1_files = [
            f for f in PROJECT_ROOT.glob("**/*.ps1")
            if not any(excluded in f.parts for excluded in EXCLUDED_DIRS)
        ]
        assert not ps1_files, (
            f"Se encontraron archivos .ps1: {[str(f.relative_to(PROJECT_ROOT)) for f in ps1_files]}"
        )

    def test_ffmpeg_resolved_via_path(self):
        """ffmpeg debe resolverse via PATH del sistema, no con rutas absolutas."""
        violations = []
        for filepath in _get_source_files():
            if filepath.suffix != ".py":
                continue
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            for line_num, line in enumerate(content.splitlines(), 1):
                # Buscar referencias a ffmpeg con ruta absoluta o .exe
                if re.search(r'["\'].*ffmpeg\.exe["\']', line):
                    violations.append(f"{filepath.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")
                if re.search(r'["\'].*[/\\]bin[/\\]ffmpeg["\']', line):
                    violations.append(f"{filepath.relative_to(PROJECT_ROOT)}:{line_num}: {line.strip()}")

        assert not violations, (
            f"Se encontraron referencias a ffmpeg con ruta absoluta:\n"
            + "\n".join(violations[:10])
        )

    def test_source_files_exist(self):
        """Debe haber al menos algunos archivos Python en el proyecto."""
        py_files = _get_source_files()
        assert len(py_files) > 0, "No se encontraron archivos Python en el proyecto"
