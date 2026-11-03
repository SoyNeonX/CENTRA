#include "imu.h"

#include "config.h"

// TODO-HW: probar el MPU6050 real en GPIO 21/22 y los signos roll/pitch.
#if USE_IMU

#include <Arduino.h>
#include <Wire.h>
#include <math.h>

namespace {

bool initialized = false;
uint32_t last_read_us = 0;
float roll_filtered = 0.0f;
float pitch_filtered = 0.0f;

constexpr uint8_t REG_SMPLRT_DIV = 0x19;
constexpr uint8_t REG_CONFIG = 0x1A;
constexpr uint8_t REG_GYRO_CONFIG = 0x1B;
constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;
constexpr uint8_t REG_WHO_AM_I = 0x75;

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(IMU_I2C_ADDRESS);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readBytes(uint8_t reg, uint8_t* buffer, uint8_t length) {
  Wire.beginTransmission(IMU_I2C_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(static_cast<uint8_t>(IMU_I2C_ADDRESS), length) != length) {
    return false;
  }
  for (uint8_t i = 0; i < length; ++i) {
    if (!Wire.available()) {
      return false;
    }
    buffer[i] = static_cast<uint8_t>(Wire.read());
  }
  return true;
}

int16_t combine(uint8_t high, uint8_t low) {
  return static_cast<int16_t>((static_cast<uint16_t>(high) << 8) | low);
}

}  // namespace

bool imuBegin() {
  Wire.begin(IMU_SDA_PIN, IMU_SCL_PIN);
  Wire.setClock(IMU_I2C_CLOCK_HZ);

  uint8_t who_am_i = 0;
  if (!readBytes(REG_WHO_AM_I, &who_am_i, 1)) {
    return false;
  }
  // El MPU6050 responde 0x68. Algunos módulos clonados responden otro valor,
  // por eso no se descarta todo si el registro no coincide.

  // Despertar, usar el oscilador interno y configurar 100 Hz aprox.
  if (!writeRegister(REG_PWR_MGMT_1, 0x01)) return false;
  if (!writeRegister(REG_SMPLRT_DIV, 9)) return false;      // 1 kHz / 10
  if (!writeRegister(REG_CONFIG, 0x03)) return false;       // DLPF 44 Hz
  if (!writeRegister(REG_GYRO_CONFIG, 0x00)) return false;  // ±250 °/s
  if (!writeRegister(REG_ACCEL_CONFIG, 0x00)) return false; // ±2 g

  initialized = false;
  last_read_us = micros();
  return true;
}

bool imuRead(float& roll, float& pitch) {
  uint8_t buffer[14];
  if (!readBytes(REG_ACCEL_XOUT_H, buffer, sizeof(buffer))) {
    return false;
  }

  const int16_t ax_raw = combine(buffer[0], buffer[1]);
  const int16_t ay_raw = combine(buffer[2], buffer[3]);
  const int16_t az_raw = combine(buffer[4], buffer[5]);
  // buffer[6..7]: temperatura, no se usa
  const int16_t gx_raw = combine(buffer[8], buffer[9]);
  const int16_t gy_raw = combine(buffer[10], buffer[11]);
  const int16_t gz_raw = combine(buffer[12], buffer[13]);  // reservado

  (void)gz_raw;

  const float ax = ax_raw / IMU_ACCEL_SCALE;
  const float ay = ay_raw / IMU_ACCEL_SCALE;
  const float az = az_raw / IMU_ACCEL_SCALE;
  const float gx = gx_raw / IMU_GYRO_SCALE;  // °/s
  const float gy = gy_raw / IMU_GYRO_SCALE;

  const float accel_roll =
      atan2f(ay, az) * (180.0f / PI) * IMU_ROLL_SIGN;
  const float accel_pitch =
      atan2f(-ax, sqrtf(ay * ay + az * az)) * (180.0f / PI) * IMU_PITCH_SIGN;

  const uint32_t now_us = micros();
  float dt = (now_us - last_read_us) / 1000000.0f;
  last_read_us = now_us;
  if (!(dt > 0.0f) || dt > 0.2f) {
    dt = 0.01f;
  }

  if (!initialized) {
    roll_filtered = accel_roll;
    pitch_filtered = accel_pitch;
    initialized = true;
  } else {
    roll_filtered = IMU_COMP_ALPHA * (roll_filtered + gx * dt) +
                    (1.0f - IMU_COMP_ALPHA) * accel_roll;
    pitch_filtered = IMU_COMP_ALPHA * (pitch_filtered + gy * dt) +
                     (1.0f - IMU_COMP_ALPHA) * accel_pitch;
  }

  roll = roll_filtered;
  pitch = pitch_filtered;
  return true;
}

#else

bool imuBegin() {
  return false;
}

bool imuRead(float& roll, float& pitch) {
  (void)roll;
  (void)pitch;
  return false;
}

#endif
