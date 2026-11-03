// Tests nativos de la lógica que corre en el ESP32.
// Ejecutar con: pio test -e native
#include <unity.h>

#include <cmath>
#include <cstring>

#include "pid.h"
#include "protocol.h"

void setUp(void) {}
void tearDown(void) {}

static void assert_near(float expected, float actual, float tolerance) {
  TEST_ASSERT_FLOAT_WITHIN(tolerance, expected, actual);
}

// ---------------------------------------------------------------- PID -------

static void test_pid_salida_positiva_para_error_positivo() {
  PidController pid;
  pid.configure({1.0f, 0.0f, 0.0f}, 8.0f, 1000.0f, 1.0f, 3.0f);
  pid.update(0.0f, 0.0f, 0.01f);
  const float out = pid.update(1.0f, 0.0f, 0.01f);
  assert_near(1.0f, out, 0.001f);
}

static void test_pid_derivativo_sobre_medicion_sin_golpe_de_setpoint() {
  PidController pid;
  pid.configure({1.0f, 0.0f, 2.0f}, 20.0f, 1000.0f, 1.0f, 3.0f);
  pid.update(0.0f, 0.0f, 0.01f);

  // Un salto de setpoint no debe producir derivativo (derivada de la medición).
  const float after_setpoint_jump = pid.update(1.0f, 0.0f, 0.01f);
  assert_near(0.0f, pid.derivativeTerm(), 0.0001f);
  assert_near(1.0f, after_setpoint_jump, 0.001f);

  // La medición sí cambia: el término derivativo debe oponerse a ese cambio.
  const float after_measurement_change = pid.update(1.0f, 0.01f, 0.01f);
  TEST_ASSERT_TRUE(pid.derivativeTerm() < 0.0f);
  TEST_ASSERT_TRUE(after_measurement_change < after_setpoint_jump);
}

static void test_pid_antiwindup_no_acumula_con_salida_saturada() {
  PidController pid;
  pid.configure({20.0f, 10.0f, 0.0f}, 8.0f, 1000.0f, 1.0f, 3.0f);
  pid.update(0.0f, 0.0f, 0.01f);
  for (int i = 0; i < 50; ++i) {
    pid.update(1.0f, 0.0f, 0.01f);
  }
  assert_near(8.0f, pid.lastOutput(), 0.001f);
  assert_near(0.0f, pid.integralTerm(), 0.001f);

  // Al invertir el error debe poder salir rápido de la saturación positiva.
  const float reversed = pid.update(0.0f, 0.1f, 0.01f);
  TEST_ASSERT_TRUE(reversed < 0.0f);
}

static void test_pid_limite_de_integral() {
  PidController pid;
  pid.configure({0.0f, 100.0f, 0.0f}, 100.0f, 1000.0f, 1.0f, 3.0f);
  pid.update(0.0f, 0.0f, 0.01f);
  for (int i = 0; i < 100; ++i) {
    pid.update(0.1f, 0.0f, 0.01f);
  }
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 3.0f, pid.integralTerm());
}

static void test_pid_limitador_de_velocidad() {
  PidController pid;
  pid.configure({100.0f, 0.0f, 0.0f}, 8.0f, 10.0f, 1.0f, 3.0f);
  pid.update(0.0f, 0.0f, 0.01f);
  const float first = pid.update(1.0f, 0.0f, 0.01f);
  const float second = pid.update(1.0f, 0.0f, 0.01f);
  assert_near(0.1f, first, 0.0001f);
  assert_near(0.2f, second, 0.0001f);
}

static void test_pid_dt_invalido_no_cambia_salida() {
  PidController pid;
  pid.configure({1.0f, 0.0f, 0.0f}, 8.0f, 1000.0f, 1.0f, 3.0f);
  const float out = pid.update(1.0f, 0.0f, 0.0f);
  assert_near(0.0f, out, 0.0001f);
}

// ------------------------------------------------------------ PROTOCOLO -----

