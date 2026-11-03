# Pruebas de hardware, en orden

Este proyecto se desarrolló sin acceso a cámara, ESP32, servos, LED, buzzer ni IMU.
Todo lo marcado con `TODO-HW:` en el código y todas las pruebas de este archivo
tienen que hacerse con el hardware real. **No saltees el orden**: cada prueba
habilita la siguiente.

## Antes de empezar

- [ ] Leíste `docs/wiring.md`.
- [ ] Fuente externa de 5 V para los servos, GND común y capacitor de 470–1000 µF.
- [ ] Instalaste las dependencias con `INSTALAR.bat` o el procedimiento manual.
- [ ] Grabaste el firmware con `SUBIR_FIRMWARE.bat` (o PlatformIO) y el monitor
      serie abre a 115200.
- [ ] Tenés a mano el comando `ESPACIO` (paro de emergencia) en la GUI.
- [ ] No hay nada frágil al lado de la placa que pueda caerse.
- [ ] La pelota se puede sacar y poner sin tocar los cables.

Para las pruebas con comandos manuales se puede usar el monitor serie de
PlatformIO (`pio device monitor`). Cada línea se termina con Enter.

---

## Prueba 1 — Servos al centro y arranque seguro

**Objetivo:** verificar el centro mecánico y que el firmware arranque apagado.

1. Sin pelota, encendé la fuente de los servos y conectá el ESP32 por USB.
2. Abrí el monitor serie y verificá que aparezca `HELLO,1.0.0`.
3. Mandá `H` y comprobá que responda `HELLO,1.0.0` y `OK,H`.
4. Observá la placa: debe quedar nivelada (servo 90° + offset) y el LED debe quedar
   apagado.
5. Esperá 5 segundos sin mandar `M,1` ni `M,2`. La placa no debe inclinarse.

**Pasa si:** los dos servos quedan quietos, la placa está razonablemente nivelada y
el estado en telemetría es 0 (`... ,0` al final de la línea `T`). Si está inclinada,
se corrige en la prueba 9 con la calibración de centro.

---

## Prueba 2 — Límites de servo (±34°), sin pelota

**Objetivo:** confirmar que los topes lógicos de 56° y 124° no fuerzan la mecánica.

1. Sacá la pelota y sostené la placa para que pueda moverse libremente.
2. Mandá `M,1` y después `V,56,56`.
3. Observá que los servos lleguen al tope sin zumbar ni chocar la estructura.
4. Mandá `V,124,124` y repetí la observación.
5. Mandá `V,0,0` y `V,300,300`: el firmware debe recortar a 56° y 124°, y no debe
   mover los servos más allá.
6. Mandá `M,0` para volver a nivel.

**Pasa si:** en ningún caso el servo supera mecánicamente los topes y no hay
trabas ni ruido de esfuerzo. Si choca antes de 56°/124°, corregí la mecánica o los
límites en `config.h`; no fuerces.

---

## Prueba 3 — Sentido de cada eje

**Objetivo:** elegir `SERVO_INVERT_X` y `SERVO_INVERT_Y`.

La convención del proyecto es que una inclinación positiva debe acelerar la pelota
hacia +X (derecha de la imagen) y hacia +Y (arriba de la imagen).

Opción A, con la GUI:

1. Antes de empezar, asegurate de que `simulation.servo.invert_x/y` en
   `config.json` coincidan con los `SERVO_INVERT_X/Y` que tiene compilado el
   firmware. El asistente usa esos valores como punto de partida.
2. Abrí la GUI.
3. Presioná `E` y seguí las instrucciones del asistente de ejes.
4. Anotá la recomendación que aparece en pantalla y en la terminal.
5. Cambiá `SERVO_INVERT_X` / `SERVO_INVERT_Y` en `firmware/include/config.h` y
   actualizá también el espejo en `config.json`.
6. Volvé a compilar/cargar y repetí la prueba hasta que la pelota acelere hacia
   la derecha/arriba con una inclinación positiva.

Opción B, con el monitor serie:

1. Mandá `M,1` y después `A,2,0`.
2. Mirá hacia dónde rueda la pelota:
   - Si rueda a la **derecha**, `SERVO_INVERT_X` debe quedar `false`.
   - Si rueda a la **izquierda**, `SERVO_INVERT_X` debe quedar `true`.
3. Mandá `A,0,0` y esperá que se detenga. Después `A,0,2`.
   - Si sube (hacia el fondo de la imagen), `SERVO_INVERT_Y` queda `false`.
   - Si baja (hacia el frente), queda `true`.
