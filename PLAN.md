# Plan del proyecto — Plataforma estabilizadora de pelota

## 1. Objetivo

Construir un sistema completo, didáctico y verificable para mantener una pelota de
ping pong cerca del centro de una placa de cartón de 24 × 24 cm. La cámara de un
celular detecta la pelota; la PC normaliza su posición y la envía por USB serie; el
ESP32 ejecuta el PID, mueve dos servos MG90S y devuelve telemetría.

El proyecto debe poder probarse en una PC Windows sin cámara, ESP32 ni servos gracias
a una cámara sintética y un `FakeESP32` que hablan el mismo protocolo.

## 2. Arquitectura

```
Cámara del celular ──> camera.py ──> vision.py ──> main.py ──> serial_link.py
                                                          │            │
                                                          │            ▼
                                                          │      USB serie 115200
                                                          │            │
                                                          │            ▼
                                                          │      ESP32: protocolo,
                                                          │      PID 100 Hz, estados,
                                                          │      servos, LED, buzzer,
                                                          │      IMU opcional
                                                          │            │
                                                          └──── telemetría T (25 Hz) ◄┘
                                                                       │
                                                         GUI + logger CSV
```

- La PC **no** ejecuta el PID en modo real: solo visión, envío de posición y
  telemetría. El lazo cerrado vive en el ESP32.
- La simulación reemplaza cámara y enlace por equivalentes en Python, pero mantiene
  el protocolo de texto y el mismo algoritmo PID para validar la lógica completa.
- `config.h` contiene exclusivamente los valores físicos y de comportamiento del
  firmware; `config.json` contiene cámara, visión, ROI, enlace y valores iniciales
  del PID para la GUI.

## 3. Fases de trabajo

| Fase | Contenido | Estado | Verificación |
|---|---|---|---|
| A | Esqueleto, `PLAN.md`, configuración y dependencias | Completada | Árbol completo y dependencias instaladas |
| B | Protocolo y PID, primero en Python y C++ | Completada | `pytest` y tests nativos de PlatformIO |
| C | Firmware ESP32 completo | Completada | `pio run`; tests nativos; compilación con `USE_IMU=0/1` |
| D | Visión HSV, ROI y normalización | Completada | Tests con imágenes sintéticas |
| E | Cámara, enlace serie, GUI, logger y calibración | Completada | Importaciones, CSV y ventana real verificados |
| F | Simulación e integración cerrada | Completada | La pelota converge en simulación; se abrió la ventana y se inspeccionó |
| G | Documentación para principiante | Completada | README, cableado, protocolo y pruebas de hardware |
| H | Autorrevisión de signos, unidades, límites, hilos y bloqueos | Completada | Correcciones y ejecución final de todo lo verificable |

El repositorio git se inicializó al final del trabajo (al comienzo no existía en la
carpeta de trabajo) y los archivos se agruparon en commits lógicos por fase al
cerrar la fase H. El entorno de desarrollo usó el Python global y PlatformIO Core
instalado con pip; las instrucciones para el usuario sí crean un entorno virtual.

## 4. Supuestos tomados

Los siguientes puntos no estaban completamente definidos. Se eligió la opción más
simple y segura; todos son cambiables en configuración o están documentados.

1. **Signo de inclinación.** En el firmware, `tilt_x > 0` representa una inclinación
   que acelera la pelota hacia +X (derecha de la imagen); `tilt_y > 0` acelera hacia
   +Y (arriba de la imagen). El PID usa `error = setpoint − medición` con ganancias
   positivas. La conversión a servo aplica un signo configurable por eje
   (`SERVO_INVERT_X`, `SERVO_INVERT_Y`) para adaptarse al montaje.
2. **Dos niveles de inversión.** `config.h` tiene la inversión de los servos (nivel
   físico). `config.json` tiene `invert_x`/`invert_y` para la convención de la imagen
   (por ejemplo, cámara montada espejada o ROI definida al revés). Normalmente ambos
   quedan en `false`; no se deben usar los dos para corregir el mismo problema. El
   asistente de ejes indica qué bandera de `config.h` cambiar.
