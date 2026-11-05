# Plataforma estabilizadora de pelota

Proyecto escolar de **ball and plate**: una placa de cartón de 24 × 24 cm se
inclina con dos servos MG90S para llevar una pelota de ping pong naranja al
centro. La cámara de un celular mira la placa desde arriba; la PC detecta la
pelota y el ESP32 corre el PID en lazo cerrado.

```
Cámara del celular (DroidCam / Iriun / IP Webcam)
        │
        ▼
PC (Python + OpenCV)
  1. detecta los 4 marcadores ArUco
  2. calcula la homografía píxeles → cm
  3. detecta la pelota naranja dentro de la placa
        │  P,<x_cm>,<y_cm>,<found>  (USB 115200)
        ▼
ESP32: PID 100 Hz → 2 servos MG90S + LED + buzzer
        │  T,<...> telemetría 25 Hz
        ▼
PC: interfaz OpenCV + CSV
```

- El lazo de control vive en el **ESP32**, no en la PC.
- La PC manda la posición en **centímetros** a la frecuencia de la cámara
  (30–60 fps) y recibe telemetría a 25 Hz.
- **No hay IMU** en esta versión. La inclinación que se muestra es la comandada
  (`tilt_source = "command"`).
- La posición se obtiene de los **cuatro marcadores ArUco** de las esquinas. Ya
  no se marca una ROI a mano.
- Si no hay hardware, `python main.py --sim` ejecuta todo con cámara sintética y
  un ESP32 falso.
- Incluye instalador Windows, firmware precompilado y guía para pendrive.

> **Estado:** todo lo verificable sin hardware está probado. Este repositorio se
> desarrolló sin cámara, ESP32, servos, LED ni buzzer reales. Las pruebas físicas
> están en **[HARDWARE_TEST.md](HARDWARE_TEST.md)** y son obligatorias.

## Decisión de alcance de esta versión

El documento de Claude pedía tkinter + matplotlib, modo de 4 pestañas y
estimación de inclinación desde los marcadores. Para esta entrega se eligió una
versión **híbrida** más segura:

- Se conserva la interfaz **OpenCV** ya probada (video, overlay, teclas,
  trackbars y panel). No se usa tkinter.
- Se migró la visión a **ArUco + cm**.
- Se mantiene la calibración de color, centro de servos y asistente de ejes
  dentro de la misma ventana.
- `tilt_source` queda en `"command"`: la inclinación estimada con una cámara
  monocular sin calibración de intrínsecos no es confiable. Está marcada como
  TODO-HW.
- El asistente de ejes es **guiado** (observás para dónde rueda la pelota), no
  automático por marcadores.
- Se eliminó la IMU.

Estas diferencias están justificadas en **[PLAN.md](PLAN.md)**.

---

## Qué se verificó y qué falta

Verificado en Windows 11, Python 3.12 y OpenCV 5.0:

- `python -m pytest` en `pc/`: **85 pruebas pasan**.
- `pio run` en `firmware/`: compila para `esp32dev`.
- `pio test -e native`: **11 pruebas** de PID y protocolo pasan.
- `python main.py --sim`: abre la ventana, detecta los 4 ArUco y la pelota
  converge desde 6 cm en **≈1,25 s** (tolerancia 0,5 cm; límite 12 s).
- La hoja de marcadores se genera y se abre; se verificó el tamaño de impresión.
- El instalador offline y el flasheo en `--dry-run` se probaron.
- No se probó un ESP32, cámara, servo, LED ni buzzer reales.

Falta con hardware: sentido real de servos, centro mecánico, detección ArUco con
luz real, calibración HSV, ajuste de ganancias y fallback de enlace.

---

## Requisitos

**Hardware**

- ESP32 DevKit (placa `esp32dev`) y cable USB con datos.
- 2 servos MG90S, fuente externa de 5 V (≥2 A), capacitor de 470–1000 µF.
- Placa de 24 × 24 cm, pelota de ping pong naranja de 40 mm.
- Celular Android con DroidCam, Iriun o IP Webcam.
- Cuatro marcadores ArUco impresos (ver más abajo).

**PC**

