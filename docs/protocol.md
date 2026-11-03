# Protocolo serie PC ↔ ESP32

La comunicación es texto ASCII por USB serie, una línea por mensaje terminada en
`\n` (el firmware también tolera `\r\n`). El valor por defecto es **115200 baudios**,
configurable en `firmware/include/config.h` (`SERIAL_BAUD`) y en `pc/config.json`
(`serial.baud`).

Los dos lados ignoran líneas truncadas o inválidas sin romperse. El firmware
responde `ERR,<motivo>` a una línea que parece un comando pero no se puede parsear.

## 1. PC → ESP32

| Comando | Formato | Significado |
|---|---|---|
| `P` | `P,<x>,<y>,<found>` | Posición normalizada de la pelota, `x` e `y` en [-1, 1] con 3 decimales. `found` = `0` o `1`. |
| `M` | `M,<modo>` | `0` apagado, `1` manual, `2` automático. |
| `A` | `A,<tilt_x>,<tilt_y>` | Inclinación deseada en grados, solo válida en modo manual. |
| `V` | `V,<servo_x>,<servo_y>` | Ángulo crudo de servo para calibrar el centro. Solo en modos 0/1. |
| `G` | `G,<eje>,<kp>,<ki>,<kd>` | Ganancias. Eje `X`, `Y` o `B` (ambos). |
| `S` | `S,<sx>,<sy>` | Setpoint normalizado. |
| `C` | `C,<off_x>,<off_y>` | Offset del centro de cada servo, en grados. |
| `L` | `L,<grados>` | Límite de inclinación en grados. |
| `W` | `W` | Guarda ganancias y offsets en la NVS (Preferences) del ESP32. |
| `H` | `H` | Pide el `HELLO`. |

### Rangos y saturación

Los valores continuos que llegan fuera de rango se **saturan**, no se rechazan:

| Campo | Rango efectivo |
|---|---|
| `P.x`, `P.y` | [-1, 1] |
| `S.sx`, `S.sy` | [-1, 1] |
| `A.tilt_x`, `A.tilt_y` | [-límite actual, +límite actual]; el límite de fábrica es ±8° |
| `V.servo_x`, `V.servo_y` | [56, 124] grados, siempre |
| `G.kp` | [0, 50] |
| `G.ki` | [0, 20] |
| `G.kd` | [0, 50] |
| `C.off_x`, `C.off_y` | [-20, 20] grados |
| `L` | [0.5, 8] grados |

Los valores discretos inválidos no se saturan para evitar arranques accidentales:
un `M,3`, un `found=2` o un eje que no sea `X/Y/B` producen `ERR` y no cambian el
estado. Un modo de operación inválido nunca se interpreta como `M,2`.

### Detalles por comando

- **P** se manda por cada cuadro procesado de la cámara (30–60 Hz). Si no se
  detecta la pelota se manda `P,0.000,0.000,0`. El firmware usa las coordenadas
  solo cuando `found=1`; el timestamp de recepción se actualiza igual para poder
  detectar una pérdida.
- **M,2** es la única forma de entrar en automático. El firmware arranca en 0 y
  nunca cambia de modo por su cuenta.
- **A** solo se acepta en modo 1. En 0/2 devuelve `ERR,modo_no_manual`. Al entrar
  en manual, el firmware conserva la inclinación que tenía y luego acepta `A`.
- **V** mueve los servos directamente y mantiene el valor hasta recibir `M`, `A` o
  una nueva orden de control. En modo 2 devuelve `ERR,modo_auto`. Se usa en el
  calibrador de centro; los ángulos siempre se recortan a [56, 124].
- **G** se puede mandar por eje. La GUI manda `G,B,...` para que ambos ejes usen
  los mismos valores. Para cambiar las ganancias de un solo eje desde un script:
  `G,X,6,0.2,4`.
- **W** guarda las ganancias de ambos ejes y los offsets. El limitador de
  inclinación (`L`), el setpoint y el modo no se guardan en NVS.
- **H** responde `HELLO,<version>`. Es lo que usa la PC para autodetectar el puerto.

### Ejemplos

```
P,0.123,-0.450,1
M,1
A,2.0,-1.5
G,B,6.000,0.200,4.000
S,0.000,0.000
C,0.00,0.00
L,8.00
V,90.00,91.50
W
H
```

## 2. ESP32 → PC

### HELLO

