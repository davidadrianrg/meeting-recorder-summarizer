# Documento de Requisitos

## Introducción

Meeting Recorder es una herramienta para Fedora Silverblue que graba audio del sistema (entrada de micrófono y salida de aplicaciones), transcribe las grabaciones usando un modelo local de Whisper, y genera resúmenes con viñetas mediante la API de OpenAI. La herramienta se despliega como contenedor Podman y se controla mediante un atajo de teclado para iniciar/detener la grabación. Al detener la grabación, la transcripción y el resumen se generan automáticamente en segundo plano.

## Glosario

- **Grabador**: Componente del sistema responsable de capturar audio del sistema mediante PipeWire
- **Transcriptor**: Componente que convierte audio grabado a texto usando el modelo local de Whisper
- **Resumidor**: Componente que genera resúmenes con viñetas a partir de transcripciones usando la API de OpenAI
- **Pipeline**: Flujo completo de procesamiento desde la detención de grabación hasta la generación del resumen
- **PipeWire**: Sistema de audio nativo de Fedora Silverblue que gestiona entrada y salida de audio
- **Contenedor_Podman**: Contenedor OCI gestionado por Podman donde se ejecuta el servicio
- **Controlador_Atajos**: Componente del host que intercepta atajos de teclado y comunica comandos al contenedor
- **Almacenamiento**: Estructura de directorios que organiza grabaciones, transcripciones y resúmenes

## Requisitos

### Requisito 1: Captura de Audio del Sistema

**Historia de Usuario:** Como usuario, quiero grabar el audio de entrada (micrófono) y salida (aplicaciones/escritorio) de mi sistema simultáneamente, para capturar reuniones completas de Teams incluyendo mi voz y la de los participantes remotos.

#### Criterios de Aceptación

1. WHEN el usuario activa la grabación, THE Grabador SHALL capturar audio de entrada (micrófono) y audio de salida (aplicaciones) simultáneamente mediante PipeWire
2. WHILE la grabación está activa, THE Grabador SHALL mezclar las fuentes de audio de entrada y salida en un único archivo de audio, normalizando ambas fuentes al mismo nivel de volumen
3. WHILE la grabación está activa, THE Grabador SHALL almacenar el audio en formato WAV con frecuencia de muestreo de 16kHz, 16 bits de profundidad y canal mono
4. IF PipeWire no está disponible o la conexión falla antes de iniciar la grabación, THEN THE Grabador SHALL registrar el error indicando la causa del fallo y notificar al usuario mediante un mensaje en la salida estándar de error en un máximo de 2 segundos
5. WHEN la grabación se inicia, THE Grabador SHALL nombrar el archivo con el formato `grabacion_YYYY-MM-DD_HH-MM-SS.wav` en el directorio de trabajo actual
6. IF una de las fuentes de audio (entrada o salida) no está disponible pero la otra sí, THEN THE Grabador SHALL continuar la grabación únicamente con la fuente disponible y registrar una advertencia indicando cuál fuente no se pudo capturar
7. WHEN el usuario detiene la grabación, THE Grabador SHALL finalizar la escritura del archivo WAV con cabeceras válidas y liberar las conexiones a PipeWire en un máximo de 3 segundos
8. IF el espacio en disco disponible es inferior a 50 MB durante la grabación, THEN THE Grabador SHALL detener la grabación de forma ordenada, guardar el audio capturado hasta ese momento y notificar al usuario que la grabación se detuvo por falta de espacio

### Requisito 2: Control de Grabación por Atajo de Teclado

**Historia de Usuario:** Como usuario, quiero iniciar y detener la grabación con un atajo de teclado, para controlar la captura de audio sin cambiar de ventana durante una reunión.

#### Criterios de Aceptación

1. WHEN el usuario presiona el atajo de teclado configurado (por defecto Ctrl+Shift+R), THE Controlador_Atajos SHALL alternar el estado de grabación entre activo e inactivo
2. WHEN la grabación se activa mediante el atajo, THE Controlador_Atajos SHALL enviar una señal de inicio al Contenedor_Podman y esperar confirmación dentro de un máximo de 5 segundos
3. WHEN la grabación se desactiva mediante el atajo, THE Controlador_Atajos SHALL enviar una señal de detención al Contenedor_Podman y esperar confirmación dentro de un máximo de 5 segundos
4. WHEN el estado de grabación cambia exitosamente, THE Controlador_Atajos SHALL mostrar una notificación de escritorio durante 3 segundos indicando si la grabación está activa o inactiva
5. THE Controlador_Atajos SHALL ejecutarse en el host como un script que se comunica con el contenedor mediante comando Podman exec
6. IF el Contenedor_Podman no responde a la señal dentro del tiempo límite de 5 segundos, THEN THE Controlador_Atajos SHALL mostrar una notificación de error indicando que el contenedor no está disponible y mantener el estado de grabación anterior sin cambios
7. IF el Contenedor_Podman no está en ejecución cuando el usuario presiona el atajo, THEN THE Controlador_Atajos SHALL mostrar una notificación de error indicando que el servicio de grabación no está activo y no modificar el estado de grabación

