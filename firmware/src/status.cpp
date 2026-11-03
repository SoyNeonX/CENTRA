#include "status.h"

#include <Arduino.h>

namespace {
bool elapsed(uint32_t now, uint32_t since, uint32_t interval_ms) {
  return static_cast<uint32_t>(now - since) >= interval_ms;
}
}  // namespace

uint8_t telemetryState(RobotMode mode, AutoPhase phase) {
  if (mode == RobotMode::OFF) return 0;
  if (mode == RobotMode::MANUAL) return 1;
  return static_cast<uint8_t>(phase);
}

void StatusOutput::begin() {
  pinMode(PIN_LED_STATUS, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_LED_STATUS, LED_OFF);
  digitalWrite(PIN_BUZZER, BUZZER_OFF);

  state_ = 0;
  state_since_ms_ = millis();
  beep_until_ms_ = 0;
  buzzer_active_ = false;
  lost_alert_done_ = false;
}

void StatusOutput::setState(uint8_t state) {
  if (state > 4) {
    state = 4;
  }
  if (state == state_) {
    return;
  }
  state_ = state;
  state_since_ms_ = millis();
  lost_alert_done_ = false;

  // Al entrar en "perdida" se rearma el aviso largo; no se dispara de
  // inmediato: el requisito lo pide después de 2 segundos.
}

void StatusOutput::update(uint32_t now_ms) {
  updateLed(now_ms);

  if (buzzer_active_ && static_cast<int32_t>(now_ms - beep_until_ms_) >= 0) {
    buzzer_active_ = false;
    setBuzzer(false);
  }

  if (state_ == 4 && !lost_alert_done_ &&
      elapsed(now_ms, state_since_ms_, LOST_ALERT_AFTER_MS)) {
    lost_alert_done_ = true;
    beepLong();
  }
}

void StatusOutput::updateLed(uint32_t now_ms) {
  bool led_on = false;

  switch (state_) {
    case 0:  // apagado
      led_on = false;
      break;

    case 1: {  // manual: parpadeo lento
      const uint32_t phase = static_cast<uint32_t>(now_ms - state_since_ms_);
      led_on = (phase % (2 * LED_SLOW_HALF_MS)) < LED_SLOW_HALF_MS;
      break;
    }

    case 2: {  // buscando: parpadeo rápido
      const uint32_t phase = static_cast<uint32_t>(now_ms - state_since_ms_);
      led_on = (phase % (2 * LED_FAST_HALF_MS)) < LED_FAST_HALF_MS;
      break;
    }

    case 3:  // estabilizando: fijo
      led_on = true;
      break;

    case 4: {  // perdida: doble parpadeo
      const uint32_t phase =
          static_cast<uint32_t>(now_ms - state_since_ms_) % LED_LOST_CYCLE_MS;
      const uint32_t first_end = LED_LOST_ON_MS;
      const uint32_t pause_end = first_end + LED_LOST_OFF_MS;
      const uint32_t second_end = pause_end + LED_LOST_ON_MS;
      led_on = (phase < first_end) || (phase >= pause_end && phase < second_end);
      break;
    }

    default:
      led_on = false;
      break;
  }

  digitalWrite(PIN_LED_STATUS, led_on ? LED_ON : LED_OFF);
}

void StatusOutput::beepShort() {
  startBeep(millis(), BUZZER_SHORT_MS);
}

void StatusOutput::beepLong() {
  startBeep(millis(), BUZZER_LONG_MS);
}

void StatusOutput::startBeep(uint32_t now_ms, uint32_t duration_ms) {
  beep_until_ms_ = now_ms + duration_ms;
  buzzer_active_ = true;
  setBuzzer(true);
}

void StatusOutput::setBuzzer(bool on) {
  digitalWrite(PIN_BUZZER, on ? BUZZER_ON : BUZZER_OFF);
}