- Windows 10/11, Python **3.10 o superior**.
- `pc/requirements.txt`: OpenCV contrib (incluye ArUco), NumPy, pyserial,
  pytest y matplotlib.
- PlatformIO **solo** para compilar/modificar el firmware. Para usar el binario
  precompilado no hace falta.

---

## Inicio rápido (Windows)

1. Ejecutá **`INSTALAR.bat`**. Crea `pc\.venv`, instala las dependencias y, si
   falta Python, ofrece abrir el instalador incluido en el paquete.
2. Conectá el ESP32 y ejecutá **`SUBIR_FIRMWARE.bat`**. Elegí el COM y confirmá.
3. Ejecutá **`ELEGIR_DISPOSITIVOS.bat`**. Elegí cámara/URL y puerto.
4. Ejecutá **`INICIAR.bat`** y seguí **[HARDWARE_TEST.md](HARDWARE_TEST.md)**.
5. Sin hardware, ejecutá **`PROBAR_SIN_HARDWARE.bat`**.

Los cinco botones son los cinco comandos para el usuario final. También se puede
usar PowerShell:

```powershell
.\INSTALAR.bat
.\PROBAR_SIN_HARDWARE.bat
.\SUBIR_FIRMWARE.bat
.\ELEGIR_DISPOSITIVOS.bat
.\INICIAR.bat
```

> En `cmd` se puede omitir el `.\`. Si copiás el proyecto a otra PC, copiá **toda
> la carpeta**, incluida `paquete/`, a una ubicación escribible antes de
> instalar. `pc\.venv`, `.pio` y `.git` no se copian.

---

## 1. Instalación manual (desarrollo)

1. Instalá Python 3.12 x64 marcando **Add python.exe to PATH**.
2. En PowerShell:

```powershell
cd plataforma-pelota\pc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r tools\requirements-flash.txt
```

3. Comprobá las importaciones:

```powershell
python -c "import cv2, numpy, serial; print(cv2.__version__); print(hasattr(cv2, 'aruco'))"
```

Debe imprimir una versión de OpenCV y `True`. Si imprime `False`, instalaste
`opencv-python` en lugar de `opencv-contrib-python`; desinstalá el primero e
instalá el segundo.

---

## 2. Firmware, PlatformIO y librerías

PlatformIO es la herramienta que descarga el core de Arduino para ESP32, el
compilador y las librerías, compila el firmware y genera el `.bin`. **No queda
dentro del ESP32.** El ESP32 solo ejecuta el firmware.

### ¿Qué librerías necesito?

| Librería | Quién la instala | Uso |
|---|---|---|
| Arduino core ESP32 | PlatformIO automáticamente | Framework |
| `ESP32Servo` 3.2.1 | PlatformIO automáticamente | Servos |
| `Wire` / `Preferences` | ya vienen en el core | I2C no usado / NVS |
| Unity | PlatformIO solo para tests | No va al ESP32 |
| `opencv-contrib-python` | instalador de la PC | ArUco + visión |
| `numpy`, `pyserial`, `pytest`, `matplotlib` | instalador | Visión, serial, tests |
| `esptool` | instalador | Grabar el firmware |

No hay que descargar ZIPs ni copiar librerías a mano.

### Opción A: usar el firmware precompilado (recomendado en la escuela)

`firmware/prebuilt/plataforma_pelota_esp32.bin` ya contiene bootloader, tabla de
particiones y aplicación. Se graba en `0x0` con `SUBIR_FIRMWARE.bat`, que usa
`esptool` y verifica el SHA256. **No requiere PlatformIO.**

Si la placa no se deja grabar, mantené presionado **BOOT** al comenzar y soltá
cuando termine la escritura.

### Opción B: compilar y subir desde PlatformIO

Con VS Code:

1. Instalá la extensión **PlatformIO IDE**.
2. Abrí la carpeta `firmware/`.
3. Esperá que descargue la plataforma y `ESP32Servo`.
4. Conectá la placa, elegí el puerto y usá **Upload**.
5. Abrí el monitor serie a **115200**.

O desde PowerShell:

```powershell
cd plataforma-pelota\firmware
pio run
pio run -t upload
pio device monitor -b 115200
```

También podés usar **`COMPILAR_Y_SUBIR_CON_PLATFORMIO.bat`**. La primera
compilación necesita internet para descargar el core y el compilador.

---

## 3. Marcadores ArUco (imprimir y pegar)

Los archivos listos para imprimir están en:

- **[hoja_marcadores_A4.pdf](docs/marcadores_aruco/hoja_marcadores_A4.pdf)**:
  hoja A4 con los IDs 0, 1, 2 y 3.
- **[hoja_marcadores_A4.png](docs/marcadores_aruco/hoja_marcadores_A4.png)**:
  vista previa.
- `aruco_0.png` … `aruco_3.png`: marcadores individuales.
- **[LEEME_MARCADORES.txt](docs/marcadores_aruco/LEEME_MARCADORES.txt)**.

**Imprimí al 100% en A4, sin “ajustar a la página”.** Cada cuadrado negro debe
medir **4,0 × 4,0 cm**. Recortá dejando 1 cm de margen blanco.

Orden visto desde la cámara:

```
        ID 0                         ID 1
   arriba-izquierda            arriba-derecha

        ID 3                         ID 2
   abajo-izquierda              abajo-derecha
