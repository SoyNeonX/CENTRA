# PLAN — CENTRA · ÁGUILAS IMPERIALES · Plataforma estabilizadora de pelota

## 1. Objetivo

Construir el software de un proyecto escolar de **ball and plate**: una placa
cuadrada de 24 × 24 cm se inclina con dos servos MG90S para llevar una pelota de
ping pong naranja al centro. La cámara de un celular mira desde arriba; la PC
detecta la placa y la pelota; el ESP32 corre el PID.

Restricciones principales:

- Windows 10/11, Python 3.10+ y usuario con programación básica.
- Sin hardware disponible en el entorno de desarrollo.
- Sin IMU en esta versión.
- La pelota no rebota.
- Todo lo físico va a `config.json` o `config.h` y se marca `TODO-HW:`.
- La entrega prioriza que el flujo básico funcione de punta a punta.

## 2. Arquitectura actual

```
Cámara (índice o URL)
   │
   ▼
markers.py: 4 ArUco → homografía → pose de placa (última pose 0.5 s)
   │
   ▼
vision.py: HSV naranja dentro de la máscara de placa → centro en píxeles
   │
   ▼
markers.py: píxel → cm (origen en el centro, +X derecha, +Y arriba)
   │  P,x_cm,y_cm,found  (USB 115200)
   ▼
ESP32: PID 100 Hz en cm → tilt ±8° → servo 56..124°
   │  T,ms,x,y,err,tilt,servo,estado  (25 Hz)
   ▼
GUI OpenCV o Tkinter + logger CSV
```

Módulos de la PC:

- `camera.py`: captura en hilo, buffer de 1 cuadro, índice/URL, reconexión.
- `markers.py`: detección ArUco, homografía, pose, máscara y conversión cm.
- `vision.py`: detección HSV de la pelota dentro de la placa.
- `serial_link.py`: autodetección por `HELLO`, lector no bloqueante, cola.
- `gui.py`: ventana OpenCV, overlay, teclas, trackbars, calibradores.
- `tk_app.py`: interfaz Tkinter responsive, vista split, gráficas y datos.
- `calibration.py`: color HSV, centro de servos y asistente de ejes guiado.
- `sim.py`: cámara sintética con ArUco, física en cm y FakeESP32.
- `logger.py`: CSV de telemetría.
- `protocol.py`: parser/formateo del protocolo.
- `devices.py`: selector visual de cámara y puerto.
- `tools/flash_firmware.py`: grabación del binario precompilado con esptool.
- `tools/generate_aruco_sheet.py`: hoja imprimible de marcadores.

## 3. Fases

| Fase | Contenido | Estado | Verificación |
|---|---|---|---|
| A | Esqueleto, configuración y dependencias | Completada | Estructura e importaciones |
| B | Protocolo y PID en Python/C++ | Completada | pytest y tests nativos |
| C | Firmware ESP32 | Completada | `pio run` |
| D | Visión HSV y geometría de placa | Completada | Tests sintéticos |
| E | Cámara, enlace, GUI, logger y calibración | Completada | Ventana y CSV |
| F | Simulación e integración | Completada | Convergencia < 12 s |
| G | Documentación para principiantes | Completada | README y guías |
| H | Autorrevisión de signos, límites e hilos | Completada | Correcciones |
| I | Selector visual de cámara y puerto | Completada | Selector y tests |
| J | Instalador, firmware precompilado y pendrive | Completada | Instalador offline y dry-run |
| K | Migración híbrida a ArUco + cm | Completada | 87 tests pasan; `pio run` y simulación estable |
| L | Ejecutable `CENTRA.exe` | Lanzador compilado | Abre la app vía `pc\.venv`; el `.exe` autocontenido requiere PyInstaller, que no se instaló |
| M | Llegada a la escuela: instalación + diagnóstico | Completada | `INSTALAR.bat`, `CENTRA.bat`, `FIRMWARE.bat` y auto-IDs |
| N | Interfaz Tkinter con cámara, plataforma 2D y gráficas | Completada y probada en simulación | Split, gráficas juntas/separadas, inversión, ventana adaptable; falta hardware |

## 4. Supuestos y decisiones

1. **Geometría de los marcadores.** Se asume una placa de 24 cm con marcadores
   de 4 cm cuyos centros están a ±10 cm del centro (2 cm del borde). Está en
   `plate.marker_centers_cm` y se puede corregir sin recompilar.
2. **Orden de IDs.** Vistos desde la cámara: ID 0 arriba-izquierda, ID 1
   arriba-derecha, ID 2 abajo-derecha e ID 3 abajo-izquierda. Un orden distinto
   produce una pose torcida, no un error silencioso.
3. **Coordenadas.** Origen en el centro, +X a la derecha de la imagen y +Y hacia
   arriba, en cm. El rango útil es ±12 cm.
4. **Ganancias en cm.** Las ganancias iniciales son `Kp=0.50`, `Ki=0.02` y
   `Kd=0.33` grados/cm. Los valores 6/0.2/4 del documento original estaban en
   unidades normalizadas; usarlos con cm saturaría el PID. La conversión es
   aproximadamente equivalente para 24 cm.
