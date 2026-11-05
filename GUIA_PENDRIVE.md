# CENTRA — Guía para llevar el proyecto en un pendrive

**ÁGUILAS IMPERIALES**

Esta guía responde las dudas típicas de transporte:

- Qué es PlatformIO y por qué está en el proyecto.
- Cómo se sube el firmware al ESP32.
- Qué librerías hacen falta y cuáles se instalan solas.
- Cómo imprimir y pegar los marcadores ArUco.
- Cómo preparar un paquete offline para una PC de la escuela sin internet.
- Qué hacer paso a paso en la PC de la escuela.

## 1. Resumen: qué necesitás llevar

La carpeta completa del proyecto:

```
plataforma-pelota/
├── INSTALAR.bat
├── CENTRA.bat                 (menú principal)
├── FIRMWARE.bat               (menú del ESP32)
├── CREAR_EXE.bat
├── PREPARAR_PENDRIVE.bat
├── LLEGAR_A_LA_ESCUELA.txt
├── README.md
├── GUIA_PENDRIVE.md          <- este archivo
├── HARDWARE_TEST.md
├── docs/
│   ├── marcadores_aruco/
│   │   ├── hoja_marcadores_A4.pdf
│   │   └── aruco_0.png ... aruco_3.png
│   ├── wiring.md
│   └── protocol.md
├── firmware/
│   └── prebuilt/
│       ├── plataforma_pelota_esp32.bin
│       ├── plataforma_pelota_esp32.bin.sha256
│       └── LEEME.txt
├── pc/
│   └── ...
└── paquete/                  <- se genera con PREPARAR_PENDRIVE.bat
    ├── wheels/
    ├── instaladores/
    ├── entorno.txt
    └── LEEME_PENDRIVE.txt
```

No copies `pc\.venv`, `firmware\.pio`, `.git`, `pc\logs` ni `__pycache__`: son
archivos de desarrollo y pueden ocupar mucho espacio. El `INSTALAR.bat` crea el
entorno virtual nuevo en cada PC.

## 2. ¿Qué es PlatformIO y por qué está acá?

PlatformIO es la herramienta que:

1. Descarga el **Arduino core de ESP32**, el compilador y las librerías.
2. Compila los archivos `.cpp` y `.h` del firmware en un archivo `.bin`.
3. Graba ese `.bin` en el ESP32 por USB.

Es el equivalente a Arduino IDE, pero con `platformio.ini` y tests automáticos. En
el proyecto ya está todo configurado en `firmware/platformio.ini`.

**PlatformIO no es un programa que quede dentro del ESP32.** El ESP32 solo
ejecuta el firmware compilado.

### ¿Lo necesito en la PC de la escuela?

**No, si solo vas a usar el firmware ya compilado.** El proyecto incluye
`firmware/prebuilt/plataforma_pelota_esp32.bin`, que contiene bootloader,
tabla de particiones y aplicación. `FIRMWARE.bat` lo graba con `esptool`
sin PlatformIO.

**Sí, si vas a modificar `config.h` o el código del firmware en la escuela.**
En ese caso necesitás PlatformIO y, la primera vez, internet para descargar el
compilador y el core de ESP32. Para el proyecto escolar normal, compilá y
probá el firmware en tu casa, y en la escuela usá el binario precompilado.

## 3. ¿Qué librerías hay que descargar o tener listo?

### Firmware

| Librería | Quién la instala | Comentario |
|---|---|---|
| Arduino core ESP32 | PlatformIO, automáticamente | Framework base |
| `ESP32Servo` 3.2.1 | PlatformIO, automáticamente | Controla los dos MG90S |
| `Preferences` | ya viene en el core | Guardar ganancias y offsets |
| Unity | PlatformIO, solo para tests | No va al ESP32 |

No hay que descargar ZIPs ni copiar carpetas a mano: `platformio.ini` pide
`ESP32Servo@3.2.1` y PlatformIO la resuelve.

### PC

Todo está en:

- `pc/requirements.txt`: `opencv-contrib-python` (ArUco), NumPy, pyserial,
  pytest y matplotlib.
- `pc/tools/requirements-flash.txt`: `esptool`, necesario para grabar el
  firmware sin PlatformIO.

El instalador los descarga e instala. El modo offline los toma de
`paquete/wheels`.

## 4. Preparar el pendrive (hacer en una PC con internet)

1. Conectá el pendrive o prepará la carpeta que vas a copiar.
2. En la PC con internet, abrí la carpeta del proyecto.
3. Ejecutá:

   **`PREPARAR_PENDRIVE.bat`**

4. El script:
   - Crea `paquete/wheels`.
   - Descarga y construye todas las librerías de PC para **Python 3.12 x64**.
   - Incluye `esptool`.
   - Descarga el instalador oficial de **Python 3.12.10 x64** en
     `paquete/instaladores/`.
   - Crea `paquete/LEEME_PENDRIVE.txt` con las instrucciones.
   - Verifica el firmware precompilado.