```

Cada centro va a **10 cm** del centro de la placa (2 cm del borde de una placa
de 24 cm). Si los pegás en otra posición, corregí `plate.marker_centers_cm` en
`pc/config.json`.

Regenerar la hoja:

```powershell
python pc\tools\generate_aruco_sheet.py
```

La hoja usa el diccionario `DICT_4X4_50` y los IDs configurados. Si cambiás el
diccionario o el tamaño, actualizá también `pc/config.json`.

### Material y montaje

- Papel **mate**; si brilla, la cámara puede no detectarlo.
- Marcadores planos, sin dobleces ni cinta brillante encima.
- La cámara debe ver los **cuatro completos**.
- ID 0 arriba-izquierda, ID 1 arriba-derecha, ID 2 abajo-derecha, ID 3
  abajo-izquierda. Si el orden está mal, la placa se detecta torcida.
- La placa debe ser oscura y mate para contrastar con la pelota naranja.

### Cómo se calculan los centímetros

`markers.py` detecta los centros de los cuatro marcadores y calcula una
homografía desde píxeles a cm con origen en el centro de la placa. +X es a la
derecha de la imagen; +Y es hacia arriba. La misma homografía convierte el clic
del setpoint y dibuja los ejes.

Si falta un marcador, se conserva la última pose válida durante **0,5 s** y
después se reporta “placa no detectada”. El control recibe `found=0`.

---

## 4. Cámara del celular y selector

### DroidCam o Iriun

1. Instalá la app en el celular y el cliente en la PC.
2. Conectá por USB si es posible (menos latencia) o por Wi-Fi.
3. Iniciá la app y verificá que la PC vea la cámara virtual.
4. Ejecutá `ELEGIR_DISPOSITIVOS.bat` y elegí la cámara virtual; el índice
   suele ser 1 o 2.

### IP Webcam

1. En la app, iniciá el servidor y anotá `http://IP:8080`.
2. En el selector, elegí **URL** y escribí
   `http://IP:8080/video`.
3. Verificá que la PC y el celular estén en la misma red.

### Selector de dispositivos

- Se abre en el primer arranque real, con la tecla **D** o con
  `ELEGIR_DISPOSITIVOS.bat`.
- Lista índices de cámara, permite una URL y lista los puertos COM con su
  descripción.
- `AUTODETECTAR` prueba los puertos y busca el que responde `HELLO`.
- Al guardar, la app reinicia internamente para aplicar los cambios.

No hay vista previa dentro del selector: elegí el índice y comprobá el video en
la ventana principal. Si el índice no funciona, probá otro.

---

## 5. Uso de la interfaz

La interfaz es una sola ventana OpenCV con video, overlay, panel y trackbars.
No hay pestañas tkinter.

### Vista de prueba

- Video en vivo con la placa, IDs, ejes X/Y, pelota, setpoint y trayectoria.
- Panel: modo, estado, enlace, posición en cm, error, tilt, servos, ArUco,
  fps y latencia.
