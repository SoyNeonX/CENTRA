// ============================================================================
//  Plataforma estabilizadora de pelota - firmware ESP32
//
//  La PC manda la posición normalizada de la pelota (P) y este programa corre
//  el PID a 100 Hz, mueve dos servos y devuelve telemetría a 25 Hz.
//
//  TODO-HW: todo el comportamiento físico (servos, LED, buzzer, IMU y enlace
//  USB real) debe verificarse con HARDWARE_TEST.md. En la PC no hay hardware.
// ============================================================================

#include <Arduino.h>
#include <ESP32Servo.h>
#include <Preferences.h>

#include <cmath>
#include <cstdio>
#include <cstring>

#include "config.h"
#include "imu.h"
#include "pid.h"
#include "protocol.h"
#include "status.h"

namespace {

constexpr uint32_t kControlPeriodUs = 1000000UL / CONTROL_HZ;
constexpr uint32_t kTelemetryPeriodUs = 1000000UL / TELEMETRY_HZ;
constexpr float kControlDt = 1.0f / static_cast<float>(CONTROL_HZ);

Servo servo_x;
Servo servo_y;
bool servos_ready = false;
int last_pulse_x = -1;
int last_pulse_y = -1;

RobotMode mode = RobotMode::OFF;
AutoPhase auto_phase = AutoPhase::SEARCHING;
StatusOutput indicators;
PidController pid_x;
PidController pid_y;

PidGains gains_x = {PID_KP_DEFAULT, PID_KI_DEFAULT, PID_KD_DEFAULT};
PidGains gains_y = {PID_KP_DEFAULT, PID_KI_DEFAULT, PID_KD_DEFAULT};
float offset_x = SERVO_OFFSET_DEFAULT_X;
float offset_y = SERVO_OFFSET_DEFAULT_Y;

float setpoint_x = 0.0f;
float setpoint_y = 0.0f;
float tilt_limit = TILT_LIMIT_DEFAULT_DEG;
float manual_tilt_x = 0.0f;
float manual_tilt_y = 0.0f;

float tilt_x = 0.0f;
float tilt_y = 0.0f;
float servo_angle_x = SERVO_CENTER_DEG;
float servo_angle_y = SERVO_CENTER_DEG;
bool raw_servo_hold = false;

bool have_pose = false;
bool last_pose_found = false;
float ball_x = 0.0f;
float ball_y = 0.0f;
float last_error_x = 0.0f;
float last_error_y = 0.0f;
uint32_t last_pose_ms = 0;
uint32_t last_valid_rx_ms = 0;
uint32_t auto_entered_ms = 0;

bool imu_ok = false;
float imu_roll = 0.0f;
float imu_pitch = 0.0f;

uint32_t last_control_us = 0;
uint32_t last_telemetry_us = 0;

char line_buffer[SERIAL_LINE_MAX];
size_t line_length = 0;
bool line_overflow = false;

// --------------------------------------------------------------- utilidades --

float clampf(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

float moveTowards(float value, float target, float max_delta) {
  if (value < target) {
    return fminf(value + max_delta, target);
  }
  if (value > target) {
    return fmaxf(value - max_delta, target);
  }
  return value;
}

bool elapsedMs(uint32_t now, uint32_t since, uint32_t interval_ms) {
  return static_cast<uint32_t>(now - since) >= interval_ms;
}

float servoAngleForTilt(float tilt_deg, float offset_deg, bool invert) {
  // servo_deg = centro + offset + signo * degrees(asin(L*sin(tilt)/r))
  const float sine = sinf(tilt_deg * PI / 180.0f);
  const float ratio = clampf(MECH_L_CM * sine / MECH_R_CM, -1.0f, 1.0f);
  const float delta_deg = asinf(ratio) * (180.0f / PI);
  const float sign = invert ? -1.0f : 1.0f;
  return clampf(SERVO_CENTER_DEG + offset_deg + sign * delta_deg,
                SERVO_ANGLE_MIN, SERVO_ANGLE_MAX);
}

int angleToPulseUs(float angle) {
  const float limited = clampf(angle, SERVO_ANGLE_MIN, SERVO_ANGLE_MAX);
  const float fraction = limited / SERVO_FULL_TRAVEL_DEG;
  const float pulse = SERVO_PULSE_MIN_US +
                      fraction * (SERVO_PULSE_MAX_US - SERVO_PULSE_MIN_US);
  return static_cast<int>(lroundf(pulse));
}

void writeServosIfChanged() {
  if (!servos_ready || raw_servo_hold) {
    return;
  }
  const int pulse_x = angleToPulseUs(servo_angle_x);
  const int pulse_y = angleToPulseUs(servo_angle_y);
  if (pulse_x != last_pulse_x) {
    servo_x.writeMicroseconds(pulse_x);
    last_pulse_x = pulse_x;
  }
  if (pulse_y != last_pulse_y) {
    servo_y.writeMicroseconds(pulse_y);
    last_pulse_y = pulse_y;
  }
}

void writeRawServoAngles() {
  if (!servos_ready) {
    return;
  }
  const int pulse_x = angleToPulseUs(servo_angle_x);
  const int pulse_y = angleToPulseUs(servo_angle_y);
  servo_x.writeMicroseconds(pulse_x);
  servo_y.writeMicroseconds(pulse_y);
  last_pulse_x = pulse_x;
  last_pulse_y = pulse_y;
  // TODO-HW: verificar en la prueba 1 que los dos servos se muevan al centro.
}

void attachServos() {
  servo_x.setPeriodHertz(50);
  servo_y.setPeriodHertz(50);
  // TODO-HW: verificar centro, pulsos y sentido en HARDWARE_TEST.md (1 a 3).
  servo_x.attach(PIN_SERVO_X, SERVO_PULSE_MIN_US, SERVO_PULSE_MAX_US);
  servo_y.attach(PIN_SERVO_Y, SERVO_PULSE_MIN_US, SERVO_PULSE_MAX_US);
  servos_ready = true;

  // Arranque nivelado y suave: una sola orden al centro; el servo hace su
  // propia rampa mecánica. No se mueve por control hasta recibir M,1 o M,2.
  servo_angle_x = servoAngleForTilt(0.0f, offset_x, SERVO_INVERT_X);
  servo_angle_y = servoAngleForTilt(0.0f, offset_y, SERVO_INVERT_Y);
  writeRawServoAngles();
}

// ------------------------------------------------------------- preferencias --

void applyGainCommand(const PidGains& values, char axis) {
  if (axis == 'X' || axis == 'B') {
    gains_x = values;
    pid_x.setGains(gains_x);
  }
  if (axis == 'Y' || axis == 'B') {
    gains_y = values;
    pid_y.setGains(gains_y);
  }
}

bool saveSettings() {
  Preferences preferences;
  if (!preferences.begin("ballplate", false)) {
    return false;
  }
  bool ok = true;
  ok = preferences.putFloat("kpx", gains_x.kp) > 0 && ok;
  ok = preferences.putFloat("kix", gains_x.ki) > 0 && ok;
  ok = preferences.putFloat("kdx", gains_x.kd) > 0 && ok;
  ok = preferences.putFloat("kpy", gains_y.kp) > 0 && ok;
  ok = preferences.putFloat("kiy", gains_y.ki) > 0 && ok;
  ok = preferences.putFloat("kdy", gains_y.kd) > 0 && ok;
  ok = preferences.putFloat("offx", offset_x) > 0 && ok;
  ok = preferences.putFloat("offy", offset_y) > 0 && ok;
  preferences.end();
  return ok;
}

void loadSettings() {
  Preferences preferences;
  if (!preferences.begin("ballplate", true)) {
    return;  // primera vez: quedan los valores de config.h
  }

  gains_x.kp = clampf(preferences.getFloat("kpx", gains_x.kp), GAIN_KP_MIN, GAIN_KP_MAX);
  gains_x.ki = clampf(preferences.getFloat("kix", gains_x.ki), GAIN_KI_MIN, GAIN_KI_MAX);
  gains_x.kd = clampf(preferences.getFloat("kdx", gains_x.kd), GAIN_KD_MIN, GAIN_KD_MAX);
  gains_y.kp = clampf(preferences.getFloat("kpy", gains_y.kp), GAIN_KP_MIN, GAIN_KP_MAX);
  gains_y.ki = clampf(preferences.getFloat("kiy", gains_y.ki), GAIN_KI_MIN, GAIN_KI_MAX);
  gains_y.kd = clampf(preferences.getFloat("kdy", gains_y.kd), GAIN_KD_MIN, GAIN_KD_MAX);
  offset_x = clampf(preferences.getFloat("offx", offset_x),
                    -SERVO_OFFSET_LIMIT_DEG, SERVO_OFFSET_LIMIT_DEG);
  offset_y = clampf(preferences.getFloat("offy", offset_y),
                    -SERVO_OFFSET_LIMIT_DEG, SERVO_OFFSET_LIMIT_DEG);
  preferences.end();
}

// ------------------------------------------------------------------ estados --

AutoPhase initialAutoPhase(uint32_t now) {
  if (!have_pose) {
    return AutoPhase::SEARCHING;
  }
  if (!last_pose_found) {
    return AutoPhase::LOST;
  }
  if (elapsedMs(now, last_pose_ms, BALL_LOST_TIMEOUT_MS)) {
    return AutoPhase::LOST;
  }
  return AutoPhase::STABILIZING;
}

void changeAutoPhase(AutoPhase new_phase) {
  if (new_phase == auto_phase) {
    return;
  }
  auto_phase = new_phase;
  // Al entrar o salir de estabilizar conviene arrancar limpio: no arrastrar
  // integral ni derivada de otro estado.
  pid_x.reset();
  pid_y.reset();
  indicators.setState(telemetryState(mode, auto_phase));
}

void setMode(RobotMode new_mode, uint32_t now) {
  const bool entering_auto = (new_mode == RobotMode::AUTO && mode != RobotMode::AUTO);
  mode = new_mode;
  raw_servo_hold = false;
  pid_x.reset();
  pid_y.reset();

  if (mode == RobotMode::AUTO) {
    auto_entered_ms = now;
    auto_phase = initialAutoPhase(now);
    if (entering_auto) {
      indicators.beepShort();
    }
  } else if (mode == RobotMode::MANUAL) {
    // Conservar la inclinación actual evita un salto brusco; el usuario manda
    // A o las flechas para moverla. Si prefiere nivelar, usa M,0.
    manual_tilt_x = tilt_x;
    manual_tilt_y = tilt_y;
  }

  indicators.setState(telemetryState(mode, auto_phase));
}

void sendOk(CommandType type) {
  Serial.print("OK,");
  Serial.println(commandName(type));
}

void sendError(const char* reason) {
  Serial.print("ERR,");
  Serial.println(reason);
}


// ------------------------------------------------------------------ comandos --

void handleCommand(const SerialCommand& command, uint32_t now) {
  switch (command.type) {
    case CommandType::POSE: {
      ball_x = clampf(command.x, -1.0f, 1.0f);
      ball_y = clampf(command.y, -1.0f, 1.0f);
      last_pose_found = command.found;
      last_pose_ms = now;
      have_pose = true;
      sendOk(command.type);
      break;
    }

    case CommandType::MODE: {
      setMode(static_cast<RobotMode>(command.mode), now);
      sendOk(command.type);
      break;
    }

    case CommandType::MANUAL_TILT: {
      if (mode != RobotMode::MANUAL) {
        sendError("modo_no_manual");
        break;
      }
      manual_tilt_x = clampf(command.x, -tilt_limit, tilt_limit);
      manual_tilt_y = clampf(command.y, -tilt_limit, tilt_limit);
      raw_servo_hold = false;
      sendOk(command.type);
      break;
    }

    case CommandType::RAW_SERVO: {
      if (mode == RobotMode::AUTO) {
        sendError("modo_auto");
        break;
      }
      servo_angle_x = clampf(command.x, SERVO_ANGLE_MIN, SERVO_ANGLE_MAX);
      servo_angle_y = clampf(command.y, SERVO_ANGLE_MIN, SERVO_ANGLE_MAX);
      raw_servo_hold = true;
      writeRawServoAngles();
      sendOk(command.type);
      break;
    }

    case CommandType::GAINS: {
      PidGains values;
      values.kp = clampf(command.x, GAIN_KP_MIN, GAIN_KP_MAX);
      values.ki = clampf(command.y, GAIN_KI_MIN, GAIN_KI_MAX);
      values.kd = clampf(command.z, GAIN_KD_MIN, GAIN_KD_MAX);
      applyGainCommand(values, command.axis);
      sendOk(command.type);
      break;
    }

    case CommandType::SETPOINT: {
      setpoint_x = clampf(command.x, -1.0f, 1.0f);
      setpoint_y = clampf(command.y, -1.0f, 1.0f);
      sendOk(command.type);
      break;
    }

    case CommandType::OFFSETS: {
      offset_x = clampf(command.x, -SERVO_OFFSET_LIMIT_DEG, SERVO_OFFSET_LIMIT_DEG);
      offset_y = clampf(command.y, -SERVO_OFFSET_LIMIT_DEG, SERVO_OFFSET_LIMIT_DEG);
      sendOk(command.type);
      break;
    }

    case CommandType::TILT_LIMIT: {
      tilt_limit = clampf(command.x, TILT_LIMIT_MIN_DEG, TILT_LIMIT_MAX_DEG);
      pid_x.setOutputLimit(tilt_limit);
      pid_y.setOutputLimit(tilt_limit);
      manual_tilt_x = clampf(manual_tilt_x, -tilt_limit, tilt_limit);
      manual_tilt_y = clampf(manual_tilt_y, -tilt_limit, tilt_limit);
      sendOk(command.type);
      break;
    }

    case CommandType::SAVE: {
      if (saveSettings()) {
        sendOk(command.type);
      } else {
        sendError("nvs");
      }
      break;
    }

    case CommandType::HELLO: {
      Serial.print("HELLO,");
      Serial.println(FW_VERSION);
      sendOk(command.type);
      break;
    }

    default:
      sendError("comando_desconocido");
      break;
  }
}

void processLine(char* line, uint32_t now) {
  SerialCommand command;
  const ParseStatus status = parseCommand(line, command);
  if (status == ParseStatus::OK) {
    // Cualquier comando válido demuestra que el enlace sigue vivo, aunque
    // después se rechace por el modo actual.
    last_valid_rx_ms = now;
    handleCommand(command, now);
  } else if (status != ParseStatus::EMPTY) {
    sendError(parseStatusMessage(status));
  }
}

void readSerial(uint32_t now) {
  int processed = 0;
  while (Serial.available() > 0 && processed < 256) {
    ++processed;
    const int value = Serial.read();
    if (value < 0) {
      break;
    }
    const char character = static_cast<char>(value);

    if (character == '\r') {
      continue;
    }

    if (character == '\n') {
      if (line_overflow) {
        sendError("linea_larga");
      } else if (line_length > 0) {
        line_buffer[line_length] = '\0';
        processLine(line_buffer, now);
      }
      line_length = 0;
      line_overflow = false;
      continue;
    }

    if (line_length < sizeof(line_buffer) - 1) {
      line_buffer[line_length++] = character;
    } else {
      line_overflow = true;
    }
  }
}

// -------------------------------------------------------------- lazo de control --

void updateAutoPhase(uint32_t now) {
  const bool link_ok = elapsedMs(now, last_valid_rx_ms, LINK_TIMEOUT_MS) == false;
  const bool fresh = have_pose && last_pose_found &&
                     !elapsedMs(now, last_pose_ms, BALL_LOST_TIMEOUT_MS);

  AutoPhase target = auto_phase;
  if (!link_ok) {
    target = AutoPhase::LOST;  // fallback de seguridad: nivelar
  } else if (fresh) {
    target = AutoPhase::STABILIZING;
  } else if (have_pose && !last_pose_found) {
    target = AutoPhase::LOST;
  } else if (have_pose && elapsedMs(now, last_pose_ms, BALL_LOST_TIMEOUT_MS)) {
    target = AutoPhase::LOST;
  } else if (!have_pose) {
    target = elapsedMs(now, auto_entered_ms, BALL_LOST_TIMEOUT_MS)
                 ? AutoPhase::LOST
                 : AutoPhase::SEARCHING;
  }

  changeAutoPhase(target);
}

void updateControl(uint32_t now) {
  if (mode == RobotMode::AUTO) {
    updateAutoPhase(now);

    const bool fresh = have_pose && last_pose_found &&
                       !elapsedMs(now, last_pose_ms, BALL_LOST_TIMEOUT_MS) &&
                       !elapsedMs(now, last_valid_rx_ms, LINK_TIMEOUT_MS);
    if (auto_phase == AutoPhase::STABILIZING && fresh) {
      last_error_x = setpoint_x - ball_x;
      last_error_y = setpoint_y - ball_y;
      tilt_x = pid_x.update(setpoint_x, ball_x, kControlDt);
      tilt_y = pid_y.update(setpoint_y, ball_y, kControlDt);
    } else {
      // Pelota perdida, en búsqueda o enlace caído: PID limpio y volver a
      // nivel en rampa, sin golpes.
      pid_x.reset();
      pid_y.reset();
      last_error_x = 0.0f;
      last_error_y = 0.0f;
      tilt_x = moveTowards(tilt_x, 0.0f, LEVEL_RAMP_DPS * kControlDt);
      tilt_y = moveTowards(tilt_y, 0.0f, LEVEL_RAMP_DPS * kControlDt);
    }
  } else if (mode == RobotMode::MANUAL) {
    tilt_x = manual_tilt_x;
    tilt_y = manual_tilt_y;
    last_error_x = 0.0f;
    last_error_y = 0.0f;
  } else {
    // Apagado: nivelar en rampa y no controlar.
    pid_x.reset();
    pid_y.reset();
    last_error_x = 0.0f;
    last_error_y = 0.0f;
    tilt_x = moveTowards(tilt_x, 0.0f, LEVEL_RAMP_DPS * kControlDt);
    tilt_y = moveTowards(tilt_y, 0.0f, LEVEL_RAMP_DPS * kControlDt);
  }

  // Doble seguridad: aunque el PID ya satura, se vuelve a limitar acá.
  tilt_x = clampf(tilt_x, -tilt_limit, tilt_limit);
  tilt_y = clampf(tilt_y, -tilt_limit, tilt_limit);

  if (!raw_servo_hold) {
    servo_angle_x = servoAngleForTilt(tilt_x, offset_x, SERVO_INVERT_X);
    servo_angle_y = servoAngleForTilt(tilt_y, offset_y, SERVO_INVERT_Y);
    writeServosIfChanged();
  }

  indicators.setState(telemetryState(mode, auto_phase));
  indicators.update(now);

  if (imu_ok) {
    float roll = imu_roll;
    float pitch = imu_pitch;
    if (imuRead(roll, pitch)) {
      imu_roll = roll;
      imu_pitch = pitch;
    }
  }
}

// ---------------------------------------------------------------- telemetría --

void sendTelemetry() {
  const uint8_t state = telemetryState(mode, auto_phase);
  char buffer[192];
  snprintf(buffer, sizeof(buffer),
           "T,%lu,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f,%.2f,%.2f,%u",
           static_cast<unsigned long>(millis()),
           static_cast<double>(ball_x), static_cast<double>(ball_y),
           static_cast<double>(last_error_x), static_cast<double>(last_error_y),
           static_cast<double>(tilt_x), static_cast<double>(tilt_y),
           static_cast<double>(servo_angle_x), static_cast<double>(servo_angle_y),
           static_cast<double>(imu_roll), static_cast<double>(imu_pitch),
           static_cast<unsigned>(state));
  Serial.println(buffer);
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);

  loadSettings();

  pid_x.configure(gains_x, tilt_limit, SERVO_SLEW_RATE_DPS,
                  PID_D_FILTER, PID_I_LIMIT_DEG);
  pid_y.configure(gains_y, tilt_limit, SERVO_SLEW_RATE_DPS,
                  PID_D_FILTER, PID_I_LIMIT_DEG);

  indicators.begin();
  attachServos();
  imu_ok = imuBegin();

  const uint32_t now_ms = millis();
  last_valid_rx_ms = now_ms;
  last_pose_ms = now_ms;
  auto_entered_ms = now_ms;
  last_control_us = micros();
  last_telemetry_us = last_control_us;

  indicators.setState(telemetryState(mode, auto_phase));
  Serial.print("HELLO,");
  Serial.println(FW_VERSION);
  // No se usa delay() en ningún lado: el lazo y los timeouts son no bloqueantes.
}

void loop() {
  const uint32_t now_ms = millis();
  readSerial(now_ms);

  const uint32_t now_us = micros();
  if (static_cast<uint32_t>(now_us - last_control_us) >= kControlPeriodUs) {
    last_control_us = now_us;
    updateControl(now_ms);
  }

  if (static_cast<uint32_t>(now_us - last_telemetry_us) >= kTelemetryPeriodUs) {
    last_telemetry_us = now_us;
    sendTelemetry();
  }

  indicators.update(millis());
}
