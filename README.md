# Plataforma estabilizadora de pelota

Proyecto escolar de **ball and plate**: una placa de cartón de 24 × 24 cm se
inclina con dos servos MG90S para llevar una pelota de ping pong al centro. La
pelota no rebota: el sistema solo estabiliza. La cámara de un celular detecta la
pelota en la PC y un ESP32 corre el PID en lazo cerrado.

```
Cámara del celular
       │  DroidCam / Iriun / IP Webcam
       ▼
PC (Python/OpenCV): detecta HSV, normaliza la posición, la manda por USB
       │  P,<x>,<y>,<found>
       ▼
ESP32: PID 100 Hz ──> 2 servos MG90S
       │                 LED + buzzer
       │                 IMU opcional (solo telemetría)
       └── T,<...> telemetría 25 Hz ──> PC (GUI + CSV)
```

- El lazo de control vive en el **ESP32**, no en la PC.
- La PC manda una posición a la frecuencia de la cámara (30–60 fps) y recibe
  telemetría a 25 Hz.
- Si no hay hardware, `python main.py --sim` ejecuta todo el flujo con una cámara
  sintética y un ESP32 falso.
- La aplicación permite **elegir cámara, URL de stream y puerto COM** desde una
  ventana propia (primer inicio, tecla `D` o `ELEGIR_DISPOSITIVOS.bat`).
- Incluye **instalador Windows** (`INSTALAR.bat`), firmware precompilado y una
  guía para llevarlo todo en un pendrive: `GUIA_PENDRIVE.md`.

> **Importante:** este repositorio se desarrolló sin cámara, ESP32, servos, LED,
> buzzer ni IMU. Todo lo que necesita hardware está marcado con `TODO-HW:` y se
> prueba a mano siguiendo `HARDWARE_TEST.md`. La simulación valida la lógica, el
> protocolo y la integración, **no** el ajuste real de ganancias.

---

## Qué se verificó y qué falta

Verificado en este entorno (Windows 11, Python 3.12, OpenCV 5.0, PlatformIO 6.2):

- `python -m pytest` en `pc/`: **82 pruebas pasan**.
- `pio run` en `firmware/`: compila para `esp32dev`.
- `pio run` con `USE_IMU=1`: también compila.
- `pio test -e native`: **11 pruebas** de PID y protocolo pasan.
- `python main.py --sim`: abre la ventana y la pelota converge desde 0,5. La
  prueba automática mide **≈1,2 s** para entrar en tolerancia y exige menos de 12 s.
- Logger CSV y `tools/plot_log.py --save`, probados.
- Selector visual de cámara/COM abierto e inspeccionado (`--setup-devices`).
- Instalador probado en modo **offline** con el paquete de `paquete/wheels`;
  creó el entorno virtual, instaló OpenCV/NumPy/pyserial/esptool y verificó el
  SHA256 del firmware.
- Herramienta de flasheo probada con `--dry-run` (sin hardware real).

Falta verificar con hardware (ver `HARDWARE_TEST.md`): sentido real de servos,
centro mecánico, cámara/luz real, ajuste final de Kp/Ki/Kd, LED, buzzer, IMU y
fallback de USB.

---

## Requisitos

**Obligatorio**

- Windows 10 u 11 (las instrucciones son para Windows; el código Python es
  multiplataforma salvo la elección de backend DirectShow).
- Python **3.10 o superior**.
- ESP32 DevKit (placa `esp32dev`) y cable USB con datos.
- 2 servos MG90S, fuente externa de 5 V, capacitor de 470–1000 µF y cables.
- Celular Android con una app que lo convierta en webcam: DroidCam, Iriun o IP
  Webcam, o cualquier stream que abra OpenCV.
- Placa de 24 × 24 cm, pelota de ping pong naranja, mecánica de 8 cm / 2 cm.

**Software**

- Windows 10/11 con PowerShell (viene incluido).
- Python 3.10 o superior; para el paquete offline, Python 3.12 x64.
- PlatformIO **solo si vas a compilar/modificar el firmware**. Para usar el
  firmware precompilado no hace falta.
- Dependencias de `pc/requirements.txt` y `pc/tools/requirements-flash.txt`.
- No se necesita GPU.

---

## Inicio rápido (Windows)

La forma recomendada para el usuario es el instalador:

1. Ejecutá **`INSTALAR.bat`**. Crea `pc\.venv` e instala todo (offline si existe
   `paquete\wheels`). Si no encuentra Python, ofrece abrir el instalador incluido
   en `paquete\instaladores` y continúa después de instalarlo.
2. Conectá el ESP32 y ejecutá **`SUBIR_FIRMWARE.bat`**. Elegí el COM y confirmá.
3. Ejecutá **`ELEGIR_DISPOSITIVOS.bat`**. Elegí cámara/URL y puerto.
4. Ejecutá **`INICIAR.bat`** y seguí `HARDWARE_TEST.md`.
5. Sin hardware, ejecutá **`PROBAR_SIN_HARDWARE.bat`**.

