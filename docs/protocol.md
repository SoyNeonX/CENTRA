# Protocolo serie PC ↔ ESP32

Comunicación de texto ASCII por USB serie, una línea por mensaje terminada en
`\n` (el firmware tolera `\r\n`). Valor por defecto: **115200 baudios**.

Los dos lados ignoran líneas truncadas o inválidas. El firmware responde
`ERR,<motivo>` cuando una línea parece un comando pero no se puede parsear.

> Versión 1.1.0: las posiciones y los setpoints se expresan en **centímetros**
> sobre la placa. La placa mide 24 × 24 cm; el rango válido es [-12, +12] cm en
> cada eje. El origen `(0,0)` es el centro.

## 1. PC → ESP32

| Comando | Formato | Significado |
|---|---|---|
| `P` | `P,<x_cm>,<y_cm>,<found>` | Posición de la pelota en cm. `found` = `0` o `1`. |
| `M` | `M,<modo>` | `0` apagado, `1` manual, `2` automático. |
| `A` | `A,<tilt_x>,<tilt_y>` | Inclinación deseada en grados, solo en modo manual. |
| `V` | `V,<servo_x>,<servo_y>` | Ángulo crudo de servo para calibrar el centro. |
| `G` | `G,<eje>,<kp>,<ki>,<kd>` | Ganancias en grados/cm. Eje `X`, `Y` o `B`. |
| `S` | `S,<sx_cm>,<sy_cm>` | Setpoint en cm. |
| `C` | `C,<off_x>,<off_y>` | Offset del centro de cada servo, en grados. |
| `L` | `L,<grados>` | Límite de inclinación en grados. |
| `W` | `W` | Guarda ganancias y offsets en Preferences (NVS). |
| `H` | `H` | Pide el `HELLO`. |

`C` se conserva como extensión del protocolo: la UI de calibración de centro lo
necesita y el firmware guarda los offsets con `W`.

### Rangos y saturación

Los valores continuos fuera de rango se **saturan**, no se rechazan:

| Campo | Rango efectivo |
|---|---|
| `P.x`, `P.y` | [-12, 12] cm |
| `S.sx`, `S.sy` | [-12, 12] cm |
| `A.tilt_x`, `A.tilt_y` | [-límite actual, +límite actual]; de fábrica ±8° |
| `V.servo_x`, `V.servo_y` | [56, 124] grados, siempre |
| `G.kp` | [0, 5] grados/cm |
| `G.ki` | [0, 1] |
| `G.kd` | [0, 5] |
| `C.off_x`, `C.off_y` | [-20, 20] grados |
| `L` | [0.5, 8] grados |

Los valores discretos inválidos no se saturan: `M,3`, `found=2` o un eje distinto
de `X/Y/B` producen `ERR` y no cambian el estado.

### Detalles

- **P** se manda por cada cuadro procesado (30–60 Hz). Si no se detecta la pelota
  o la placa, se manda `P,0.00,0.00,0`. El firmware solo usa las coordenadas con
  `found=1`, pero actualiza el timestamp para detectar la pérdida.
- **M,2** es la única forma de entrar en automático. El firmware arranca apagado.
- **A** solo se acepta en manual; en 0/2 devuelve `ERR,modo_no_manual`.
- **V** mueve los servos directamente y mantiene el valor hasta `M`, `A` o una
  nueva orden. En automático devuelve `ERR,modo_auto`.
- **G** se puede mandar por eje o con `B`. Ejemplo: `G,B,0.500,0.020,0.330`.
- **W** guarda ganancias y offsets. El setpoint, el modo y el límite de inclinación
  no se guardan en NVS.
- **H** responde `HELLO,1.1.0`; la PC lo usa para autodetectar el puerto.

### Ejemplos

```
P,3.25,-2.10,1
P,0.00,0.00,0
M,1
A,2.0,-1.5
G,B,0.500,0.020,0.330
S,0.00,0.00
C,0.00,0.00
L,8.00
V,90.00,91.50
W
H
```

## 2. ESP32 → PC

### HELLO

