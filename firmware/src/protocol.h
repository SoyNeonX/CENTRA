#pragma once

#include <stdint.h>

// Largo máximo de una línea del protocolo (sin contar el '\0').
#define PROTOCOL_LINE_MAX 96

// Comandos que la PC puede mandar al ESP32.
enum class CommandType : uint8_t {
  NONE,
  POSE,        // P,<x>,<y>,<found>
  MODE,        // M,<modo>
  MANUAL_TILT, // A,<tilt_x>,<tilt_y>
  RAW_SERVO,   // V,<servo_x>,<servo_y>
  GAINS,       // G,<eje>,<kp>,<ki>,<kd>
  SETPOINT,    // S,<sx>,<sy>
  OFFSETS,     // C,<off_x>,<off_y>
  TILT_LIMIT,  // L,<grados>
  SAVE,        // W
  HELLO        // H
};

enum class ParseStatus : uint8_t {
  OK,
  EMPTY,
  UNKNOWN,
  BAD_ARGS,
  BAD_NUMBER,
  BAD_RANGE
};

struct SerialCommand {
  CommandType type = CommandType::NONE;
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  float w = 0.0f;
  uint8_t mode = 0;
  bool found = false;
  char axis = 'B';
};

// Parsea una línea completa (sin '\n'). No modifica el texto de entrada.
// Devuelve OK y llena "out" solo si la línea es un comando válido.
ParseStatus parseCommand(const char* line, SerialCommand& out);

// Texto corto y sin espacios para responder ERR,<motivo>.
const char* parseStatusMessage(ParseStatus status);

// Letra del comando para responder OK,<cmd>.
const char* commandName(CommandType type);