Los cinco botones son los mismos “cinco comandos” para el usuario final; no hay
que abrir PowerShell ni escribir rutas. El detalle para llevar todo en un
pendrive está en **[GUIA_PENDRIVE.md](GUIA_PENDRIVE.md)**.

> Si ya preparaste el paquete offline con `PREPARAR_PENDRIVE.bat`, copiá toda la
> carpeta del proyecto, incluida `paquete/`. En la escuela, copiá la carpeta a una
> ubicación escribible (por ejemplo el Escritorio) antes de instalar. Si no
> preparaste el paquete, `INSTALAR.bat` descarga las dependencias desde internet.

---

## 1. Instalación manual (alternativa para desarrollo)

El instalador `.bat` es la opción recomendada. Esta sección queda para quien
prefiera una terminal o esté desarrollando.

### 1.1 Python y entorno virtual

1. Descargá Python desde <https://www.python.org/downloads/windows/>. En el
   instalador marcá **Add python.exe to PATH**.
2. Abrí **PowerShell** y comprobá:

   ```powershell
   python --version
   ```

   Debe decir 3.10 o mayor. Si `python` no se reconoce, probá `py --version` y
   reinstalá marcando PATH.

3. Entrá a la carpeta de la PC y creá el entorno virtual:

   ```powershell
   cd plataforma-pelota\pc
   python -m venv .venv
   ```

4. Activá el entorno e instalá dependencias (incluye `esptool` para grabar el
   firmware):

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt -r tools\requirements-flash.txt
   ```

   Si PowerShell bloquea el script de activación, ejecutá solo para esta sesión:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   ```

   y volvé a activar. También podés usar `cmd` y `.venv\Scripts\activate.bat`.

5. Cada vez que abras una terminal nueva para usar el proyecto, activá de nuevo
   `.\.venv\Scripts\Activate.ps1` antes de ejecutar `python`.

> `matplotlib` está en `requirements.txt` solo por comodidad; es opcional y se usa
> únicamente en `tools/plot_log.py`.

---

## 2. PlatformIO y cómo subir el firmware

### ¿Qué es PlatformIO y por qué se usa?

PlatformIO es la herramienta de compilación. Descarga el core de Arduino para
ESP32, el compilador, la librería `ESP32Servo` y arma el archivo `.bin`. Después
lo sube por USB. No es un programa que quede en el ESP32 ni algo que la placa
ejecute: el ESP32 solo corre el firmware compilado.

Se eligió PlatformIO porque:

- deja las librerías y versiones fijadas en `firmware/platformio.ini`;
- permite los tests nativos del PID y del protocolo;
- evita instalar librerías a mano en Arduino IDE;
- el usuario final **no lo necesita** para usar el firmware ya compilado.

**En la PC de la escuela:** usá `SUBIR_FIRMWARE.bat`. Ese botón graba
`firmware/prebuilt/plataforma_pelota_esp32.bin` con `esptool` y no depende de
PlatformIO. Es la opción pensada para el pendrive.

**En la PC de desarrollo (o si cambiás `config.h`):** compilá con PlatformIO.
El proyecto ya pide automáticamente la única librería externa necesaria
(`ESP32Servo 3.2.1`); no hay que descargar ZIPs.

### Librerías necesarias

| Parte | Librería | Cómo se obtiene |
|---|---|---|
| Firmware | Arduino core ESP32 | PlatformIO automáticamente |
| Firmware | `ESP32Servo` 3.2.1 | PlatformIO automáticamente, declarada en `platformio.ini` |
| Firmware | `Wire`, `Preferences` | Incluidas en el core de ESP32 |
| PC | OpenCV, NumPy, pyserial, pytest, matplotlib | `INSTALAR.bat` o `requirements.txt` |
| PC / flasheo | `esptool` | `INSTALAR.bat` o `tools/requirements-flash.txt` |

### Subir con el firmware precompilado (recomendado)

**`SUBIR_FIRMWARE.bat`**

El binario ya contiene bootloader, tabla de particiones y aplicación. Se escribe
en `0x0` con esptool. El script pregunta el puerto COM y verifica el SHA256.

### Subir compilando el código fuente

Desde VS Code: abrí `firmware/`, esperá que PlatformIO descargue la plataforma y
usá **Upload** en la barra inferior.

Desde PowerShell:

```powershell
cd plataforma-pelota\firmware
pio run -t upload
```

O ejecutá **`COMPILAR_Y_SUBIR_CON_PLATFORMIO.bat`**. Este último es solo para
desarrollo y requiere PlatformIO instalado; la primera compilación necesita
internet para descargar el core/compilador.

### Opción A: VS Code (desarrollo)

1. Instalá **Visual Studio Code**.
2. En Extensiones, buscá **PlatformIO IDE** e instalalo. Esperá a que termine de
   instalar sus herramientas.