```
HELLO,1.1.0
```

Se envía al arrancar y ante cada `H`. La versión está en `FW_VERSION` de
`firmware/include/config.h`.

### Respuestas

- `OK,<cmd>`: comando aceptado. Los `P` también reciben `OK,P`; la GUI los ignora.
- `ERR,<motivo>`: `comando_desconocido`, `argumentos_invalidos`, `numero_invalido`,
  `fuera_de_rango`, `linea_vacia`, `linea_larga`, `modo_no_manual`, `modo_auto`,
  `nvs`.

### Telemetría T (25 Hz por defecto)

```
T,<ms>,<x_cm>,<y_cm>,<err_x_cm>,<err_y_cm>,<tilt_x>,<tilt_y>,<sx>,<sy>,<estado>
```

| Campo | Unidad | Significado |
|---|---|---|
| `ms` | ms | `millis()` del ESP32 desde el arranque. |
| `x_cm`, `y_cm` | cm | Última posición recibida, en [-12, 12]. |
| `err_x_cm`, `err_y_cm` | cm | `setpoint - posición`; 0 si no está estabilizando. |
| `tilt_x`, `tilt_y` | grados | Inclinación comandada por el PID, manual o nivel. |
| `sx`, `sy` | grados | Ángulo real convertido a los servos, siempre en [56, 124]. |
| `estado` | — | 0 apagado, 1 manual, 2 buscando, 3 estabilizando, 4 pelota perdida. |

La telemetría se sigue mandando en apagado/manual; en ese caso los errores valen
0 y la inclinación es la manual o la de nivel.

## 3. Convención de signos y de placa

- La cámara ve la placa desde arriba. El marcador **ID 0** está arriba-izquierda,
  **ID 1** arriba-derecha, **ID 2** abajo-derecha e **ID 3** abajo-izquierda.
- `x = +12 cm` está a la **derecha** de la imagen; `x = -12 cm` a la izquierda.
- `y = +12 cm` está **arriba** en la imagen; `y = -12 cm` abajo. La homografía
  de los ArUco hace la conversión de píxeles a cm.
- `tilt_x > 0` debe acelerar la pelota hacia +X; `tilt_y > 0`, hacia +Y. El PID
  usa `error = setpoint - medición` con ganancias positivas.
- Si el montaje físico del servo invierte el sentido, **no se recompila**:
  la PC espeja `P` y `S` para ese eje cuando `control.invert_x` o
  `control.invert_y` está activo. Los flags se cambian con **X/Y** en OpenCV,
  con las casillas de Tkinter o con el asistente **E**. Dejá
  `SERVO_INVERT_X/Y` de `config.h` en `false`; la corrección es por software.
- La telemetría `T` y el CSV quedan en coordenadas del firmware (espejadas si
  hay inversión). La GUI muestra la posición/error físicos al invertir.
- `tilt_source` en `config.json` puede ser `"command"` o `"markers"`. En esta
  entrega se usa `"command"`: la inclinación que se muestra es la comandada. La
  estimación de inclinación desde ArUco con una cámara monocular sin intrínsecos
  queda como TODO-HW.

## 4. Tiempos y seguridad

- PID a **100 Hz**, telemetría a **25 Hz**.
- Sin P válida durante **200 ms**, el automático pasa a *perdida*, resetea el PID
  y nivela la placa en rampa de 30°/s.
- Sin ningún comando válido durante **1 s** en automático, el enlace se considera
  caído y también nivela.
- Al recuperar el enlace, la PC reenvía `M`, `G`, `S` y `C` (si estaban
  configurados).
- Los límites [56°, 124°] se aplican en todos los modos, incluso `V` y `A`.
- El lazo no usa `delay()`.

## 5. Autodetección y reconexión

1. Abre el puerto a 115200.
2. Envía `H` y espera `HELLO,<version>` durante 1,8 s.
3. Se queda con el primer puerto que responda.
4. Al conectar reenvía los últimos `M`, `G`, `S`/`C`.
5. Si se desconecta, reintenta sin bloquear la GUI.
