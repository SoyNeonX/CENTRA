#pragma once

#include <stdint.h>

#include "config.h"

enum class RobotMode : uint8_t {
  OFF = 0,
  MANUAL = 1,
  AUTO = 2
};

// Subestado del modo automático. Los números coinciden con el campo
// <estado> de la telemetría T.
enum class AutoPhase : uint8_t {
  SEARCHING = 2,
  STABILIZING = 3,
  LOST = 4
};

uint8_t telemetryState(RobotMode mode, AutoPhase phase);

// LED único y buzzer activo, actualizados sin bloquear.
// TODO-HW: comprobar patrones de LED y sonidos en HARDWARE_TEST.md (prueba 9).
class StatusOutput {
 public:
  void begin();
  void setState(uint8_t state);
  void update(uint32_t now_ms);
  void beepShort();
  void beepLong();

  uint8_t state() const { return state_; }

 private:
  void updateLed(uint32_t now_ms);
  void startBeep(uint32_t now_ms, uint32_t duration_ms);
  void setBuzzer(bool on);

  uint8_t state_ = 0;
  uint32_t state_since_ms_ = 0;
  uint32_t beep_until_ms_ = 0;
  bool buzzer_active_ = false;
  bool lost_alert_done_ = false;
};