3. En VS Code, **File → Open Folder** y abrí `plataforma-pelota\firmware`.
4. Esperá a que PlatformIO descargue la plataforma `espressif32` y la librería
   `ESP32Servo` (la primera vez puede tardar varios minutos).
5. Conectá el ESP32 por USB.
6. En la barra inferior de PlatformIO, elegí el entorno `esp32dev` y usá
   **Upload** (flecha hacia la derecha). También podés abrir PlatformIO Home →
   Project Tasks → esp32dev → Upload.
7. Abrí el monitor serie a **115200**. Deberías ver `HELLO,1.0.0`.

### Opción B: línea de comandos (desarrollo)

Instalá PlatformIO Core con pip (dentro o fuera del venv, pero dejalo disponible):

```powershell
python -m pip install platformio
```

Luego:

```powershell
cd plataforma-pelota\firmware
pio run
pio run -t upload
pio device monitor -b 115200
```

Si la subida falla:

- Probá bajar `upload_speed` de 460800 a 115200 en `firmware/platformio.ini`.
- Cerrá Arduino IDE, el monitor serie de PlatformIO o cualquier programa que tenga
  el COM abierto.
- Verificá que el cable USB sea de datos, no solo de carga.
- Instalá el driver CH340 o CP210x según el chip de tu placa.
- Mantené presionado **BOOT** al empezar a subir y soltalo cuando la consola diga
  "Connecting..." si la placa no entra sola en modo bootloader.
- En algunos ESP32 hay que mantener **EN/RESET** un instante.

El firmware arranca en **modo apagado** y no se mueve hasta recibir `M,1` o `M,2`.
La PC envía `M,0` al iniciar por seguridad; recién cuando presiones `2` en la GUI se
activa el control automático.

### Tests del firmware

```powershell
cd plataforma-pelota\firmware
pio test -e native
```

No requiere la placa: usa el compilador de la PC y el entorno `native` con Unity.
Prueban el PID y el parser de protocolo.

### Botones/instalador de Windows

| Archivo | Qué hace |
|---|---|
| `INSTALAR.bat` | Crea el entorno virtual, instala las dependencias, verifica el firmware y crea un acceso directo. Usa `paquete\wheels` si existe (sin internet). |
| `INICIAR.bat` | Abre la aplicación real. |
| `PROBAR_SIN_HARDWARE.bat` | Abre la simulación (`--sim`). |
| `ELEGIR_DISPOSITIVOS.bat` | Abre el selector de cámara, URL y COM. |
| `SUBIR_FIRMWARE.bat` | Graba el firmware precompilado con esptool, sin PlatformIO. |
| `COMPILAR_Y_SUBIR_CON_PLATFORMIO.bat` | Compila el código actual y lo sube; requiere PlatformIO. |
| `PREPARAR_PENDRIVE.bat` | Prepara `paquete/` con todas las librerías y el instalador de Python para usar en la escuela sin internet. |

**Para la escuela:** en una PC con internet ejecutá `PREPARAR_PENDRIVE.bat`, copiá
la carpeta completa al pendrive y seguí **[GUIA_PENDRIVE.md](GUIA_PENDRIVE.md)**.
En la PC de la escuela no hace falta PlatformIO si solo vas a usar el firmware
precompilado.

---

## 3. Cableado y alimentación

Leé **`docs/wiring.md`** antes de conectar nada. Resumen:

| Elemento | GPIO |
|---|---|
| Servo X | 18 |
| Servo Y | 19 |
| LED | 4 |
| Buzzer activo | 16 |
| MPU6050 SDA (opcional) | 21 |
| MPU6050 SCL (opcional) | 22 |

**No alimentes los servos desde el ESP32.** Usá una fuente de 5 V aparte, uní los
GND y poné un capacitor de 470–1000 µF cerca de los servos. Los pines de los
servos van a 5 V, GND y la señal al GPIO.

La cámara del celular debe quedar fija a unos 40 cm, mirando la placa completa desde
arriba.

---

## 4. Conectar el celular como cámara

La PC acepta dos formas de cámara: **índice de OpenCV** (0, 1, 2...) o **URL de
stream**.

### Opción A: DroidCam

1. Instalá la app DroidCam en el celular y el cliente DroidCam en la PC desde el
   sitio oficial.
2. Conectá celular y PC por USB o por el mismo Wi-Fi.
3. Abrí DroidCam y seguí las instrucciones de la app.
4. En la PC, seleccioná la cámara virtual de DroidCam.
5. Probá con `python main.py --camera 1` (el índice puede ser 0 o 1, según la PC).

### Opción B: Iriun Webcam

1. Instalá Iriun en el celular y en la PC.
2. Conectá ambos al mismo Wi-Fi o por USB, según la app.
3. La cámara virtual aparece como un índice de OpenCV.

### Opción C: IP Webcam (URL)

1. Instalá IP Webcam en el Android y tocá "Iniciar servidor".
2. Anotá la URL que muestra, por ejemplo `http://192.168.0.50:8080/video`.
3. Ejecutá:

   ```powershell
   python main.py --camera http://192.168.0.50:8080/video
   ```

   También podés dejar esa URL en `camera.source` de `config.json`.

