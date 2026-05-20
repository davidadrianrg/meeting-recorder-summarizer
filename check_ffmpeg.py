"""Verifica la disponibilidad y capacidades de ffmpeg en el sistema.

Uso: python check_ffmpeg.py
"""

import shutil
import subprocess


def check_ffmpeg(path: str) -> dict | None:
    """Verifica si ffmpeg está disponible y sus capacidades.

    Args:
        path: Ruta o nombre del binario ffmpeg.

    Returns:
        Diccionario con version, nvenc y av1, o None si no está disponible.
    """
    if not shutil.which(path):
        return None

    try:
        v_out = subprocess.check_output(
            [path, "-version"], stderr=subprocess.STDOUT, text=True
        ).split("\n")[0]

        encoders = subprocess.check_output(
            [path, "-encoders"], stderr=subprocess.STDOUT, text=True
        )
        has_nvenc = "nvenc" in encoders

        decoders = subprocess.check_output(
            [path, "-decoders"], stderr=subprocess.STDOUT, text=True
        )
        has_av1 = "av1" in decoders

        return {
            "version": v_out,
            "nvenc": has_nvenc,
            "av1": has_av1,
        }
    except Exception:
        return None


if __name__ == "__main__":
    info = check_ffmpeg("ffmpeg")
    if info:
        print(f"ffmpeg encontrado en PATH")
        print(f"  Versión : {info['version']}")
        print(f"  NVENC   : {'Sí' if info['nvenc'] else 'No'}")
        print(f"  AV1     : {'Sí' if info['av1'] else 'No'}")
    else:
        print("ffmpeg no está disponible en el PATH del sistema.")
        print("En Fedora Silverblue, instálalo con: sudo rpm-ostree install ffmpeg")
        print("O usa el contenedor Podman que ya incluye ffmpeg.")