```
HELLO,1.0.0
```

Se envía una vez al arrancar y cada vez que llega `H`. La versión del firmware está
en `FW_VERSION` (`config.h`).

### Respuestas de comandos

- `OK,<cmd>`: comando válido aceptado. `<cmd>` es la letra del comando (`P`, `M`, ...).
  Incluso `P` recibe `OK,P` para cumplir el protocolo de respuesta; la PC ignora esos
  acuses.
- `ERR,<motivo>`: comando rechazado o inválido. Motivos posibles:
  - `comando_desconocido`
  - `argumentos_invalidos`
  - `numero_invalido`
  - `fuera_de_rango`
  - `linea_vacia`
  - `linea_larga`
  - `modo_no_manual`
  - `modo_auto`
  - `nvs` (no se pudo escribir la memoria no volátil)

### Telemetría T (25 Hz por defecto)

```
T,<ms>,<x>,<y>,<err_x>,<err_y>,<tilt_x>,<tilt_y>,<sx>,<sy>,<roll>,<pitch>,<estado>
```

| Campo | Unidad | Significado |
|---|---|---|
| `ms` | ms | `millis()` del ESP32 desde el arranque. |
| `x`, `y` | normalizado | Última posición recibida, en [-1, 1]. |
| `err_x`, `err_y` | normalizado | `setpoint - posición`; vale 0 si no está estabilizando. |
| `tilt_x`, `tilt_y` | grados | Inclinación deseada que está aplicando el PID (o manual/apagado). |
| `sx`, `sy` | grados | Ángulo real convertido a los servos, siempre en [56, 124]. |
| `roll`, `pitch` | grados | Lectura de la IMU. `0.00` si `USE_IMU=0` o no hay lectura. |
| `estado` | — | 0 apagado, 1 manual, 2 buscando, 3 estabilizando, 4 pelota perdida. |

La telemetría también se sigue mandando en modo apagado/manual; en ese caso los
errores son 0 y `tilt` es la inclinación manual o de nivel.

## 3. Convención de signos

- `x = +1` está a la **derecha** de la imagen y `x = -1` a la izquierda.
- `y = +1` está **arriba** en la imagen y `y = -1` abajo (la conversión a píxeles
  invierte el eje vertical).
- Un `tilt_x > 0` debe acelerar la pelota hacia +X; un `tilt_y > 0`, hacia +Y.
  El PID usa ganancias positivas con `error = setpoint - medición`.
- Si el montaje del servo invierte el sentido físico, se corrige con
  `SERVO_INVERT_X` / `SERVO_INVERT_Y` en `firmware/include/config.h`. El asistente
  de ejes de la GUI indica qué valores poner. No se deben confundir con
  `control.invert_x` / `control.invert_y` de `config.json`, que corrigen la
  convención de la imagen (por ejemplo, cámara espejada).

## 4. Tiempos y seguridad

- El PID corre a **100 Hz** y la telemetría sale a **25 Hz**.
- Si la pelota no se ve (`found=0`) o pasan **200 ms** sin una P válida, el estado
  automático pasa a *perdida*, el PID se resetea y la inclinación vuelve a nivel
  en rampa de 30°/s.
- Si en modo automático pasan **1 s** sin ningún comando válido, el enlace se
  considera caído y también se nivela. Desde ±8° esto tarda menos de 1,5 s en
  total. El LED pasa a doble parpadeo y, a los 2 s de pérdida, suena un pitido
  largo.
- Al recuperar el enlace, la PC reenvía `M` y `G` (y `S`/`C` si estaban
  configurados) y sigue mandando `P`.
- Los límites [56°, 124°] se aplican en todos los modos, incluso `V` y `A`.
- El firmware no usa `delay()` en el lazo.

## 5. Autodetección y reconexión de la PC

Si `serial.port` está vacío y `serial.auto_detect` es `true`, `serial_link.py`
prueba los puertos COM disponibles:

1. Abre el puerto a 115200.
2. Envía `H\n` y reintenta cada 350 ms durante 1,8 s.
3. Se queda con el primer puerto que responda `HELLO,<version>`.
4. Al conectar, reenvía los últimos `M`, `G` y `S`/`C` guardados.
5. Si el cable se desconecta, cierra el puerto, espera y vuelve a buscar; la GUI
   nunca se bloquea.

Si se configura un puerto explícito en `config.json`, se prueba solo ese.