5. Copiá **toda la carpeta `plataforma-pelota`** al pendrive, incluyendo
   `paquete/`.

> `paquete/` está en `.gitignore` porque pesa y se genera localmente. Si clonás
> el repositorio desde git, tenés que ejecutar `PREPARAR_PENDRIVE.bat` en una PC
> con internet antes de llevarlo.

El script necesita Python 3.12 x64 en la PC que prepara el paquete. El paquete
offline queda pensado para esa misma versión. Si la PC de la escuela tiene otra
versión de Python, usá el instalador incluido o ejecutá `INSTALAR.bat` con
internet.

> El paquete actual pesa alrededor de 116 MB, casi todo por OpenCV contrib y el
> instalador de Python.

## 5. En la PC de la escuela

**Primero copiá la carpeta del proyecto del pendrive al Escritorio** (o a otra
carpeta escribible de la PC). No la ejecutes directamente desde un pendrive de
solo lectura ni desde una carpeta de red: el instalador necesita crear
`pc\.venv` y escribir config.json/logs.

### Paso 1: instalar Python si no está

El instalador ofrece abrir el Python incluido. Si no lo encontró:

1. Ejecutá `paquete\instaladores\python-3.12.10-amd64.exe`.
2. Marcá **Add python.exe to PATH**.
3. Volvé a ejecutar `INSTALAR.bat`.

Si el paquete no tiene el instalador, descargá Python 3.12 x64 desde
<https://www.python.org/downloads/windows/>.

### Paso 2: imprimir y pegar los marcadores

Antes de usar la cámara:

1. Imprimí `docs\marcadores_aruco\hoja_marcadores_A4.pdf` en A4 al **100%**.
2. Comprobá que cada cuadrado negro mida **4 × 4 cm**.
3. Recortá dejando 1 cm de blanco alrededor.
4. Pegalos en la placa: ID 0 arriba-izquierda, 1 arriba-derecha,
   2 abajo-derecha y 3 abajo-izquierda, vistos desde la cámara.
5. Los centros deben quedar a **±10 cm** del centro de la placa.

### Paso 3: instalar la aplicación

**Primero:** doble clic en **`INSTALAR.bat`** (una sola vez).
Después: **`CENTRA.bat`** es el menú para abrir OpenCV, Tkinter, simulaciones,
configurar cámara/COM y verificar.

El instalador:

- Crea `pc\.venv` (entorno virtual).
- Detecta `paquete\wheels` y trabaja sin internet.
- Instala OpenCV contrib (ArUco), NumPy, pyserial, pytest, matplotlib y esptool.
- Verifica las importaciones.
- Comprueba el SHA256 del firmware precompilado.
- Crea un acceso directo **CENTRA** en el escritorio (apunta a `CENTRA.bat`).

Si no hay `paquete\wheels`, intenta descargar todo desde internet.

### Paso 3.1: ejecutable (opcional)

Si querés un ejecutable, ejecutá `CREAR_EXE.bat`. Si PyInstaller está instalado
deja un `CENTRA.exe` autocontenido; si no, deja un lanzador que usa `pc\.venv`.
`CENTRA.bat` lo detecta automáticamente. `FIRMWARE.bat` necesita el entorno
instalado o PlatformIO.

### Paso 4: drivers del USB y conectar el ESP32

Instalá el driver del chip USB de tu DevKit:

- CH340/CH341: <http://www.wch-ic.com/downloads/CH341SER_EXE.html>.
- CP210x: <https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers>.
- También puede servir el ZIP que te dio el vendedor de la placa.

Conectá el ESP32 con un cable USB **de datos**. En el Administrador de
dispositivos debe aparecer un puerto COM nuevo.

### Paso 5: grabar el firmware

1. Cerrá Arduino IDE, el monitor serie y cualquier programa que use el COM.
2. Ejecutá **`FIRMWARE.bat`**.
3. Elegí el número del puerto COM del ESP32.
4. Confirmá con `S`.
5. Si no entra en modo grabación, mantené presionado **BOOT** al comenzar y
   soltalo cuando aparezca `Connecting...`.

El firmware precompilado se graba en `0x0` con esptool y no requiere
PlatformIO.

### Paso 6: elegir cámara y puerto

Ejecutá **`CENTRA.bat`** y elegí **Configurar cámara y puerto USB** (opción 5).

- **Cámara:** elegí el índice 0, 1, 2... según DroidCam/Iriun, o hacé clic en el
  campo URL y escribí una URL de IP Webcam/RTSP. Enter termina de editar la URL
  y un segundo Enter guarda.
- **Puerto serial:** elegí **AUTODETECTAR** (recomendado) o un COM concreto.
- Guardá con Enter.

La aplicación también abre este selector sola en el primer arranque y se puede
reabrir desde la ventana principal con la tecla **D**. Al aplicar cambios, la
aplicación se reinicia sola para abrir la cámara y el puerto nuevos.

### Paso 7: usar y probar