Si el stream se ve con mucha latencia, preferí USB (DroidCam/Iriun) o bajá la
resolución/fps en la app. IP Webcam y DroidCam tienen más latencia por Wi-Fi.

### Configurar resolución y fps

En `config.json`:

```json
"camera": {
  "source": 0,
  "width": 640,
  "height": 480,
  "fps": 60,
  "fourcc": "MJPG",
  "backend": "dshow"
}
```

`source` puede ser un número o una URL. `width`, `height` y `fps` son pedidos a la
cámara; si el celular no los soporta, entrega lo que pueda. La GUI muestra los fps
reales.

---

## 5. Seleccionar cámara y puerto COM

### Selector dentro de la aplicación

La app tiene una ventana propia de configuración:

- Se abre **sola en el primer arranque real**.
- Se puede abrir cuando quieras con la tecla **`D`** o ejecutando
  **`ELEGIR_DISPOSITIVOS.bat`**.
- Muestra los índices de cámara (`0`, `1`, `2`, ...), un campo para una **URL**
  de IP Webcam/RTSP y la lista de puertos COM detectados (más
  **AUTODETECTAR**).

Cómo usarla:

1. Hacé clic en una cámara o en la fila de URL. Si elegís URL, presioná `U`,
   escribí la dirección y Enter para terminar de editarla.
2. Elegí el puerto serial, o dejá **AUTODETECTAR**.
3. Presioná **ENTER** para guardar. La aplicación se reinicia automáticamente
   con la cámara y el puerto nuevos.
4. `R` actualiza la lista de puertos; `ESC` cancela.

El selector **no prueba** las cámaras para no bloquearse ni chocar con la cámara
en uso. Si un índice no abre, elegí otro. La app muestra `SIN ENLACE` o
`Esperando imagen` si el dispositivo no está disponible.

### Puerto COM manual

1. Conectá el ESP32 por USB.
2. Abrí el **Administrador de dispositivos** de Windows → **Puertos (COM y LPT)**.
   Debería aparecer algo como `Silicon Labs CP210x (COM5)` o `USB-SERIAL CH340
   (COM3)`.
3. Anotá el número de COM.
4. Por defecto `config.json` tiene `"port": ""` y `"auto_detect": true`, así que la
   PC prueba los puertos y elige el que responde `HELLO`. Si querés fijarlo:

   ```json
   "serial": { "port": "COM5", "baud": 115200, "auto_detect": true }
   ```

   Si hay un solo ESP32, la autodetección suele ser suficiente. Si no encuentra el
   puerto, revisá driver/cable o elegí el COM con el selector.

---

## 6. Primera ejecución de la PC

La forma más simple es doble clic en `INICIAR.bat`. Para desarrollo manual, desde
`pc/` con el venv activado:

```powershell
python main.py
```

Se abre una ventana de OpenCV. Si no hay cámara o ESP32, la ventana igual abre y
reintenta; es útil para probar teclas y ver errores.

1. Si es el primer arranque real, aparece el **selector de cámara y COM**.
   Elegí los dispositivos y guardá.
2. Verificá que aparezca el video.
3. Presioná `R` y marcá las cuatro esquinas de la placa.
4. Presioná `C` y calibrá el color naranja.
5. Opcional: `P` activa/desactiva la perspectiva.
6. Los trackbars Kp/Ki/Kd están abajo o arriba del video, según la versión de
   OpenCV. Empiezan con los valores de `config.json`.
7. Presioná `1` para manual. Con las flechas incliná la placa y comprobá los
   sentidos.
8. Recién después de la prueba de ejes, presioná `2` para automático.

La tecla **`D`** vuelve a abrir el selector en cualquier momento; al guardar, la
app se reinicia sola con la nueva cámara/puerto.

### Teclas de la GUI

| Tecla | Acción |
|---|---|
| `Q` | Salir (manda `M,0` al cerrar). |
| `ESPACIO` | Parada de emergencia: `M,0` y placa nivelada. |
| `1` | Modo manual. |
| `2` | Modo automático. |
| `C` | Calibrar color HSV. |
| `R` | Definir ROI con 4 clics. |
| `W` | Guardar ganancias y offsets en el ESP32 (`W`) y sincronizar ganancias en `config.json`. |
| `↑ ↓ ← →` | Mover la inclinación en modo manual (±8°). |
| Clic izquierdo | Definir un nuevo setpoint. |
| `E` | Asistente de ejes (recomienda `SERVO_INVERT_*` para `config.h`). |
| `K` | Calibrar el centro de los servos con `V` y `C`. |
| `D` | Elegir cámara/URL y puerto COM; guarda y reinicia. |
| `P` | Activar/desactivar perspectiva de la ROI. |

La barra superior muestra estado, enlace, posición, error, inclinación, ángulos de
servo, IMU, fps de cámara/visión, tiempo de procesamiento y latencia.