3. **ROI y perspectiva.** La ROI es un cuadrilátero de 4 puntos. La detección se hace
   sobre el cuadro completo enmascarando la ROI. Si `perspective` está activo, la
   normalización de coordenadas usa una homografía (`getPerspectiveTransform`) hacia
   un cuadrado; no se deforma el video mostrado. Esto reduce latencia y cumple la
   normalización relativa a la placa.
4. **Orden de las esquinas de la ROI.** Se piden al usuario en el orden
   arriba-izquierda, arriba-derecha, abajo-derecha, abajo-izquierda. El software
   reordena automáticamente si es razonablemente posible.
5. **Pelota perdida.** Cuando `found = 0` o pasan más de 200 ms sin una medición
   válida, el estado automático pasa a "perdida", se resetea el PID y la inclinación
   vuelve a cero en rampa. `P` con `found=0` se envía con `0,0`; el firmware ignora
   las coordenadas y usa el timestamp de recepción.
6. **Estado "buscando".** Al entrar en automático se muestra "buscando" hasta que
   llegue la primera medición válida, con un máximo de 200 ms; después se pasa a
   "perdida" si no hay pelota. Así se respeta el timeout de 200 ms.
7. **Modo automático y arranque.** El firmware arranca en modo 0 (apagado) y nunca
   pasa a automático si no recibe exactamente `M,2`. La PC puede enviar `M,2` tras
   conectar; en `--sim` lo hace sola para que la demostración converja sin tocar
   teclas. En hardware real el primer arranque muestra la placa quieta hasta que el
   operador elige modo.
8. **Fallback al perder comunicación.** En modo automático, después de 1 s sin
   paquetes válidos, la placa va suavemente a nivel y queda en estado "perdida".
   No cambia sola a modo manual. Al volver el enlace, la PC reenvía `M` y `G`.
9. **Comandos inválidos.** Los valores continuos fuera de rango se saturan
   (posición, inclinación, ganancias, offsets, límite). Un modo desconocido o una
   línea mal formada no cambia el estado y devuelve `ERR`; nunca se interpreta un
   `M` inválido como `M,2`.
10. **Servos.** Se usa la librería `ESP32Servo` con pulsos de 500–2400 µs. Todos los
    ángulos pasan siempre por una función de recorte a 56–124°. El modo manual y el
    comando de calibración `V` también pasan por ese recorte.
11. **`V` (servo crudo).** Se acepta solo en modos 0 y 1 (nunca en automático). Mueve
    los servos al ángulo pedido y mantiene ese valor hasta que llegue `M`, `A` o una
    nueva orden de control; se usa para verificar el centro físico. `C` ajusta los
    offsets usados por la conversión normal.
12. **Ganancias por eje.** El protocolo permite `G,X,...` y `G,Y,...` por separado;
    la GUI usa `G,B,...` para mantener ambos ejes iguales. Las ganancias y los
    offsets se guardan en Preferences con `W`.
13. **Telemetría sin hardware.** `roll` y `pitch` valen `0.00` si `USE_IMU=0` o si
    todavía no hay lectura. La IMU no participa del lazo de control.
14. **Cámara.** El índice de cámara usa DirectShow en Windows (con fallback genérico);
    una URL se entrega a OpenCV como texto. Se solicitan 640×480 a 60 fps y MJPG, pero
    la cámara manda; si no los soporta se usan los valores reales que entregue.
15. **GUI y calibración extra.** Además de las teclas pedidas se agregan `E` para el
    asistente de ejes y `K` para el calibrador del centro de servos, porque esos dos
    procedimientos son requisitos de calibración y no tenían tecla asignada.
16. **Persistencia de la PC.** La ROI, el rango HSV y las inversiones de imagen se
    guardan en `config.json`. El ESP32 guarda ganancias y offsets en su propia NVS.
    Al presionar `W`, la GUI también sincroniza las ganancias en `config.json` para
    que la próxima sesión no pise las recién guardadas en el ESP32.