4. Mandá `M,0`, cambiá `config.h` si hace falta, recompilá y repetí.

**Pasa si:** la GUI manual y el lazo automático empujan la pelota en el sentido
correcto. No uses `control.invert_x`/`invert_y` de `config.json` para corregir el
sentido del servo; esas banderas son para la convención de la imagen. La GUI y el
firmware tienen inversiones distintas a propósito.

---

## Prueba 4 — Cámara real y ROI

**Objetivo:** capturar imagen estable y marcar la placa.

1. Montá el celular a unos 40 cm, centrado y fijo. Conectalo como webcam (ver
   README: DroidCam, Iriun o IP Webcam).
2. Ejecutá `ELEGIR_DISPOSITIVOS.bat` (o `INICIAR.bat` y después la tecla `D`) y
   elegí la cámara y el puerto COM. Guardá.
3. Ejecutá `INICIAR.bat` (o `python main.py` desde `pc/`).
4. Verificá que se vea el video, con fps en pantalla. Si no abre, probá otro
   índice de cámara con el selector.
5. Presioná `R` y hacé clic en las cuatro esquinas de la placa: superior izquierda,
   superior derecha, inferior derecha, inferior izquierda.
6. Aceptá con Enter. La ROI debe quedar dibujada y guardada en `config.json`.
7. Si la cámara está inclinada, activá `P` para usar perspectiva. El centro y los
   bordes deben seguir teniendo sentido al mover la pelota a cada esquina.
8. Cerrá y abrí la GUI para confirmar que la ROI persiste.

**Pasa si:** la GUI muestra la placa completa, fps estables (idealmente 30 o más),
la ROI queda dentro de la placa y la pelota se dibuja con un círculo verde cuando
se la ve.

---

## Prueba 5 — Detección de color con la luz real

**Objetivo:** calibrar HSV y descartar falsos positivos.

1. Poné la pelota naranja en el centro de la placa, con la iluminación habitual.
2. Presioná `C`.
3. Mové las trackbars Hmin/Hmax, Smin/Smax, Vmin/Vmax hasta que:
   - la pelota se vea blanca en la máscara de la derecha;
   - el fondo oscuro y los objetos del aula no aparezcan;
   - el círculo verde siga a la pelota.
4. Pasá la pelota por las cuatro esquinas y por el borde de la ROI.
5. Probá con la luz del aula encendida y apagada, y con una mano haciendo sombra
   (sin tapar la pelota).
6. Aceptá con Enter. El rango se guarda en `config.json`.

**Pasa si:** se detecta la pelota en toda la placa, sin falsos positivos, y el
centro detectado tiene un error visual menor a unos pocos píxeles. Si el aula tiene
otra fuente naranja, reducí el área máxima o el rango S/V.

---

## Prueba 6 — Lazo abierto en manual

**Objetivo:** comprobar movimientos, límites y parada sin PID.

1. Con la pelota quieta o sin ella, presioná `1` (manual).
2. Movete con las flechas y observá la placa:
   - flecha derecha debe inclinar para mover la pelota a la derecha;
   - flecha izquierda, al revés;
   - flecha arriba debe inclinarla para que la pelota suba en la imagen;
   - flecha abajo, al revés.
3. Aumentá la inclinación hasta el límite (8°). La placa no debe pasar de allí.
4. Presioná `ESPACIO`: debe ir a modo apagado y nivelarse en una rampa corta.
5. Repetí con una pelota y comprobá que no haya golpes ni rebotes.

**Pasa si:** los sentidos son correctos, no hay vibración fuerte, los topes se
respetan y la parada de emergencia nivela la placa.

---

## Prueba 7 — Lazo cerrado con Kp bajo

**Objetivo:** cerrar el lazo sin riesgo de que la pelota salga despedida.

1. Poné la pelota en el centro y el setpoint en el centro (clic en el centro).
2. En las trackbars, bajá las ganancias a algo conservador:
   `Kp = 1.5`, `Ki = 0.0`, `Kd = 0.0` (recordá que están multiplicadas por 100).
3. Presioná `2` (automático). Debe sonar un pitido corto.
4. Mové suavemente la placa o la pelota y observá si el sistema corrige.
5. Si la corrección va para el lado contrario, volvé a la prueba 3 y corregí el
   signo. Si oscila mucho, reducí Kp y presioná `ESPACIO`.
6. Aumentá Kp de a poco hasta que la pelota empiece a corregir con decisión.

