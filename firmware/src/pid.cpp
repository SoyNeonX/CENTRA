#include "pid.h"

#include <cmath>

namespace {
constexpr float kMaxDtSeconds = 0.05f;
}

PidController::PidController()
    : gains_{0.0f, 0.0f, 0.0f},
      output_limit_(8.0f),
      slew_rate_(120.0f),
      derivative_filter_(1.0f),
      integral_limit_(3.0f),
      integral_(0.0f),
      filtered_derivative_(0.0f),
      last_measurement_(0.0f),
      last_output_(0.0f),
      derivative_term_(0.0f),
      initialized_(false) {}

void PidController::configure(const PidGains& gains,
                              float output_limit_deg,
                              float slew_rate_dps,
                              float derivative_filter,
                              float integral_limit_deg) {
  gains_ = gains;
  output_limit_ = fabsf(output_limit_deg);
  slew_rate_ = fabsf(slew_rate_dps);
  derivative_filter_ = clampValue(derivative_filter, 0.0f, 1.0f);
  integral_limit_ = fabsf(integral_limit_deg);
  reset();
}

void PidController::setGains(const PidGains& gains) {
  gains_ = gains;
}

void PidController::setOutputLimit(float limit_deg) {
  output_limit_ = fabsf(limit_deg);
}

void PidController::setSlewRate(float rate_dps) {
  slew_rate_ = fabsf(rate_dps);
}

void PidController::setIntegralLimit(float limit_deg) {
  integral_limit_ = fabsf(limit_deg);
  integral_ = clampValue(integral_, -integral_limit_, integral_limit_);
}

void PidController::reset() {
  integral_ = 0.0f;
  filtered_derivative_ = 0.0f;
  last_measurement_ = 0.0f;
  derivative_term_ = 0.0f;
  last_output_ = 0.0f;
  initialized_ = false;
}

float PidController::clampValue(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

float PidController::update(float setpoint, float measurement, float dt_s) {
  if (!(dt_s > 0.0f)) {
    return last_output_;
  }
  if (dt_s > kMaxDtSeconds) {
    dt_s = kMaxDtSeconds;
  }

  const float error = setpoint - measurement;

  // Derivativo sobre la medición, con filtro pasa-bajos de primer orden.
  float raw_derivative = 0.0f;
  if (initialized_) {
    raw_derivative = (measurement - last_measurement_) / dt_s;
  }
  filtered_derivative_ +=
      derivative_filter_ * (raw_derivative - filtered_derivative_);
  derivative_term_ = -gains_.kd * filtered_derivative_;

  // Integral tentativa, siempre recortada al límite configurado.
  float tentative_integral =
      integral_ + gains_.ki * error * dt_s;
  tentative_integral =
      clampValue(tentative_integral, -integral_limit_, integral_limit_);

  float unsaturated =
      gains_.kp * error + tentative_integral + derivative_term_;

  // Anti-windup: si la salida ya satura y el error empuja en el mismo
  // sentido, no se acumula más integral. La salida final sigue pasando por
  // el limitador de velocidad (slew rate).
  const bool pushes_positive = unsaturated > output_limit_ && error > 0.0f;
  const bool pushes_negative = unsaturated < -output_limit_ && error < 0.0f;
  if (pushes_positive || pushes_negative) {
    tentative_integral = integral_;
    unsaturated = gains_.kp * error + tentative_integral + derivative_term_;
  }

  integral_ = tentative_integral;
  const float limited =
      clampValue(unsaturated, -output_limit_, output_limit_);

  const float max_step = slew_rate_ * dt_s;
  last_output_ += clampValue(limited - last_output_, -max_step, max_step);
  last_output_ = clampValue(last_output_, -output_limit_, output_limit_);

  last_measurement_ = measurement;
  initialized_ = true;
  return last_output_;
}
