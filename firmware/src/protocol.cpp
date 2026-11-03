#include "protocol.h"

#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>

namespace {

constexpr int MAX_FIELDS = 8;

struct Field {
  const char* start;
  size_t len;
};

// Parte la línea por comas, recortando espacios de cada campo. No usa
// strtok() porque queremos conservar los campos vacíos y detectarlos como error.
bool splitFields(const char* line, Field* fields, int& count) {
  count = 0;
  if (line == nullptr) {
    return false;
  }

  size_t line_len = strlen(line);
  if (line_len > PROTOCOL_LINE_MAX) {
    return false;
  }

  const char* cursor = line;
  while (true) {
    const char* comma = strchr(cursor, ',');
    const char* end = (comma == nullptr) ? (line + line_len) : comma;

    while (cursor < end && isspace(static_cast<unsigned char>(*cursor))) {
      ++cursor;
    }
    const char* field_end = end;
    while (field_end > cursor &&
           isspace(static_cast<unsigned char>(*(field_end - 1)))) {
      --field_end;
    }

    if (count >= MAX_FIELDS) {
      return false;
    }
    fields[count].start = cursor;
    fields[count].len = static_cast<size_t>(field_end - cursor);
    ++count;

    if (comma == nullptr) {
      break;
    }
    cursor = comma + 1;
  }
  return true;
}

bool fieldToFloat(const Field& field, float& value) {
  char buffer[32];
  if (field.len == 0 || field.len >= sizeof(buffer)) {
    return false;
  }
  memcpy(buffer, field.start, field.len);
  buffer[field.len] = '\0';

  errno = 0;
  char* end = nullptr;
  const float parsed = strtof(buffer, &end);
  if (end == buffer || errno != 0) {
    return false;
  }
  while (*end != '\0' && isspace(static_cast<unsigned char>(*end))) {
    ++end;
  }
  if (*end != '\0' || !std::isfinite(parsed)) {
    return false;
  }
  value = parsed;
  return true;
}

bool fieldToInt(const Field& field, long& value) {
  char buffer[24];
  if (field.len == 0 || field.len >= sizeof(buffer)) {
    return false;
  }
  memcpy(buffer, field.start, field.len);
  buffer[field.len] = '\0';

  errno = 0;
  char* end = nullptr;
  const long parsed = strtol(buffer, &end, 10);
  if (end == buffer || errno != 0) {
    return false;
  }
  while (*end != '\0' && isspace(static_cast<unsigned char>(*end))) {
    ++end;
  }
  if (*end != '\0') {
    return false;
  }
  value = parsed;
  return true;
}

bool oneChar(const Field& field, char& value) {
  if (field.len != 1) {
    return false;
  }
  value = field.start[0];
  return true;
}

} // namespace