**Pasa si:** la pelota no se cae, el estado pasa a 3 (estabilizando), y el sistema
empuja hacia el centro. No sigas si el sentido es incorrecto.

---

## Prueba 8 — Ajuste fino del PID

**Objetivo:** encontrar ganancias aceptables para el hardware real.

Empezá con Kp bajo y seguí este orden:

1. **Kp:** subí hasta que la pelota responda rápido sin oscilar de forma sostenida.
2. **Kd:** agregá amortiguación hasta que las oscilaciones desaparezcan; si los
   servos vibran o zumban, bajá Kd o revisá la alimentación.
3. **Ki:** agregá un valor chico para eliminar el error de posición lento. Si la
   pelota se vuelve lenta o inestable, bajá Ki.
4. Probá el setpoint en el centro y en distintos puntos con clics.
5. Empujá la pelota suavemente y soltala.
6. Tapá la pelota con la mano: debe pasar a perdida, nivelar la placa y sonar el
   aviso largo después de 2 s.
7. Cuando estés conforme, presioná `W`. Se guardan las ganancias y offsets en el
   ESP32 y se sincronizan las ganancias en `config.json`.

**Pasa si:** la pelota queda dentro de la placa, vuelve al centro después de una
perturbación razonable y no hay vibración continua. Las ganancias de la simulación
**no** son las definitivas.

---

## Prueba 9 — IMU, LED, buzzer y fallback de enlace

**Objetivo:** cerrar las pruebas de sensores/periféricos y seguridad.

### IMU

1. Cambiá `USE_IMU` a `1` en `firmware/include/config.h` (si está conectada) y
   recompilá.
2. Abrí el monitor serie o la GUI y verificá que `roll` y `pitch` en la telemetría
   cambien al inclinar la placa. No deben usarse para el control.
3. Volvé a `USE_IMU=0` si no la vas a dejar conectada.

### LED

Con la placa quieta y el monitor serie abierto:

| Estado | LED esperado |
|---|---|
| apagado 0 | apagado |
| manual 1 | parpadeo lento |
| buscando 2 | parpadeo rápido |
| estabilizando 3 | fijo |
| perdida 4 | doble parpadeo |

### Buzzer

- Al pasar de apagado/manual a automático: pitido corto.
- Pelota perdida durante más de 2 s: pitido largo.

### Fallback de enlace

**Atención:** si el ESP32 se alimenta solo por USB, desenchufar el USB apaga el
microcontrolador y la placa **no puede** nivelarse. Para esta prueba hay que cortar
solo los datos conservando la alimentación del ESP32. Algunas formas:

- Alimentar el ESP32 desde la fuente de 5 V por el pin `5V`/`VIN` de la placa y usar
  el USB solo para datos. Consultá el pinout de tu DevKit y no conectes 5 V al pin
  de 3,3 V.
- Usar un cable USB de solo alimentación para mantener el ESP32 encendido y otro
  cable/canal de datos que se pueda desconectar (no todos los cables lo permiten).
- Hacer que la PC deje de mandar comandos (por ejemplo, cerrando la aplicación)
  mientras el ESP32 sigue alimentado por una fuente externa.

Pasos:

1. En automático con la pelota visible y el ESP32 alimentado aparte, cortá **solo la
   comunicación serie**.
2. Cronometrá cuánto tarda la placa en ir a nivel. Debe ser **menos de 1,5 s**.
3. Restablecé la comunicación. La PC debe reconectar sola, reenviar modo y ganancias,
   y reanudar la telemetría.
4. Repetí presionando `ESPACIO` y comprobando que el modo apagado no se abandona
   solo.

**Pasa si:** todos los patrones coinciden, el fallback nivela a tiempo y el sistema
no entra en automático sin un `M,2` explícito.

---

## Registro de resultados

Completá este registro con tus valores reales:

| Prueba | Fecha | Resultado | Observaciones |
|---|---|---|---|
| 1. Centro y arranque | | | |
| 2. Límites 56–124° | | | |
| 3. Sentido de ejes | | | |
| 4. Cámara y ROI | | | |
| 5. Color HSV | | | |
| 6. Manual | | | |
| 7. Kp bajo | | | |
| 8. Afinación | | | |
| 9. IMU/LED/buzzer/fallback | | | |

Ganancias finales de hardware:

```
Kp = _____    Ki = _____    Kd = _____
Offsets: X = _____°   Y = _____°
SERVO_INVERT_X = _____   SERVO_INVERT_Y = _____
```
