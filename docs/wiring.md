# Cableado y alimentación

## 1. Tabla de pines

| Elemento | Pin ESP32 DevKit | Notas |
|---|---|---|
| Señal servo X (MG90S) | GPIO 18 | PWM de 50 Hz, pulso 500–2400 µs |
| Señal servo Y (MG90S) | GPIO 19 | PWM de 50 Hz, pulso 500–2400 µs |
| LED de estado | GPIO 4 | LED + resistencia de 220–330 Ω a GND |
| Buzzer activo | GPIO 16 | Buzzer activo entre GPIO 16 y GND |
| GND de referencia | GND | Común con la fuente de los servos |

No se usa IMU en esta versión. Los cuatro marcadores ArUco son la referencia
visual de la placa.

## 2. Diagrama simplificado

```
                    +5 V fuente externa
                         │
              ┌──────────┴──────────┐
              │                     │
         [470–1000 µF]          MG90S X rojo   MG90S Y rojo
              │                     │              │
             GND ─────────────── servo GND ────────┘
              │
              ├──── ESP32 GND  (GND común obligatorio)
              │
GPIO 18 ────── señal servo X (naranja)
GPIO 19 ────── señal servo Y (naranja)

GPIO 4  ────── [220–330 Ω] ────── LED ────── GND
GPIO 16 ────── buzzer activo (+) ────── GND
```

## 2.1 Marcadores ArUco

- Pegá los marcadores impresos de `docs/marcadores_aruco/hoja_marcadores_A4.pdf`
  en las cuatro esquinas de la placa, sobre la cara que mira a la cámara.
- Orden visto desde la cámara: ID 0 arriba-izquierda, ID 1 arriba-derecha,
  ID 2 abajo-derecha, ID 3 abajo-izquierda.
- Por defecto cada centro está a **10 cm** del centro de la placa (2 cm del borde
  para un marcador de 4 cm). Si medís otra posición, cambiala en
  `pc/config.json` → `plate.marker_centers_cm`.
- Papel mate y buen contraste. Evitá que el marcador se despegue o se doble.
- El tamaño impreso tiene que ser 4 × 4 cm. El PDF se imprime al 100%.

## 3. Advertencia de alimentación

**No alimentes los dos MG90S desde el pin de 5 V del ESP32 ni desde el USB de la
PC.** Los servos consumen picos de corriente altos; eso puede reiniciar el ESP32 o
dañar el regulador de la placa.

- Usá una fuente externa de **5 V** capaz de entregar al menos 2 A para los dos
  servos.
- Uní el **GND de la fuente externa con el GND del ESP32**. Sin GND común la señal
  PWM no tiene referencia y los servos se comportan de forma errática.
- Soldá un capacitor electrolítico de **470 a 1000 µF** entre +5 V y GND lo más
  cerca posible de los servos, respetando la polaridad.
- La señal PWM va del GPIO del ESP32 al cable de **señal** del servo (normalmente
  naranja o amarillo). No conectes la señal a 5 V.
- Revisá que la fuente entregue 5 V estables con los dos servos moviéndose.
- El ESP32 normalmente se alimenta por USB. Para probar la pérdida de enlace serie
  sin apagar el microcontrolador, hace falta alimentarlo aparte (por ejemplo, por
  `5V`/`VIN` desde la fuente de 5 V, con el USB desconectado). Verificá el pinout de
  tu placa antes y no inyectes 5 V en el pin de 3,3 V.

## 4. Servos MG90S

- Rango de pulso usado: **500 a 2400 µs**.
- El firmware nunca manda un ángulo fuera de **56° a 124°**.
- Los valores `MECH_L_CM=8`, `MECH_R_CM=2`, centro 90°, límites y signos están en
  `firmware/include/config.h`.
- Los offsets de centro se pueden ajustar sin recompilar con `C` y guardar con `W`.
- Si un servo zumba y no se mueve, no fuerces la mecánica: revisá el tope, el
  cableado y la alimentación.

## 5. Mecánica y cámara

- Placa de cartón de 24 × 24 cm, con una superficie oscura mate para que la pelota
  naranja contraste y los marcadores se detecten.
- La pelota es de ping pong de 40 mm. El sistema **no** la hace rebotar: solo
  compensa la inclinación para llevarla al centro.
- La cámara debe ver los **cuatro marcadores completos**; si falta uno, no hay
  pose válida después de 0,5 s.
- La varilla de cada servo se une a 8 cm del centro, sobre el eje de ese servo.
- El celular se monta fijo a unos **40 cm** sobre la placa, con la cámara mirando
  hacia abajo y la placa completa dentro del cuadro. Evitá que se mueva durante las
  pruebas.
- Iluminación pareja; evitá reflejos fuertes sobre la placa y sombras en movimiento.
- En `HARDWARE_TEST.md` están las pruebas de montaje, sentido de los ejes y
  alimentación, en orden.

## 6. Lista de verificación antes de encender

- [ ] GND común entre ESP32 y fuente de servos.
- [ ] Capacitor de 470–1000 µF cerca de los servos, polarizado correctamente.
- [ ] Los servos reciben 5 V de la fuente externa, no del ESP32.
- [ ] Señales en GPIO 18 y 19.
- [ ] LED con resistencia en GPIO 4.
- [ ] Buzzer activo en GPIO 16.
- [ ] Ningún cable toca las partes móviles.
- [ ] La placa puede inclinarse sin forzar los topes.
- [ ] Los cuatro marcadores ArUco están pegados con el ID correcto y completos.
- [ ] La cámara del celular ve toda la placa desde arriba.
- [ ] Firmware cargado y monitor serie a 115200.