ParseStatus parseCommand(const char* line, SerialCommand& out) {
  out = SerialCommand();

  if (line == nullptr) {
    return ParseStatus::EMPTY;
  }

  Field fields[MAX_FIELDS];
  int count = 0;
  if (!splitFields(line, fields, count)) {
    return ParseStatus::BAD_ARGS;
  }
  if (count == 0 || fields[0].len == 0) {
    return ParseStatus::EMPTY;
  }

  char command = '\0';
  if (!oneChar(fields[0], command)) {
    return ParseStatus::UNKNOWN;
  }

  // Cada comando valida primero la cantidad exacta de campos.
  switch (command) {
    case 'P': {
      if (count != 4) return ParseStatus::BAD_ARGS;
      long found = 0;
      if (!fieldToFloat(fields[1], out.x) ||
          !fieldToFloat(fields[2], out.y) ||
          !fieldToInt(fields[3], found)) {
        return ParseStatus::BAD_NUMBER;
      }
      if (found < 0 || found > 1) return ParseStatus::BAD_RANGE;
      out.found = (found == 1);
      out.type = CommandType::POSE;
      return ParseStatus::OK;
    }

    case 'M': {
      if (count != 2) return ParseStatus::BAD_ARGS;
      long mode = 0;
      if (!fieldToInt(fields[1], mode)) return ParseStatus::BAD_NUMBER;
      if (mode < 0 || mode > 2) return ParseStatus::BAD_RANGE;
      out.mode = static_cast<uint8_t>(mode);
      out.type = CommandType::MODE;
      return ParseStatus::OK;
    }

    case 'A': {
      if (count != 3) return ParseStatus::BAD_ARGS;
      if (!fieldToFloat(fields[1], out.x) ||
          !fieldToFloat(fields[2], out.y)) {
        return ParseStatus::BAD_NUMBER;
      }
      out.type = CommandType::MANUAL_TILT;
      return ParseStatus::OK;
    }

    case 'V': {
      if (count != 3) return ParseStatus::BAD_ARGS;
      if (!fieldToFloat(fields[1], out.x) ||
          !fieldToFloat(fields[2], out.y)) {
        return ParseStatus::BAD_NUMBER;
      }
      out.type = CommandType::RAW_SERVO;
      return ParseStatus::OK;
    }

    case 'G': {
      if (count != 5) return ParseStatus::BAD_ARGS;
      char axis = '\0';
      if (!oneChar(fields[1], axis)) return ParseStatus::BAD_ARGS;
      if (axis != 'X' && axis != 'Y' && axis != 'B') {
        return ParseStatus::BAD_RANGE;
      }
      if (!fieldToFloat(fields[2], out.x) ||
          !fieldToFloat(fields[3], out.y) ||
          !fieldToFloat(fields[4], out.z)) {
        return ParseStatus::BAD_NUMBER;
      }
      out.axis = axis;
      out.type = CommandType::GAINS;
      return ParseStatus::OK;
    }

    case 'S': {
      if (count != 3) return ParseStatus::BAD_ARGS;
      if (!fieldToFloat(fields[1], out.x) ||
          !fieldToFloat(fields[2], out.y)) {
        return ParseStatus::BAD_NUMBER;
      }
      out.type = CommandType::SETPOINT;
      return ParseStatus::OK;
    }

    case 'C': {
      if (count != 3) return ParseStatus::BAD_ARGS;
      if (!fieldToFloat(fields[1], out.x) ||
          !fieldToFloat(fields[2], out.y)) {
        return ParseStatus::BAD_NUMBER;
      }
      out.type = CommandType::OFFSETS;
      return ParseStatus::OK;
    }

    case 'L': {
      if (count != 2) return ParseStatus::BAD_ARGS;
      if (!fieldToFloat(fields[1], out.x)) return ParseStatus::BAD_NUMBER;
      out.type = CommandType::TILT_LIMIT;
      return ParseStatus::OK;
    }

    case 'W': {
      if (count != 1) return ParseStatus::BAD_ARGS;
      out.type = CommandType::SAVE;
      return ParseStatus::OK;
    }

    case 'H': {
      if (count != 1) return ParseStatus::BAD_ARGS;
      out.type = CommandType::HELLO;
      return ParseStatus::OK;
    }

    default:
      return ParseStatus::UNKNOWN;
  }
}

const char* parseStatusMessage(ParseStatus status) {
  switch (status) {
    case ParseStatus::OK:        return "ok";
    case ParseStatus::EMPTY:     return "linea_vacia";
    case ParseStatus::UNKNOWN:   return "comando_desconocido";
    case ParseStatus::BAD_ARGS:  return "argumentos_invalidos";
    case ParseStatus::BAD_NUMBER:return "numero_invalido";
    case ParseStatus::BAD_RANGE: return "fuera_de_rango";
    default:                     return "error";
  }
}

const char* commandName(CommandType type) {
  switch (type) {
    case CommandType::POSE:        return "P";
    case CommandType::MODE:        return "M";
    case CommandType::MANUAL_TILT: return "A";
    case CommandType::RAW_SERVO:   return "V";
    case CommandType::GAINS:       return "G";
    case CommandType::SETPOINT:    return "S";
    case CommandType::OFFSETS:     return "C";
    case CommandType::TILT_LIMIT:  return "L";
    case CommandType::SAVE:        return "W";
    case CommandType::HELLO:       return "H";
    default:                       return "?";
  }
}