### Estados de la telemetría

| Código | Estado | LED |
|---|---|---|
| 0 | Apagado | Apagado |
| 1 | Manual | Parpadeo lento |
| 2 | Buscando | Parpadeo rápido |
| 3 | Estabilizando | Fijo |
| 4 | Pelota perdida | Doble parpadeo |

La pérdida ocurre si la pelota no se ve o pasan 200 ms sin una posición válida. La
placa vuelve a nivel en rampa y, después de 2 s perdida, suena un pitido largo.

---

## 7. Calibración paso a paso

Las herramientas son de ventana; se controlan con teclado y mouse. La cámara real y
la luz cambian todos los valores, así que hacé estas calibraciones con el montaje
final.

### 7.1 ROI: qué es y cómo se marca

**ROI** significa *Region Of Interest* (región de interés): el rectángulo o
cuadrilátero que encierra la placa en la imagen. La detección de color solo
analiza esa zona, así que un objeto naranja fuera de la placa no se confunde con
la pelota. Además, el centro de la ROI se usa como origen para normalizar la
posición de la pelota entre -1 y +1:

```
Imagen de la cámara
┌──────────────────────────────────────────┐
│                                          │
│      4 esquinas de la ROI                │
│      (amarillo)                          │
│        ┌──────────────────┐              │
│        │   ● pelota       │  centro (0,0)
│        │        +         │              │
│        └──────────────────┘              │
│                                          │
└──────────────────────────────────────────┘
```

La detección de color queda limitada a la ROI; el centro de la ROI es el
setpoint por defecto y +Y es hacia arriba de la imagen.

1. Presioná `R`.
2. Hacé clic en las cuatro esquinas de la **placa**, en orden:
   arriba-izquierda → arriba-derecha → abajo-derecha → abajo-izquierda.
3. Enter acepta, Esc cancela, Backspace borra el último punto.
4. La ROI se guarda en `config.json` como coordenadas normalizadas.

Si la placa no se ve rectangular porque la cámara está inclinada, activá `P` para
usar perspectiva. La detección seguirá siendo sobre el video original, pero la
normalización corrige la deformación.

### 7.2 Color

1. Presioná `C`.
2. Mové las trackbars Hmin/Hmax, Smin/Smax y Vmin/Vmax hasta aislar la pelota.
3. Del lado derecho se ve la máscara; del izquierdo, la detección.
4. Enter o `S` guarda en `config.json`; Esc o `Q` cancela.

El rango inicial es H 5–20, S 120–255, V 120–255 (naranja), pero la iluminación real
manda. Si detecta objetos del aula, reducí el área máxima o el rango de saturación.

### 7.3 Sentido de los ejes

La convención es: `tilt_x > 0` acelera la pelota hacia la derecha de la imagen;
`tilt_y > 0`, hacia arriba. El montaje puede invertir los servos.

1. Presioná `E` (asistente de ejes). También se puede hacer a mano en modo manual:
   `A,2,0` y observar.
2. Si con la inclinación positiva la pelota rueda a la **izquierda**, el eje X está
   invertido. Si rueda hacia **abajo**, el eje Y está invertido.
3. El asistente parte de los flags actuales guardados en
   `simulation.servo.invert_x/y` de `config.json` (que deben ser espejo de
   `config.h`) y te muestra los valores absolutos recomendados. Por ejemplo:

   ```c
   #define SERVO_INVERT_X false
   #define SERVO_INVERT_Y true
   ```

4. Volvé a compilar y cargar. Actualizá también
   `simulation.servo.invert_x/y` en `config.json` para que el espejo siga
   coincidiendo. Repetí la prueba si hace falta.

El asistente no puede cambiar esos valores solo porque son constantes de
compilación. Tampoco uses `control.invert_x`/`control.invert_y` de `config.json`
para este problema: esas banderas corrigen la orientación de la imagen, no la
dirección del servo.

### 7.4 Centro de los servos

El centro de 90° puede no coincidir con la placa nivelada por tolerancias
mecánicas. La GUI permite corregirlo usando los comandos `V` y `C`:

1. Presioná `K` con el ESP32 conectado y sin pelota.
2. Mové las trackbars de ángulo crudo X/Y hasta que la placa quede nivelada de
   verdad.
3. Enter aplica el offset con `C`; `S` aplica y guarda con `W`; Esc cancela.
4. Al salir se manda `M,0` y la placa vuelve a nivel usando el offset nuevo.

El offset se guarda en la NVS del ESP32 y sobrevive a reinicios. El firmware limita
los offsets a ±20° y los ángulos finales a [56°, 124°].

### 7.5 Setpoint

Un clic dentro de la ROI define el nuevo setpoint. La cruz roja lo muestra. El
setpoint no se guarda en el ESP32 ni en `config.json`; al reiniciar vuelve a
`(0,0)` o al valor de `control.setpoint_x/y` de `config.json`.

---

## 8. Afinar el PID