### Requisito 3: Transcripción Automática con Whisper Local

**Historia de Usuario:** Como usuario, quiero que las grabaciones se transcriban automáticamente usando un modelo local de Whisper, para obtener el texto de mis reuniones sin depender de servicios externos de transcripción.

#### Criterios de Aceptación

1. WHEN la grabación se detiene, THE Transcriptor SHALL iniciar la transcripción del archivo de audio generado en un máximo de 5 segundos
2. THE Transcriptor SHALL usar el modelo local de openai-whisper con procesamiento en CPU por defecto
3. WHERE la aceleración CUDA está habilitada mediante variable de entorno, THE Transcriptor SHALL ejecutar la transcripción utilizando la GPU NVIDIA
4. WHEN la transcripción finaliza, THE Transcriptor SHALL guardar el resultado en formato texto plano con codificación UTF-8 en el directorio de transcripciones
5. WHEN la transcripción finaliza, THE Transcriptor SHALL nombrar el archivo con el mismo prefijo temporal que la grabación correspondiente con extensión `.txt`
6. IF la transcripción falla por un error del modelo o porque el archivo de audio no existe o no es legible, THEN THE Transcriptor SHALL registrar el error indicando la causa y conservar el archivo de audio original para reintento manual
7. THE Transcriptor SHALL soportar la configuración del modelo de Whisper (tiny, base, small, medium, large, turbo) mediante variable de entorno, usando el modelo "base" cuando la variable no está definida
8. IF la variable de entorno del modelo contiene un valor no reconocido, THEN THE Transcriptor SHALL registrar un error indicando los valores válidos y no iniciar la transcripción

### Requisito 4: Generación de Resúmenes con API de OpenAI

**Historia de Usuario:** Como usuario, quiero obtener un resumen con viñetas de cada reunión transcrita, para revisar rápidamente los puntos clave sin leer la transcripción completa.

#### Criterios de Aceptación

1. WHEN la transcripción finaliza exitosamente, THE Resumidor SHALL enviar el texto transcrito a la API de OpenAI para generar un resumen en español
2. THE Resumidor SHALL usar un modelo económico de OpenAI (gpt-4o-mini o equivalente) para minimizar costos
3. WHEN la API de OpenAI retorna la respuesta, THE Resumidor SHALL generar el resumen en formato de viñetas (bullet points) conteniendo entre 5 y 15 puntos que resuman decisiones, tareas asignadas y temas discutidos en la reunión
4. WHEN el resumen se genera exitosamente, THE Resumidor SHALL guardar el resultado en formato Markdown en el directorio de resúmenes
5. WHEN el resumen se genera, THE Resumidor SHALL nombrar el archivo con el mismo prefijo temporal que la grabación correspondiente con extensión `.md`
6. IF la API de OpenAI no responde dentro de 60 segundos o retorna un error, THEN THE Resumidor SHALL registrar el error indicando el tipo de fallo y conservar la transcripción para reintento manual
7. THE Resumidor SHALL leer la clave de API de OpenAI desde una variable de entorno (`OPENAI_API_KEY`)
8. IF la variable de entorno `OPENAI_API_KEY` no está definida o está vacía, THEN THE Resumidor SHALL mostrar un mensaje de error indicando que la clave de API es requerida y no procesar la transcripción

### Requisito 5: Ejecución en Contenedor Podman

**Historia de Usuario:** Como usuario de Fedora Silverblue, quiero que el servicio se ejecute en un contenedor Podman, para mantener el sistema inmutable y gestionar dependencias de forma aislada.

#### Criterios de Aceptación

1. THE Contenedor_Podman SHALL incluir las siguientes dependencias: Python 3.12+, ffmpeg, openai-whisper, torch (compilado para CPU por defecto), y `uv` como gestor de dependencias Python
2. THE Contenedor_Podman SHALL montar el directorio de Almacenamiento del host (según la ruta configurada en Requisito 6) para persistir grabaciones, transcripciones y resúmenes
3. THE Contenedor_Podman SHALL montar el socket de PipeWire del host (ubicado en `$XDG_RUNTIME_DIR/pipewire-0`) para capturar audio del sistema
4. WHERE la aceleración CUDA está habilitada mediante la variable de entorno `ENABLE_CUDA=true`, THE Contenedor_Podman SHALL exponer acceso a la GPU NVIDIA del host mediante NVIDIA Container Toolkit
5. THE Contenedor_Podman SHALL ejecutarse en modo rootless y iniciarse automáticamente con la sesión del usuario mediante un servicio systemd de usuario (`systemctl --user`)
6. IF el contenedor se detiene inesperadamente, THEN THE Contenedor_Podman SHALL reiniciarse automáticamente con un máximo de 3 reintentos en un intervalo de 60 segundos antes de permanecer detenido
7. THE Contenedor_Podman SHALL recibir las variables de entorno necesarias para la operación del servicio: `OPENAI_API_KEY`, `WHISPER_MODEL` (por defecto `base`), `ENABLE_CUDA` (por defecto `false`), y `STORAGE_PATH` (por defecto `~/meeting-recorder-data/`)