17. **Archivos extra.** Se agrega `pc/config.py` como único módulo auxiliar para
    cargar/guardar la configuración JSON de forma consistente; no agrega frameworks
    ni funcionalidad de terceros. `pc/tests/` y `pc/logs/` no estaban detallados pero
    son consecuencia directa de los requisitos de pruebas y registro.
18. **Sin rebote.** La simulación no modela rebotes: al llegar a ±1 la posición se
    limita y la velocidad se anula. La meta de convergencia se evalúa antes de que
    eso ocurra; si la pelota se escapa, el test falla.
19. **Zona muerta y saturación.** La salida del PID se satura a ±8° y luego pasa por
    un limitador de velocidad configurable (por defecto 120 °/s). El retorno a nivel
    por pelota perdida usa la rampa configurable de 30 °/s.
20. **Pruebas sin hardware.** Todo lo que requiere cámara física, ESP32, servos, LED,
    buzzer o IMU se marca con `TODO-HW:` y se numera en `HARDWARE_TEST.md`.
21. **Asistente de ejes.** No puede modificar `config.h` en caliente. Determina la
    dirección real observando el movimiento de la pelota. Para calcular el valor
    absoluto parte de los flags actuales del espejo
    `simulation.servo.invert_x/y` de `config.json` (que debe coincidir con
    `config.h`) y, si la dirección es la esperada, los conserva; si no, los
    invierte. Muestra/imprime los valores para recompilar. Las banderas
    `invert_x/y` de `config.json` quedan reservadas para invertir la convención de
    imagen; no se cambian automáticamente para no duplicar correcciones.
22. **Logger.** El CSV se escribe con flush por fila para poder inspeccionarlo en
    vivo y no perder datos si la app se cierra de golpe. Está en `pc/logs/`, que no
    se versiona.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Signo físico de un servo invertido | El lazo se vuelve inestable y la pelota se cae | Flags `SERVO_INVERT_*`, asistente de ejes y prueba manual 3 |
| Ruido/luz que confunde la detección naranja | No se detecta o se detecta de más | Calibrador HSV en vivo, rango de área/circularidad y ROI |
| Latencia de cámara por USB o stream | Oscilación y pérdida de pelota | Hilo con buffer de 1, MJPG, límites de velocidad y timeout de 200 ms |
| Picos de corriente de los MG90S | Reinicios del ESP32 | Fuente de 5 V aparte, GND común y capacitor de 470–1000 µF |
| Integral acumulada durante pérdidas | Golpe de inclinación al recuperar | Reset del PID al perder y anti-windup |
| Comunicación serie bloqueada | GUI congelada | Un solo hilo de I/O, cola acotada y reconexión no bloqueante |
| Diferencias entre simulación y hardware | Ganancias de simulación no sirven | Aclaración en README; ajuste real comienza con Kp bajo |
| Pérdida de paquetes por ruido | Falsos estados de pérdida | Parser tolerante, timeout de 200 ms y timeout de enlace de 1 s |
| Python/OpenCV con versiones incompatibles | No arranca en Windows | Versiones mínimas en `requirements.txt` y entorno virtual documentado |
| Ausencia de PlatformIO en el entorno de desarrollo | No se puede compilar aquí | Se intenta instalar; si falla se documenta y se dejan tests nativos listos |

## 6. Criterios de aceptación y cómo se verifican

1. `pytest` en `pc/` pasa: suite de PID, conversión, protocolo, normalización,
   detección sintética e integración.
2. `pio run` compila el firmware. Si el entorno no lo permite, se informa el error y
   se valida al menos la lógica C++ con los tests nativos si hay compilador local.
3. `python main.py --sim` abre la ventana de OpenCV y la pelota converge a
   `|error| < 0.05`; se documenta el tiempo medido por el test de integración.
4. El firmware nunca manda ángulos fuera de [56°, 124°]: recorte centralizado y tests
   de conversión.