5. **Tilt.** `tilt_source="command"` es el valor validado. La estimación de
   inclinación desde los marcadores necesita intrínsecos de cámara y `solvePnP`;
   queda como TODO-HW. No se usa para el lazo.
6. **Interfaces.** OpenCV queda como interfaz principal y respaldo probado. Se
   agregó una Tkinter opcional con cámara, plataforma 2D, gráficas y datos, que
   comparte el mismo núcleo. Se probó en simulación; su calibración de ejes y
   centro de servos sigue en OpenCV.
7. **Asistente de ejes.** Es guiado (observar el sentido de la pelota), no
   automático por ArUco. La deducción automática con una cámara monocular sin
   calibración no es confiable. La inversión se aplica por software (espejando
   P/S en la PC), sin recompilar el firmware.
8. **Tolerancia de simulación.** 0.5 cm, no 0.05 cm. A 640×480 y ~40 cm, 0.05 cm
   equivale a poco más de un píxel. La simulación converge en ≈1.25 s.
9. **Comando C.** Se conserva como extensión del protocolo, aunque el documento
   de Claude no lo listaba, porque el firmware guarda offsets y la UI los ajusta.
10. **Telemetría.** 11 campos, sin roll/pitch: posición y error en cm, tilt,
    servos y estado.
11. **IMU.** Eliminada del firmware, del protocolo y de la documentación.
12. **Pelota perdida.** Si no hay P válida durante 200 ms o no hay enlace durante
    1 s en automático, se nivela con rampa y se resetea el PID.

## 5. Verificación

Verificado en Windows 11, Python 3.12, OpenCV 5.0, PlatformIO 6.2:

| Prueba | Resultado |
|---|---|
| `python -m pytest -q` desde `pc/` | **87 passed** |
| `pio test -e native` | **11/11** |
| `pio run` para `esp32dev` | **SUCCESS** |
| Simulación ArUco + PID | converge en **≈1.25 s**, tolerancia 0.5 cm |
| GUI `python main.py --sim` | ventana, 4 ArUco, placa, ejes y pelota |
| Hoja de marcadores A4 | generada; cuadrados de 4 cm a 600 dpi |
| Instalador offline | probado con wheels y Python 3.12 |
| `flash_firmware.py --dry-run` | comando y hash verificados |

Lo que **no** se probó: ESP32 real, cámara real, servos, LED, buzzer, drivers USB,
grabación por COM, luz del aula y detección ArUco física.

`CENTRA.exe` quedó compilado como **lanzador** que usa `pc\.venv`. El `.exe`
autocontenido requiere PyInstaller; la instalación de PyInstaller no terminó en
este entorno, así que `CREAR_EXE.bat` cae al lanzador. En una PC con
PyInstaller instalado genera el `.exe` completo.

La interfaz **Tkinter** se ejecutó en simulación (split, gráficas y servos
separados). La interfaz OpenCV sigue siendo la principal y no fue reemplazada.

## 6. Pendientes de hardware

- Ver `HARDWARE_TEST.md` (8 pruebas en orden).
- Compensar el centro mecánico con los offsets.
- Probar la inversión X/Y desde el software en los servos reales; dejar
  `SERVO_INVERT_X/Y` de `config.h` en false.
- Calibrar HSV con la cámara real.
- Ajustar Kp/Ki/Kd y validar en las cuatro esquinas.
- Verificar el patrón de LED/buzzer y la alimentación de los servos.
- Medir latencia real y error en cm.

## 7. Riesgos

| Riesgo | Efecto | Mitigación |
|---|---|---|
| Marcadores mal pegados u orden incorrecto | Pose torcida o sin detección | Hoja impresa al 100%, IDs y centros documentados |
| Brillos o luz desigual | No se detectan ArUco o pelota | Papel mate, luz pareja, calibrar HSV |
| Cámara muy lejos o movida | Error en cm | Fijar la cámara, ver los 4 marcadores completos |
| Ganancias demasiado altas | Saturación y oscilación | Empezar con Kp bajo; límites de firmware |
| Servos alimentados desde el ESP32 | Reinicios o daño | Fuente externa 5 V y GND común |
| `opencv-python` en vez de contrib | `cv2.aruco` ausente | Instalar `opencv-contrib-python` |
| Sin hardware en desarrollo | No se validó lo físico | `TODO-HW:` y HARDWARE_TEST.md |

## 8. Fuera de alcance de esta entrega

- Estimación de inclinación desde ArUco (`tilt_source="markers"`).
- Asistente de ejes totalmente automático.
- Fusión con IMU (no hay IMU).
- Segunda interfaz Tkinter: opcional y probada en simulación; la versión OpenCV
  es la principal. Incluye vista split, cámara, plataforma 2D, gráficas juntas y
  separadas, datos, inversión y controles adaptables.

Estas tareas se pueden agregar después sin romper el núcleo ArUco/cm.
