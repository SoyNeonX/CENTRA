# CENTRA — Pruebas de hardware, en orden

**ÁGUILAS IMPERIALES**

Este proyecto se desarrolló **sin cámara, ESP32, servos, LED ni buzzer físicos**.
Todo lo marcado `TODO-HW:` en el código y las pruebas de este archivo son
obligatorias antes de dar el proyecto por terminado.

> No alimentes los servos desde el ESP32. Usá fuente externa de 5 V, GND común y
> capacitor de 470–1000 µF. Revisá `docs/wiring.md` antes de encender.

## Antes de empezar

- [ ] Firmware grabado con `FIRMWARE.bat`.
- [ ] Driver CH340 o CP210x instalado.
- [ ] Cuatro marcadores ArUco impresos, recortados con 1 cm de margen y pegados.
- [ ] Cámara del celular fija, mirando desde arriba, con la placa completa.
- [ ] `INSTALAR.bat` ejecutado y `CENTRA.bat` (opción 5) configurado.
- [ ] Fuente de 5 V apagada mientras se hacen las conexiones.

La placa debe quedar libre para inclinarse. Empezá sin pelota en las pruebas 1 a 4.

---

## Prueba 1 — Servos al centro y offsets

Objetivo: que la placa quede nivelada con los servos en 90°.

1. Encendé la fuente y conectá el ESP32. El firmware arranca **apagado** y lleva
   los servos al centro.
2. Ejecutá `CENTRA.bat`, opción 1 (OpenCV) u opción 2 (Tkinter).
3. Mirá la placa de frente: debería quedar horizontal.
4. Si está inclinada, presioná **K** en la GUI. Movés los servos con las trackbars
   y ves el resultado en la cámara/placa.
5. Ajustá los dos offsets hasta que los cuatro bordes queden a la misma altura.
6. Cerrá con **S** (envía `W` y guarda en Preferences). Anotá los valores.

**Pasa si:** la placa queda nivelada y el firmware no se reinicia al mover los
servos.

---

## Prueba 2 — Límites de servo sin pelota

Objetivo: comprobar que nunca se manda un ángulo fuera de 56°–124°.

1. Con la placa libre, presioná **1** (manual) y usá las flechas para inclinar
   +8°, -8° en X y en Y.
2. Verificá que los servos se muevan suave y que la placa no fuerce topes.
3. En el monitor serie, los campos `sx` y `sy` de `T` deben quedar siempre entre
   56 y 124.
4. Repetí con `V,56,124` y `V,124,56` (por ejemplo desde el calibrador de centro)
   y comprobá que no se superen los topes.
5. Cortá la alimentación de los servos: la placa debe quedar en una posición
   segura, sin golpear.

**Pasa si:** ningún comando, inclinación manual o PID manda un servo fuera de
[56°, 124°] y no hay zumbido contra el tope.

---

## Prueba 3 — Marcadores con luz real

Objetivo: detectar los cuatro ArUco y obtener centímetros estables.

1. Imprimí `docs/marcadores_aruco/hoja_marcadores_A4.pdf` **al 100% en A4**.
2. Verificá que cada cuadrado negro mida 4,0 × 4,0 cm.
3. Pegá los marcadores mirando a la cámara:
   - ID 0 arriba-izquierda
   - ID 1 arriba-derecha
   - ID 2 abajo-derecha
   - ID 3 abajo-izquierda
4. Los centros deben quedar a **±10 cm** del centro (2 cm del borde). Si los
   movés, actualizá `pc/config.json` → `plate.marker_centers_cm`.
5. Abrí la GUI y apuntá la cámara. En el panel debe decir `arUco 4/4`.
6. Mové la placa ±2 cm y comprobá que el contorno celeste siga los marcadores.
7. Tapá un marcador: después de **0,5 s** debe aparecer `PLACA NO DETECTADA` y el
   control debe dejar de recibir una pose nueva.

**Pasa si:** los 4 IDs se detectan con luz normal, el overlay dibuja la placa y
la posición en cm es estable (sin saltos de varios cm).

---

## Prueba 4 — Asistente de ejes

Objetivo: determinar el sentido físico de X e Y y corregirlo desde el software
(sin tocar los flags `SERVO_INVERT_X/Y` del firmware).

1. Poné la pelota en el centro y esperá a que quede quieta.
2. Presioná **E**. El asistente inclina +2° en X y te pide observar la pelota.
3. Si rueda a la **derecha**, presioná **→**. Si rueda a la **izquierda**, **←**.
4. Aceptá con **ENTER** y repetí para Y: **↑** si rueda hacia arriba, **↓** si no.
5. Al cerrar el mensaje del asistente, la app aplica la inversión **en el
   software** (espeja `P`/`S`). No hay que recompilar.
