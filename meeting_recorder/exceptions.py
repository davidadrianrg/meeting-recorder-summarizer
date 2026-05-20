"""Jerarquía de excepciones del sistema Meeting Recorder.

Define excepciones personalizadas para cada componente del sistema,
permitiendo manejo granular de errores en grabación, transcripción,
resumen, almacenamiento y pipeline.
"""


class MeetingRecorderError(Exception):
    """Error base del sistema Meeting Recorder.

    Todas las excepciones del sistema heredan de esta clase,
    permitiendo capturar cualquier error del sistema con un único except.
    """

    pass


class PipeWireConnectionError(MeetingRecorderError):
    """No se puede conectar a PipeWire.

    Se lanza cuando el socket de PipeWire no está disponible o la conexión
    falla antes de iniciar la grabación.
    """

    pass


class RecordingError(MeetingRecorderError):
    """Error durante la grabación de audio.

    Se lanza cuando ocurre un fallo en el proceso de captura de audio
    que no está relacionado con la conexión a PipeWire.
    """

    pass


class TranscriptionError(MeetingRecorderError):
    """Error durante la transcripción de audio.

    Se lanza cuando el modelo de Whisper falla al transcribir,
    el archivo de audio no existe o no es legible.
    """

    pass


class InvalidModelError(TranscriptionError):
    """Modelo de Whisper no válido.

    Se lanza cuando se especifica un nombre de modelo que no está
    en la lista de modelos válidos (tiny, base, small, medium, large, turbo).
    """

    pass


class SummaryError(MeetingRecorderError):
    """Error durante la generación de resumen.

    Se lanza cuando la API de OpenAI no responde dentro del timeout
    de 60 segundos o retorna un error.
    """

    pass


class ConfigurationError(MeetingRecorderError):
    """Error de configuración del sistema.

    Se lanza cuando la configuración es inválida, por ejemplo
    cuando la API key de OpenAI está vacía o no definida.
    """

    pass


class StorageError(MeetingRecorderError):
    """Error de almacenamiento.

    Se lanza cuando la ruta de almacenamiento no es accesible,
    no se pueden crear directorios, o hay problemas de permisos.
    """

    pass


class DiskSpaceError(StorageError):
    """Espacio en disco insuficiente.

    Se lanza cuando el espacio disponible es inferior a 50 MB
    durante la grabación o al verificar espacio antes de operar.
    """

    pass


class PipelineTimeoutError(MeetingRecorderError):
    """Un paso del pipeline excedió el timeout.

    Se lanza cuando la transcripción o el resumen no completan
    su ejecución dentro del límite de 120 segundos por paso.
    """

    pass
