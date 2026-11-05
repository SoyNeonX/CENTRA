#pragma once

// PID didáctico, sin dependencias de Arduino para poder probarlo en la PC.
// La salida es una inclinación en grados.
struct PidGains {
  float kp;
  float ki;
  float kd;
};

class PidController {
 public:
  PidController();

  void configure(const PidGains& gains,
                 float output_limit_deg,
                 float slew_rate_dps,
                 float derivative_filter,
                 float integral_limit_deg);

  void setGains(const PidGains& gains);
  void setOutputLimit(float limit_deg);
  void setSlewRate(float rate_dps);
  void setIntegralLimit(float limit_deg);
  void reset();

  // setpoint y measurement están en centímetros; las ganancias son grados/cm.
  // dt_s es el tiempo transcurrido desde la llamada anterior, en segundos.
  float update(float setpoint, float measurement, float dt_s);

  float lastOutput() const { return last_output_; }
  float integralTerm() const { return integral_; }
  float derivativeTerm() const { return derivative_term_; }
  const PidGains& gains() const { return gains_; }

 private:
  static float clampValue(float value, float low, float high);

  PidGains gains_;
  float output_limit_;
  float slew_rate_;
  float derivative_filter_;
  float integral_limit_;

  float integral_;
  float filtered_derivative_;
  float last_measurement_;
  float last_output_;
  float derivative_term_;
  bool initialized_;
};