- Si no hay 4 marcadores, aparece `PLACA NO DETECTADA`.
- Presioná **C** para calibrar el color HSV dentro de la placa.
- Presioná **D** para cámara/puerto.

### Configuración

1. **Color:** `C`, ajustá H/S/V y guardá.
2. **Centro de servos:** `K`, movés los servos y guardás con `S` (envía `W`).
3. **Ejes:** `E`, el asistente inclina la placa y te guía para observar la
   pelota. Al final imprime los flags para `config.h`.
4. **Ganancias:** trackbars Kp/Ki/Kd; se envían en vivo con `G,B`.
5. **Guardar:** `W` guarda ganancias y offsets en el ESP32 y sincroniza el PID
   en `config.json`.

### Control

- `1` manual, `2` automático, `ESPACIO` paro de emergencia (manda `M,0`).
- Clic dentro de la placa: define el setpoint en cm y manda `S`.
- Flechas en manual: ±1° por pulsación, con límite ±8°.
- `Q` cierra.

### Teclas

| Tecla | Acción |
|---|---|
| `Q` | Salir. |
| `ESPACIO` | Paro de emergencia: `M,0`. |
| `1` | Modo manual. |
| `2` | Modo automático. |
| `C` | Calibrar color HSV. |
| `W` | Guardar ganancias y offsets en el ESP32. |
| `E` | Asistente de ejes guiado. |
| `K` | Calibrar centro de servos. |
| `D` | Elegir cámara/URL y puerto COM. |
| Flechas | Inclinar en manual. |
| Clic | Definir setpoint. |

---

## 6. Sistema de coordenadas y control

- Placa de 24 × 24 cm, origen en el centro, rango ±12 cm.
- `x > 0` a la derecha de la imagen; `y > 0` hacia arriba.
- El PID usa `error = setpoint − medición` en cm.
- Ganancias iniciales en **grados/cm**: `Kp=0.50`, `Ki=0.02`, `Kd=0.33`.
  No son las ganancias normalizadas 6/0.2/4 de la versión anterior; equivalen
  aproximadamente para 24 cm.
- La salida se satura a ±8° y tiene limitador de velocidad de 120°/s.
- Integral con anti-windup y reset al perder la pelota.
- Si no hay P válida por 200 ms: pelota perdida, rampa a nivel y LED/buzzer.
- Si no hay enlace por 1 s en automático: nivela.

El protocolo completo, campos de `T`, rangos y signos está en
**[docs/protocol.md](docs/protocol.md)**.

### `tilt_source`

En `pc/config.json`:

```json
"tilt_source": "command"
```

- `"command"`: la GUI muestra la inclinación comandada por el firmware. Es la
  opción validada.
- `"markers"`: queda como TODO-HW; requiere calibrar intrínsecos de la cámara y
  no se usa para el lazo en esta entrega.

---

## 7. Simulación

```powershell
python main.py --sim
```

o `PROBAR_SIN_HARDWARE.bat`.

La simulación:

- genera una placa con los cuatro ArUco;
- dibuja la pelota naranja;
- usa la misma detección HSV y homografía que la cámara real;
- implementa un FakeESP32 con el protocolo y el PID;
- integra la física `a = (5/7)·g·sin(tilt)` en cm/s².

La prueba de integración arranca a 6 cm del centro y exige |error| < 0,5 cm
durante 1 s. En este entorno converge en ≈1,25 s.

No valida servos, cámara, luz, rebotes ni calibración real.

---

## 8. Pruebas

Desde `pc/`:

```powershell
python -m pytest -q
```

Cubre, entre otras cosas:

- detección de los 4 ArUco en imágenes sintéticas con perspectiva;
- homografía píxel → cm con error < 0,2 cm;
- pose conservada 0,5 s y timeout;
- detección de pelota, ruido, brillo y máscara de placa;
- parser de protocolo con basura y telemetría de 11 campos;
- PID, anti-windup, servo/tilt y límites;
- integración cerrada con simulación.

Firmware:

```powershell
cd firmware
pio test -e native
pio run
```

---

## 9. Solución de problemas

### No detecta los marcadores

