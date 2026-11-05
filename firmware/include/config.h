#pragma once

// ============================================================================
//  CONFIGURACIÓN DEL FIRMWARE - versión ArUco (posiciones en cm)
//  Todos los valores físicos y de comportamiento están acá.
//  Si cambiás algo de la mecánica, actualizá también pc/config.json para que
//  la simulación use los mismos números (la placa real no lee este archivo).
// ============================================================================

// ------------------------------ Comunicación --------------------------------
#define FW_VERSION            "1.1.0"
#define SERIAL_BAUD           115200
#define SERIAL_LINE_MAX       96       // caracteres por línea (sin contar '\0')

// --------------------------------- Pines ------------------------------------
#define PIN_SERVO_X           18
#define PIN_SERVO_Y           19
#define PIN_LED_STATUS        4
#define PIN_BUZZER            16

// -------------------------------- Mecánica ----------------------------------
#define PLATE_SIZE_CM         24.0f     // placa cuadrada
#define PLATE_HALF_SIZE_CM    (PLATE_SIZE_CM / 2.0f)
#define POSITION_LIMIT_CM     PLATE_HALF_SIZE_CM
#define MECH_L_CM             8.0f     // distancia del centro a la varilla
#define MECH_R_CM             2.0f     // brazo del servo
#define SERVO_CENTER_DEG      90.0f
#define SERVO_ANGLE_MIN       56.0f    // nunca se manda un ángulo menor
#define SERVO_ANGLE_MAX       124.0f   // nunca se manda un ángulo mayor
#define SERVO_PULSE_MIN_US    500
#define SERVO_PULSE_MAX_US    2400
#define SERVO_FULL_TRAVEL_DEG 180.0f  // recorrido usado para convertir ángulo a µs
#define SERVO_INVERT_X        false    // ajustar según el montaje (prueba 3)
#define SERVO_INVERT_Y        false
#define SERVO_OFFSET_DEFAULT_X 0.0f    // offset de centro del servo X (grados)
#define SERVO_OFFSET_DEFAULT_Y 0.0f
#define SERVO_OFFSET_LIMIT_DEG 20.0f   // máximo offset aceptado por C
#define TILT_LIMIT_DEFAULT_DEG 8.0f    // inclinación máxima de diseño
#define TILT_LIMIT_MIN_DEG    0.5f
#define TILT_LIMIT_MAX_DEG    8.0f     // no permitir más que el diseño
#define SERVO_SLEW_RATE_DPS   120.0f   // limitador de velocidad del PID
#define LEVEL_RAMP_DPS        30.0f    // rampa al nivelar por pérdida / apagado

// ------------------------------ Lazo de control -----------------------------
#define CONTROL_HZ            100      // frecuencia fija del PID y servos
#define TELEMETRY_HZ          25       // frecuencia de las líneas T
#define BALL_LOST_TIMEOUT_MS  200      // sin P válida => pelota perdida
#define LINK_TIMEOUT_MS       1000     // sin enlace en automático => nivelar

// Ganancias en grados de inclinación por centímetro de error.
// Equivalentes a Kp=6, Ki=0.2 y Kd=4 en coordenadas normalizadas.
#define PID_KP_DEFAULT        0.50f
#define PID_KI_DEFAULT        0.02f
#define PID_KD_DEFAULT        0.33f
#define PID_I_LIMIT_DEG       3.0f     // límite del término integral
#define PID_D_FILTER          0.15f    // 1 = sin filtro, 0 = derivativo nulo

// Rangos aceptados por el comando G (los valores fuera de rango se saturan)
#define GAIN_KP_MIN           0.0f
#define GAIN_KP_MAX           5.0f
#define GAIN_KI_MIN           0.0f
#define GAIN_KI_MAX           1.0f
#define GAIN_KD_MIN           0.0f
#define GAIN_KD_MAX           5.0f

// ------------------------------- Indicadores --------------------------------
#define LED_ON                1
#define LED_OFF               0
#define BUZZER_ON             1
#define BUZZER_OFF            0
#define LED_SLOW_HALF_MS      500      // modo manual: parpadeo lento
#define LED_FAST_HALF_MS      120      // buscando: parpadeo rápido
#define LED_LOST_CYCLE_MS     1000     // perdida: doble parpadeo por segundo
#define LED_LOST_ON_MS        100
#define LED_LOST_OFF_MS       150      // pausa entre los dos destellos
#define BUZZER_SHORT_MS       150      // al pasar a automático
#define BUZZER_LONG_MS        1000     // pelota perdida por más de 2 s
#define LOST_ALERT_AFTER_MS   2000