El PID corre en el ESP32. La GUI manda `G,B,<kp>,<ki>,<kd>` al mover los trackbars.
Las ganancias de partida son Kp=6, Ki=0.2, Kd=4, pero son solo un punto de partida.

**Para hardware real, empezó bajo:** Kp≈1.5, Ki=0, Kd=0.

Orden recomendado:

1. **Primero Kp.** Subilo hasta que la pelota responda rápido sin oscilar de forma
   sostenida. Si oscila, bajá.
2. **Después Kd.** Agregá amortiguación hasta que las oscilaciones desaparezcan. Si
   los servos vibran o zumban, bajá Kd y revisá la alimentación.
3. **Al final Ki.** Agregá un valor chico para eliminar el error lento de posición.
   Si se vuelve lento o inestable, bajá Ki.
4. Cuando estés conforme, presioná `W`: se guardan ganancias y offsets en el ESP32.
   También se actualizan las ganancias en `config.json` para que la próxima sesión
   empiece con esos valores.
5. Tené en cuenta que la PC manda sus ganancias al conectar. Si cambiás las
   ganancias con el monitor serie y no actualizás `config.json`, la próxima vez que
   abras la GUI volverá a mandar las de la configuración.

Los límites aceptados por firmware son Kp [0,50], Ki [0,20], Kd [0,50]. Los valores
de la simulación no son los valores del hardware real.

### Parada segura

- `ESPACIO` en cualquier momento: `M,0`, la placa se nivela en rampa.
- Si se cae el USB en automático: después de 1 s sin comandos, el firmware nivela
  la placa. Desde ±8° tarda menos de 1,5 s en total.
- Si el programa se cierra de forma ordenada, manda `M,0` antes de cerrar.
- El firmware nunca entra en automático si no recibió explícitamente `M,2`.

---

## 9. Modo simulación (sin hardware)

```powershell
python main.py --sim
```

Esto:

- Genera video sintético: pelota naranja, fondo azul y placa oscura.
- Usa la física `a = (5/7)·g·sin(tilt)` (sin rebote).
- Arranca la pelota en `x=0.5`.
- Ejecuta un FakeESP32 en Python que habla el mismo protocolo y aplica el mismo PID.
- Arranca en automático para que se vea la convergencia sin tocar teclas.

La ventana, las teclas, el setpoint, las trackbars, el CSV y el logger funcionan
igual. Es útil para practicar antes de conectar hardware. **No valida** servos,
cámara, luz, mecánica ni las ganancias reales.

También podés correr la integración automática:

```powershell
cd plataforma-pelota\pc
python -m pytest -q
```

La prueba de convergencia usa 60 fps simulados, arranca en 0,5, exige
`|error| < 0.05` en ambos ejes durante 1 s y tiene un máximo de 12 s. En esta
máquina midió ≈1,2 s.

---

## 10. Pruebas automatizadas

### PC