static void test_protocolo_p_valido() {
  SerialCommand cmd;
  const ParseStatus status = parseCommand(" P , 0.250 , -1.500 , 1 \r\n", cmd);
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(status));
  TEST_ASSERT_EQUAL(static_cast<int>(CommandType::POSE),
                    static_cast<int>(cmd.type));
  assert_near(0.25f, cmd.x, 0.0001f);
  assert_near(-1.5f, cmd.y, 0.0001f);
  TEST_ASSERT_TRUE(cmd.found);
  // El parser no satura: el firmware lo hace después y así se puede probar.
}

static void test_protocolo_comandos_validos() {
  SerialCommand cmd;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("M,2", cmd)));
  TEST_ASSERT_EQUAL(2, cmd.mode);

  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("A,-3.5,2", cmd)));
  assert_near(-3.5f, cmd.x, 0.001f);

  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("G,X,6,0.2,4", cmd)));
  TEST_ASSERT_EQUAL('X', cmd.axis);
  assert_near(4.0f, cmd.z, 0.001f);

  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("S,0.1,0.2", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("C,2.5,-1", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("L,7.5", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("W", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::OK),
                    static_cast<int>(parseCommand("H", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(CommandType::HELLO),
                    static_cast<int>(cmd.type));
}

static void test_protocolo_rechaza_lineas_invalidas() {
  SerialCommand cmd;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::EMPTY),
                    static_cast<int>(parseCommand("", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::EMPTY),
                    static_cast<int>(parseCommand("   ", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::UNKNOWN),
                    static_cast<int>(parseCommand("Z,1", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_ARGS),
                    static_cast<int>(parseCommand("P,0.1,0.2", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_ARGS),
                    static_cast<int>(parseCommand("P,0.1,0.2,1,9", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_NUMBER),
                    static_cast<int>(parseCommand("P,abc,0.2,1", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_NUMBER),
                    static_cast<int>(parseCommand("P,nan,0.2,1", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_RANGE),
                    static_cast<int>(parseCommand("P,0.1,0.2,2", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_RANGE),
                    static_cast<int>(parseCommand("M,3", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_RANGE),
                    static_cast<int>(parseCommand("G,Z,1,2,3", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_ARGS),
                    static_cast<int>(parseCommand("W,1", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_ARGS),
                    static_cast<int>(parseCommand("G,X,1,2", cmd)));
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_NUMBER),
                    static_cast<int>(parseCommand("M,2x", cmd)));
}

static void test_protocolo_linea_demasiado_larga() {
  char long_line[PROTOCOL_LINE_MAX + 10];
  memset(long_line, 'A', sizeof(long_line) - 1);
  long_line[sizeof(long_line) - 1] = '\0';
  SerialCommand cmd;
  TEST_ASSERT_EQUAL(static_cast<int>(ParseStatus::BAD_ARGS),
                    static_cast<int>(parseCommand(long_line, cmd)));
}

static void test_protocolo_textos_de_error() {
  TEST_ASSERT_EQUAL_STRING("numero_invalido",
                           parseStatusMessage(ParseStatus::BAD_NUMBER));
  TEST_ASSERT_EQUAL_STRING("P", commandName(CommandType::POSE));
  TEST_ASSERT_EQUAL_STRING("?", commandName(CommandType::NONE));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_pid_salida_positiva_para_error_positivo);
  RUN_TEST(test_pid_derivativo_sobre_medicion_sin_golpe_de_setpoint);
  RUN_TEST(test_pid_antiwindup_no_acumula_con_salida_saturada);
  RUN_TEST(test_pid_limite_de_integral);
  RUN_TEST(test_pid_limitador_de_velocidad);
  RUN_TEST(test_pid_dt_invalido_no_cambia_salida);
  RUN_TEST(test_protocolo_p_valido);
  RUN_TEST(test_protocolo_comandos_validos);
  RUN_TEST(test_protocolo_rechaza_lineas_invalidas);
  RUN_TEST(test_protocolo_linea_demasiado_larga);
  RUN_TEST(test_protocolo_textos_de_error);
  return UNITY_END();
}