- **`CENTRA.bat` opción 1**: OpenCV con cámara y ESP32 reales.
- **`CENTRA.bat` opción 2**: Tkinter con cámara, split y gráficas.
- **`CENTRA.bat` opción 3 u 4**: simulación OpenCV o Tkinter, sin hardware.

La primera vez, dentro de la aplicación:

1. Apuntá la cámara y verificá que el panel diga `arUco 4/4`.
2. `C` para calibrar el color de la pelota.
3. `K` para ajustar el centro de los servos.
4. `E` para el asistente de ejes.
5. `1` manual y flechas para probar movimientos.
6. `2` automático, empezando con Kp bajo.
7. `ESPACIO` es la parada de emergencia.

Seguí `HARDWARE_TEST.md` en orden para la puesta en marcha completa.

## 6. Si querés modificar el firmware en la escuela

Necesitás PlatformIO instalado allí y conexión a internet la primera vez para
descargar el compilador. La forma recomendada es hacerlo antes en tu casa.

En una PC con PlatformIO:

```powershell
cd firmware
pio run -t upload
```

O ejecutá en Windows:

**`FIRMWARE.bat`**

Ese botón compila el código fuente actual y lo sube. Si cambiás
`SERVO_INVERT_X/Y`, pines, ganancias o mecánica en `config.h`:

1. Recompilá con PlatformIO.
2. Probá.
3. Si querés que el botón precompilado del pendrive también quede actualizado,
   volvé a generar el binario fusionado o usá PlatformIO directamente en la
   escuela.

El firmware precompilado es la versión 1.1.0, sin IMU. Si cambiás el código o
`config.h`, hay que recompilar y volver a generar el binario fusionado.

## 7. Archivos de la aplicación

| Archivo | Para qué sirve |
|---|---|
| `INSTALAR.bat` | Instala las dependencias de la PC. |
| `CENTRA.bat` | Menú: OpenCV, Tkinter, simulaciones, cámara/COM y diagnóstico. |
| `FIRMWARE.bat` | Menú: grabar el `.bin`, compilar con PlatformIO o monitor serie. |
| `PREPARAR_PENDRIVE.bat` | Descarga todo para usar sin internet. |
| `CREAR_EXE.bat` | Crea `CENTRA.exe` (autocontenido o lanzador). |

Dentro de `CENTRA.bat`:
1. OpenCV real · 2. Tkinter real · 3. Simulación OpenCV · 4. Simulación Tkinter
· 5. Configurar cámara/COM · 6. Verificar · 7. Firmware · 8. Salir.

## 8. Problemas frecuentes en la escuela

### “No se encontró Python”

Instalá Python desde `paquete\instaladores` y volvé a ejecutar `INSTALAR.bat`.
Marcá “Add python.exe to PATH”.

### “No se pudieron instalar las dependencias”

- Verificá que `paquete\wheels` esté copiado completo.
- El paquete offline es para **Python 3.12 x64**. Si la PC tiene otra versión,
  instalá Python 3.12 del paquete.
- Si hay internet, borrá o renombrá `paquete\wheels` para que el instalador
  descargue las versiones correspondientes a esa PC.
- Si el entorno virtual `pc\.venv` fue copiado de otra PC, el instalador lo
  detecta y lo vuelve a crear; no es necesario borrarlo a mano.

### No aparece el COM

- Cable de datos, no solo de carga.
- Driver CH340/CP210x.
- Cerrá Arduino IDE, VS Code Monitor, etc.
- Probá otro puerto USB.
- La placa puede estar en modo bootloader: desconectá y reconectá.

### “Connecting...” no termina

Mantené **BOOT** presionado al comienzo del flasheo y soltalo cuando espere.
Revisá el puerto elegido. Si el ESP32 se alimenta de una fuente externa, revisá
el GND común.

### La aplicación no ve la cámara

- Instalá DroidCam/Iriun también en la PC de la escuela.
- Probá otro índice con `CENTRA.bat`.
- Para IP Webcam usá `http://IP:8080/video` y verificá que la PC y el celular
  estén en la misma red.
- Cerrá Zoom/Teams/OBS.

### Quiero probar sin hardware

Abrí `CENTRA.bat` y elegí la opción 3 (OpenCV) o 4 (Tkinter). Usa el FakeESP32
y una cámara sintética.

## 9. Ventaja del firmware precompilado

En la escuela solo se necesita:

```
INSTALAR.bat -> FIRMWARE.bat -> CENTRA.bat (opcion 5) -> CENTRA.bat (opcion 1 o 2)
```

PlatformIO queda para la PC de desarrollo.

## 10. Seguridad

- No alimentes los servos desde el ESP32.
- Usá fuente externa de 5 V y GND común.
- Poné el capacitor de 470–1000 µF.
- El firmware limita los servos a 56–124°.
- Antes de mover la placa, tené a mano `ESPACIO` o cerrá la app.
- Si no hay pelota o se corta el enlace en automático, la placa vuelve a nivel.