```powershell
cd plataforma-pelota\pc
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Si instalaste con `INSTALAR.bat`, desde la raíz del proyecto también podés usar
el Python del entorno instalado:

```powershell
pc\.venv\Scripts\python.exe -m pytest -q pc
```

Cubre:

- PID: escalón, derivativo sobre la medición, anti-windup, límites, slew rate.
- Conversión inclinación ↔ servo: ida y vuelta, saturación, signos, offsets.
- Protocolo: líneas válidas, truncadas, basura, telemetría.
- Normalización: centro, bordes, Y hacia arriba, inversiones, perspectiva.
- Detección con imágenes sintéticas: error < 2 px, sin pelota, ruido, brillo.
- Integración cerrada en simulación.
- Seguridad del FakeESP32, lógica del asistente de ejes y logger.
- Selector de dispositivos: normalización de índices/URL y guardado de
  cámara/puerto en `config.json`.

### Firmware nativo

```powershell
cd plataforma-pelota\firmware
pio test -e native
```

### Firmware para la placa

```powershell
pio run
```

Si `pio` no está disponible, se puede compilar desde VS Code con PlatformIO.
En este entorno `pio run` compiló correctamente para `esp32dev`.

Las pruebas físicas están en **`HARDWARE_TEST.md`** y son obligatorias antes de dar
el proyecto por terminado con hardware.

---

## 11. Logs y gráficos

Cada ejecución con `logging.enabled=true` crea un CSV en `pc/logs/`:

```text
pc/logs/telemetria_20261102_230204.csv
```

Columnas: tiempo, hora, ms del ESP32, posición, errores, inclinación, servos,
roll/pitch y estado.

Para graficar (requiere matplotlib):

```powershell
cd plataforma-pelota
python pc\tools\plot_log.py pc\logs\telemetria_20261102_230204.csv
python pc\tools\plot_log.py pc\logs\telemetria_....csv --save grafico.png
```

---

## 12. Configuración

### `firmware/include/config.h`

Contiene los valores físicos y de comportamiento del firmware:

- Pines y versión.
- `USE_IMU` (0 por defecto), pines I2C y filtro complementario.
- L=8 cm, r=2 cm, centro, límites [56,124], pulsos [500,2400].
- `SERVO_INVERT_X/Y`, offsets por defecto.
- Límite de inclinación ±8°, slew rate y rampa de nivelación.
- PID, filtro derivativo, límite del integral y límites de ganancias.
- Timeouts (200 ms pelota, 1000 ms enlace).
- Patrones de LED, buzzer y ganancias iniciales.

### `pc/config.json`

Contiene lo de la PC y lo espeja para la simulación:

- Cámara (índice/URL, resolución, fps, backend, MJPG).
- Enlace serie y autodetección.
- `setup_completed`: si es `false`, la app muestra el selector de dispositivos en
  el primer arranque real. El selector también se abre con `D`.
- El instalador crea `pc\.venv`, un acceso directo en el escritorio y usa
  `paquete\wheels` para trabajar sin internet.
- Rango HSV, área, circularidad, kernels.
- ROI y perspectiva.
- Setpoint, paso manual, inversiones de imagen y PID de la GUI/simulación.
- Parámetros de simulación (física, timeouts, servos espejo).
- GUI y logging.

> Si cambiás la mecánica en `config.h`, actualizá también el bloque
> `simulation.servo` de `config.json`. La simulación no lee archivos del firmware.

---

## 13. Solución de problemas

### La pelota no se detecta

- Verificá que la iluminación sea pareja y que la pelota naranja contraste con la
  placa.
- Presioná `C` y mirá la máscara: debe quedar blanca solo la pelota.
- Revisá que la ROI esté bien marcada (`R`) y que la pelota esté dentro.
- Subí/bajá `min_area`, `max_area` o `min_circularity` en `config.json`.
- Alejá la cámara del celular, limpiá el lente y comprobá el enfoque.
- En simulador no debería fallar; si falla ahí, es un problema de configuración.

### Los servos vibran o zumban

- Alimentación insuficiente: usá fuente externa de 5 V ≥2 A y capacitor de
  470–1000 µF.
- GND no común.
- Bajá Kd y Kp; el lazo puede estar sobreampliando.
- Revisá topes mecánicos y que la placa no esté forzada.
- Asegurate de que el cable de señal no esté cerca de la alimentación de los servos.

### La placa se va para el lado contrario

- Hacé la prueba 3 y activá `SERVO_INVERT_X/Y` en `config.h` según corresponda.
- No confundas con `control.invert_x/y` de `config.json` (orientación de imagen).
- Verificá que el PID tenga ganancias positivas; no cambies el signo del error.
- Revisá que los servos estén en GPIO 18 (X) y GPIO 19 (Y).

### Latencia alta

- Cerrá otras aplicaciones que usen la cámara.
- Preferí USB (DroidCam/Iriun) antes que Wi-Fi.
- Bajá a 640×480 como máximo; 320×240 puede ser suficiente.
- Pedí MJPG y 30–60 fps en `config.json`; el celular puede no dar 60.
- Ejecutá la PC sin cargas de CPU.
- Reducí Kp/Kd si el lazo oscila; la latencia real no se arregla solo con PID.

### No encuentra el ESP32 / "SIN ENLACE"

- Revisá Administrador de dispositivos y el driver.
- Cerrá otros programas que usen el COM (Arduino IDE, monitor serie).
- Poné el COM manualmente en `config.json`.
- Verificá que el firmware responda `HELLO,1.0.0` en el monitor a 115200.
- Probá otro cable USB de datos.
- La placa puede reiniciarse por falta de alimentación de servos.

### La cámara no abre

- Abrí `ELEGIR_DISPOSITIVOS.bat` o presioná `D` y probá otro índice.
- También podés usar `--camera 0`, `--camera 1`, `--camera 2`.
- Verificá que DroidCam/Iriun estén activos y no los esté usando otra app.
- Si usás una URL, comprobá que se abra en el navegador de la PC y que estén en la
  misma red.
- Cerrá Zoom, Teams, OBS u otras apps que tomen la webcam.

### No aparece el selector de dispositivos

- Abrí `ELEGIR_DISPOSITIVOS.bat` o presioná `D` dentro de la app.
- Si ya guardaste antes, `setup_completed` es `true` en `config.json` y no se abre
  solo; ese comportamiento es intencional.

### El instalador no encuentra Python

- Instalá el Python incluido en `paquete\instaladores\python-3.12.10-amd64.exe`
  (si preparaste el pendrive) y marcá **Add python.exe to PATH**.
- O instalá Python 3.12 x64 y volvé a ejecutar `INSTALAR.bat`.
- Verificá con `python --version` o `py --version`.

### Falla la instalación offline

- Copiá completa la carpeta `paquete\wheels`.
- El paquete está preparado para Python 3.12 x64. Si esa PC tiene otra versión,
  usá el instalador de Python incluido o instalá las dependencias con internet.
- Si hay internet, podés renombrar temporalmente `paquete` y ejecutar
  `INSTALAR.bat`: instalará desde la red.

### `SUBIR_FIRMWARE.bat` no encuentra el COM

- Instalá el driver CH340 o CP210x.
- Cerrá Arduino IDE/monitor serie y reconectá la placa.
- Probá otro cable USB de datos.
- Mantené BOOT al comenzar si aparece `Connecting...` pero no avanza.

### Error de ejecución de políticas en PowerShell

Los `.bat` ya llaman a PowerShell con `-ExecutionPolicy Bypass`, así que
normalmente no aparece. Para comandos manuales, ejecutá solo en esa terminal:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

o usá `cmd` y `.venv\Scripts\activate.bat`.

### `pio` no se reconoce

- **Para grabar el firmware no lo necesitás:** usá `SUBIR_FIRMWARE.bat`.
- Para desarrollo, instalá PlatformIO Core con `python -m pip install platformio`
  y abrí una terminal nueva.
- O usá la extensión de VS Code: PlatformIO → Upload.
- Si PlatformIO no está disponible, el firmware precompilado y todo el software
  de PC se pueden usar igual.

### La GUI no responde a las teclas

- Hacé clic dentro de la ventana de video para darle foco.
- En modo apagado/manual las flechas de movimiento solo actúan en manual (`1`).
- Cerrá los diálogos de calibración (Enter/Esc).
- Si el foco está en la terminal, las teclas van a la terminal.

### La pelota se pierde

- Revisá la máscara y la ROI.
- Verificá que la cámara no mueva el encuadre.
- El firmware pasa a perdida a los 200 ms sin P; un frame lento puede disparar el
  aviso. Reducí resolución/mejorá la luz.
- El buzzer avisa a los 2 s; es normal durante la calibración si tapás la pelota.

### El CSV está vacío

- Necesita que el ESP32 esté conectado y mandando telemetría; en `--sim` también
  se llena.
- Verificá `logging.enabled` en `config.json`.
- El archivo se escribe en `pc/logs/`.

---

## 14. Estructura del repositorio

```
plataforma-pelota/
├── README.md
├── LEEME_PRIMERO.txt
├── GUIA_PENDRIVE.md
├── PLAN.md
├── HARDWARE_TEST.md
├── INSTALAR.bat
├── INICIAR.bat
├── PROBAR_SIN_HARDWARE.bat
├── ELEGIR_DISPOSITIVOS.bat
├── SUBIR_FIRMWARE.bat
├── COMPILAR_Y_SUBIR_CON_PLATFORMIO.bat
├── PREPARAR_PENDRIVE.bat
├── windows/
│   ├── instalar.ps1
│   ├── preparar_pendrive.ps1
│   └── compilar_y_subir.ps1
├── docs/
│   ├── wiring.md
│   └── protocol.md
├── firmware/
│   ├── platformio.ini
│   ├── prebuilt/
│   │   ├── plataforma_pelota_esp32.bin
│   │   ├── plataforma_pelota_esp32.bin.sha256
│   │   └── LEEME.txt
│   ├── include/
│   │   └── config.h
│   ├── src/
│   │   ├── main.cpp
│   │   ├── pid.h / pid.cpp
│   │   ├── protocol.h / protocol.cpp
│   │   ├── status.h / status.cpp
│   │   └── imu.h / imu.cpp
│   └── test/
│       └── test_core/test_core.cpp
├── paquete/                (se crea con PREPARAR_PENDRIVE.bat; no se versiona)
│   ├── wheels/
│   ├── instaladores/
│   ├── entorno.txt
│   └── LEEME_PENDRIVE.txt
└── pc/
    ├── requirements.txt
    ├── config.json
    ├── config.py
    ├── devices.py
    ├── main.py
    ├── camera.py
    ├── vision.py
    ├── calibration.py
    ├── serial_link.py
    ├── protocol.py
    ├── gui.py
    ├── logger.py
    ├── sim.py
    ├── logs/               (se crea al ejecutar)
    ├── tools/
    │   ├── plot_log.py
    │   ├── flash_firmware.py
    │   └── requirements-flash.txt
    └── tests/
        ├── conftest.py
        ├── test_axis_assistant.py
        ├── test_devices.py
        ├── test_pid.py
        ├── test_protocol.py
        ├── test_servo_conversion.py
        ├── test_vision.py
        ├── test_sim_integration.py
        └── test_sim_safety.py
```

---

## 15. Seguridad y alcance

- El firmware limita los servos a [56°, 124°] y la inclinación a ±8°.
- La fuente de los servos no debe salir del ESP32.
- No dejes la pelota ni la placa en una posición inestable sin supervisión.
- La parada de emergencia es `ESPACIO`; también podés cerrar la GUI: manda `M,0`.
- Si el USB se cae, la placa se nivela sola después del timeout de seguridad.
- La IMU no controla el lazo en esta versión; solo se muestra en telemetría.
- Las pruebas de hardware son manuales y no pudieron ejecutarse en este entorno.