5. El firmware solo entra en automático con `M,2`: parser estricto para el modo y
   máquina de estados que arranca apagada.
6. Con el enlace caído en automático, la placa se nivela:
   timeout de 1000 ms + rampa de 30 °/s desde 8° = 0,27 s; total < 1,5 s.
7. Todos los valores físicos están en `config.h` o `config.json`.

## 7. Pendientes que requieren hardware

- Verificar el sentido real de ambos servos y elegir `SERVO_INVERT_*`.
- Medir el centro mecánico real y ajustar `C,<off_x>,<off_y>`.
- Comprobar que los servos no superan 56–124° con la placa montada.
- Validar la detección HSV con la iluminación real y la cámara del celular.
- Medir latencia real cámara → USB → visión y fps del celular.
- Ajustar Kp, Kd y Ki reales (los valores de simulación no son los definitivos).
- Probar LED, buzzer, timeout de enlace, IMU y alimentación bajo carga.
- Confirmar que la pelota no recibe golpes ni rebotes de la mecánica.

## 8. Estado de ejecución

### Entorno comprobado

- Windows 11 Pro, Python 3.12.10, pip 25.0.1.
- OpenCV 5.0.0, NumPy 2.5.4, pyserial 3.5, pytest 9.2.0, matplotlib 3.11.2.
- PlatformIO Core 6.2.0, plataforma `espressif32` 8.0.0, framework Arduino 3.3.12,
  ESP32Servo 3.2.1, toolchain xtensa-esp-elf 14.2.0, GCC nativo 13.2.0 (MinGW).
- Git no existía al comenzar; se inicializó un repositorio local al cerrar el
  proyecto.

### Resultados reales

| Verificación | Resultado |
|---|---|
| `python -m pytest -q` desde `pc/` | **78 passed** |
| `pio test -e native` desde `firmware/` | **11 test cases: 11 succeeded** |
| `pio run` para `esp32dev` | **SUCCESS**; RAM 7,0 %, flash 26,0 % con IMU apagada |
| `pio run` con `USE_IMU=1` | **SUCCESS**; compila la rama real de Wire/MPU6050 |
| Integración de convergencia | ≈**1,23 s** para entrar en tolerancia (límite de test 12 s) |
| Tiempo estable requerido | `|x|<0,05` y `|y|<0,05` durante 1 s |
| `python main.py --sim` | Abrió ventana OpenCV 656×639; se capturó e inspeccionó el cuadro, con la pelota centrada a los 4 s |
| CSV | Se generaron y leyeron archivos de telemetría reales del simulador |
| `tools/plot_log.py --save` | Generó un PNG de 97 874 bytes a partir del CSV |
| Cámara/ESP32/servos/LED/buzzer/IMU reales | **No probados** (no hay hardware disponible) |

### Correcciones hechas en la autorrevisión

- Se cerró la condición de carrera de `_stored_commands` entre el hilo de enlace y
  la GUI usando el lock del enlace.
- Se protegieron los cierres de ventanas de calibración para que cerrar una ventana
  con la X no tumbe la aplicación.
- Se corrigió el caso en que cancelar el asistente de ejes dejaba la GUI sin
  procesar teclas.
- Se corrigió el asistente de ejes para que calcule los valores absolutos de
  `SERVO_INVERT_*` a partir de los flags actuales, en vez de invertirlos siempre.
- Se agregó un límite de coordenadas al clic del mouse para no tomar clics sobre las
  trackbars como setpoints.
- Se aumentó la altura del panel de estado para que no se corte la línea de latencia.
- Se agregó flush por fila al CSV.
- Se protegió la lectura de cámara contra un error de OpenCV durante la desconexión.
- Se revisaron signos, grados/radianes y límites de servo en firmware y simulación.
- Se compiló el firmware con y sin IMU.

### Pendiente de hardware

Todo lo listado en la sección 7 y en `HARDWARE_TEST.md`. En particular: sentido
físico, centro mecánico, alimentación real, detección bajo luz real, ajuste del PID
y pruebas de LED/buzzer/IMU/fallback.