- Imprimí al 100% y comprobá que cada marcador mida 4 cm.
- Pegá los IDs en el orden correcto.
- Asegurate de que la cámara vea los cuatro completos y no estén tapados.
- Evitá brillos, sombras duras o marcadores doblados.
- En el panel debe decir `arUco 4/4`.
- Si el orden está mal, la pose sale torcida: volvé a pegar.

### La posición en cm está corrida

- Medí los centros de los marcadores y actualizá `plate.marker_centers_cm`.
- Verificá que la placa sea de 24 cm y que los marcadores estén planos.
- Si la cámara está muy inclinada, la homografía corrige la perspectiva, pero
  los marcadores deben verse completos.

### No detecta la pelota

- Presioná **C** y ajustá el rango HSV con la luz real.
- La pelota debe estar dentro del cuadrilátero de los marcadores.
- Revisá `min_area`, `max_area` y `min_circularity`.
- Evitá reflejos y sombras.

### El servo no se mueve o zumba

- Revisá la fuente externa de 5 V y el GND común.
- No alimentes los servos desde el ESP32.
- Verificá GPIO 18/19 y el pulso de 500–2400 µs.
- Ajustá el centro con **K**.
- Si el sentido está mal, usá **E** y recompilá `SERVO_INVERT_X/Y`.

### El puerto COM no aparece

- Instalá el driver CH340 o CP210x.
- Probá otro cable USB (de datos).
- Cerrá Arduino IDE o cualquier monitor serie que esté usando el puerto.
- En el selector, probá `AUTODETECTAR` o elegí el COM manualmente.

### `opencv-contrib-python` / ArUco

Si `import cv2; cv2.aruco` falla, tenés instalado `opencv-python`:

```powershell
python -m pip uninstall -y opencv-python opencv-contrib-python
python -m pip install opencv-contrib-python>=4.8.0
```

No instales los dos paquetes a la vez.

### La app se abre sin cámara

La ventana muestra “Esperando imagen”; el hilo de cámara reintenta. Revisá el
selector **D** o ejecutá `--sim`. No se bloquea.

---

## 10. Estructura del repositorio

```
plataforma-pelota/
├── INSTALAR.bat / INICIAR.bat / SUBIR_FIRMWARE.bat
├── ELEGIR_DISPOSITIVOS.bat / PROBAR_SIN_HARDWARE.bat
├── COMPILAR_Y_SUBIR_CON_PLATFORMIO.bat
├── PREPARAR_PENDRIVE.bat
├── LEEME_PRIMERO.txt
├── GUIA_PENDRIVE.md
├── HARDWARE_TEST.md
├── PLAN.md
├── docs/
│   ├── protocol.md
│   ├── wiring.md
│   └── marcadores_aruco/
│       ├── hoja_marcadores_A4.pdf
│       ├── hoja_marcadores_A4.png
│       ├── aruco_0.png ... aruco_3.png
│       └── LEEME_MARCADORES.txt
├── firmware/
│   ├── config.h / main.cpp / pid / protocol / status
│   ├── platformio.ini
│   ├── test/test_core/test_core.cpp
│   └── prebuilt/plataforma_pelota_esp32.bin
├── pc/
│   ├── main.py / camera.py / markers.py / vision.py
│   ├── serial_link.py / protocol.py / logger.py / sim.py
│   ├── gui.py / calibration.py / config.json
│   ├── devices.py
│   ├── tools/flash_firmware.py
│   ├── tools/generate_aruco_sheet.py
│   └── tests/
├── windows/
│   ├── instalar.ps1
│   ├── preparar_pendrive.ps1
│   └── compilar_y_subir.ps1
└── paquete/              (se genera con PREPARAR_PENDRIVE.bat)
```

---

## 11. Seguridad y alcance

- Los servos se limitan siempre a [56°, 124°] y la inclinación a ±8°.
- La fuente de los servos no sale del ESP32.
- La parada de emergencia es **ESPACIO**; al cerrar la GUI se manda `M,0`.
- Si el USB se cae, la placa se nivela después del timeout.
- No hay IMU; la inclinación mostrada es la comandada.
- El sistema no hace rebotar la pelota: solo estabiliza.
- Las pruebas con hardware real siguen pendientes.