### Requisito 6: Estructura de Almacenamiento

**Historia de Usuario:** Como usuario, quiero que las grabaciones, transcripciones y resúmenes se organicen en directorios separados, para localizar fácilmente cualquier artefacto de una reunión específica.

#### Criterios de Aceptación

1. THE Almacenamiento SHALL organizar los archivos en tres directorios: `recordings/`, `transcriptions/`, y `summaries/`
2. WHEN el sistema se inicia, IF la estructura de directorios no existe, THEN THE Almacenamiento SHALL crear los directorios `recordings/`, `transcriptions/`, y `summaries/` con permisos de lectura y escritura para el usuario del proceso
3. THE Almacenamiento SHALL nombrar los archivos usando el patrón `YYYY-MM-DD_HH-MM-SS` en zona horaria local del sistema, de modo que los archivos generados en una misma sesión compartan el mismo prefijo temporal en los tres directorios
4. THE Almacenamiento SHALL ubicarse en la ruta definida por la variable de entorno `MEETING_RECORDER_DATA_DIR`, con valor por defecto `~/meeting-recorder-data/`
5. IF la ruta configurada no existe o no es accesible con permisos de escritura, THEN THE Almacenamiento SHALL informar al usuario con un mensaje de error indicando la ruta inaccesible y SHALL detener la ejecución sin pérdida de datos
6. IF el sistema no puede crear la estructura de directorios durante el inicio, THEN THE Almacenamiento SHALL informar al usuario con un mensaje de error indicando el motivo del fallo y SHALL detener la ejecución

### Requisito 7: Pipeline Automático de Procesamiento

**Historia de Usuario:** Como usuario, quiero que la transcripción y el resumen se generen automáticamente al detener la grabación, para obtener los resultados sin intervención manual.

#### Criterios de Aceptación

1. WHEN la grabación se detiene, THE Pipeline SHALL ejecutar secuencialmente: primero la transcripción del audio y luego la generación de resumen a partir de la transcripción obtenida
2. WHILE el Pipeline está procesando, THE Pipeline SHALL permitir iniciar una nueva grabación, ejecutando un máximo de 3 pipelines de forma concurrente sin esperar a que finalicen los anteriores
3. IF la transcripción falla, THEN THE Pipeline SHALL omitir la generación de resumen, registrar el error del paso fallido, y enviar una notificación de escritorio al usuario indicando que el procesamiento falló en la etapa de transcripción
4. WHEN el Pipeline completa todos los pasos exitosamente, THE Pipeline SHALL enviar una notificación de escritorio al usuario indicando que el resumen está disponible
5. IF un paso del Pipeline no completa su ejecución dentro de 120 segundos, THEN THE Pipeline SHALL cancelar dicho paso, registrar el error por timeout, y tratar el paso como fallido

### Requisito 8: Eliminación de Dependencias Windows

**Historia de Usuario:** Como desarrollador, quiero que el proyecto sea exclusivamente Linux, para mantener una base de código limpia y enfocada en la plataforma objetivo.

#### Criterios de Aceptación

1. THE Sistema SHALL eliminar todos los archivos con extensiones exclusivas de Windows (`.bat`, `.ps1`, `.cmd`) del directorio del proyecto
2. THE Sistema SHALL eliminar todas las referencias a rutas de Windows del código fuente, incluyendo rutas con letras de unidad (e.g., `C:\`), separadores backslash como delimitadores de ruta, y referencias a binarios `.exe`
3. THE Sistema SHALL usar exclusivamente rutas POSIX (separador `/`, sin letras de unidad) en todos los archivos de código fuente y scripts shell, incluyendo el contenido de scripts como `activate_comfy.sh`
4. THE Sistema SHALL resolver la ruta de `ffmpeg` exclusivamente mediante búsqueda en el PATH del sistema, sin referencias a rutas absolutas ni a binarios `.exe` locales
5. THE Sistema SHALL documentar en el archivo README.md los requisitos del sistema operativo, especificando Fedora Silverblue como sistema base y PipeWire como servidor de audio, dentro de una sección dedicada de requisitos del sistema