6. También podés invertir a mano con **X** o **Y** en OpenCV, o con las
   casillas **Invertir X/Y** en Tkinter.
7. Guardá con **W** si querés conservar ganancias/offsets; `config.json`
   conserva `control.invert_x/y`.

> El asistente es **guiado**: no deduce automáticamente el sentido desde la
> imagen, porque una cámara monocular sin intrínsecos no distingue de forma
> confiable si una esquina sube o se aleja. Esta decisión está documentada en
> `PLAN.md`.

**Pasa si:** al inclinar +X la pelota rueda a la derecha y al inclinar +Y rueda
hacia arriba, con la inversión aplicada desde el software.

---

## Prueba 5 — Pelota y color

Objetivo: detectar la pelota dentro de la placa y reportar cm.

1. Poné la pelota en el centro. En la GUI debe aparecer un círculo verde y
   `PELOTA x≈0.0 y≈0.0 cm`.
2. Si no aparece, presioná **C** y ajustá H, S y V con la máscara.
3. Guardá con **S/ENTER** dentro del calibrador.
4. Mové la pelota a posiciones conocidas: centro, 5 cm a la derecha, 5 cm arriba,
   5 cm abajo-izquierda. Compará con una regla.
5. Tapá la pelota: el círculo debe desaparecer y la GUI debe mandar `found=0`.

**Pasa si:** el error de posición es menor a **0,5–1 cm** en el centro de la
placa y la detección no confunde la pelota con los marcadores.

---

## Prueba 6 — Control manual en lazo abierto

Objetivo: validar servos, signos y mecánica sin PID.

1. Presioná **1**. Con las flechas incliná ±2°, ±4° en X e Y.
2. Verificá que la placa se mueva en la dirección esperada y que la pelota ruede
   hacia el lado correcto.
3. Soltá las flechas: la inclinación queda en el último valor manual (no hay
   retorno automático). Volvé a 0 con las flechas opuestas.
4. Presioná **ESPACIO**: debe apagar el control y nivelar.

**Pasa si:** los dos ejes responden, no hay vibración excesiva y la pelota rueda
en el sentido de la inclinación.

---

## Prueba 7 — Automático con Kp bajo

Objetivo: cerrar el lazo con margen.

1. Poné la pelota cerca del centro, dentro de la placa.
2. En la GUI bajá **Kp** a aproximadamente 0,20–0,30 (trackbar ×100 = 20–30).
3. Dejá Ki y Kd bajos: Ki≈0,00–0,02, Kd≈0,10–0,20.
4. Presioná **2**. El estado debe pasar a `ESTABILIZANDO`.
5. Soltá la pelota a 2–3 cm del centro. Debe volver sin oscilar demasiado.
6. Si se va al borde, presioná **ESPACIO** inmediatamente.
7. Probá el setpoint con un clic dentro de la placa; debe mover la cruz roja y
   mandar `S` en cm.

**Pasa si:** con Kp bajo la pelota se acerca al setpoint y no se vuelve inestable.

---

## Prueba 8 — Pérdida, enlace y afinación

1. Tapá la pelota más de 200 ms en automático: el estado debe ser
   `PELOTA PERDIDA`, la placa debe nivelarse y el LED hacer el patrón de pérdida.
2. Desconectá el USB en automático: después de 1 s la placa debe nivelarse.
3. Reconectá: la GUI debe reconectar y reenviar modo/ganancias.
4. Ajustá primero **Kp**, después **Kd**, y por último un **Ki** pequeño.
5. Guardá con **W**. El firmware guarda ganancias y offsets; el setpoint y el
   modo no se guardan.
6. Repetí con la pelota en distintas posiciones y con la luz del aula.

**Pasa si:** no hay carreras, la placa nunca queda inclinada sin control y el
sistema vuelve al centro de forma repetible.

---

## Tabla de resultados

| Prueba | Fecha | Resultado | Observaciones |
|---|---|---|---|
| 1. Servos al centro | | | |
| 2. Límites 56–124° | | | |
| 3. ArUco con luz real | | | |
| 4. Asistente de ejes | | | |
| 5. Pelota/color | | | |
| 6. Manual | | | |
| 7. Automático Kp bajo | | | |
| 8. Pérdida/afinación | | | |

## Pendientes que requieren hardware

- Sentido real de los servos y flags `SERVO_INVERT_X/Y`.
- Centro mecánico y offsets reales.
- Calibración HSV con la cámara y la luz del aula.
- Error real en cm, repetibilidad y vibración.
- Detección de ArUco con brillo, reflejos y marcadores parcialmente tapados.
- Tiempo de recuperación tras pérdida de enlace.
- Ajuste final de Kp/Ki/Kd y prueba de setpoints en las cuatro esquinas.
- LED, buzzer y consumo de la fuente de 5 V.
