"""Lógica del asistente de ejes, sin abrir ventanas ni usar hardware."""

from calibration import AxisAssistant


class LinkFalso:
    def __init__(self):
        self.commands = []

    def send(self, command):
        self.commands.append(command)


def ejecutar(actual_x, actual_y, direccion_x, direccion_y):
    link = LinkFalso()
    assistant = AxisAssistant(
        link,
        tilt_deg=2.0,
        current_invert_x=actual_x,
        current_invert_y=actual_y,
    )
    assistant.start()
    assistant.handle_key(direccion_x)
    assistant.handle_key("enter")
    assistant.handle_key(direccion_y)
    return assistant, link


def test_ejes_correctos_conservan_las_banderas():
    assistant, _ = ejecutar(False, False, "right", "up")
    assert assistant.done is True
    assert assistant.invert_x is False
    assert assistant.invert_y is False


def test_direccion_opuesta_invierte_las_banderas():
    assistant, _ = ejecutar(False, False, "left", "down")
    assert assistant.done is True
    assert assistant.invert_x is True
    assert assistant.invert_y is True


def test_si_ya_estaba_invertido_y_ahora_va_bien_se_conserva():
    assistant, _ = ejecutar(True, True, "right", "up")
    assert assistant.done is True
    assert assistant.invert_x is True
    assert assistant.invert_y is True


def test_si_ya_estaba_invertido_y_sigue_al_reves_se_desactiva():
    assistant, _ = ejecutar(True, True, "left", "down")
    assert assistant.done is True
    assert assistant.invert_x is False
    assert assistant.invert_y is False


def test_envia_los_comandos_de_prueba_y_vuelve_a_apagado():
    assistant, link = ejecutar(False, False, "right", "up")
    assert "M,1" in link.commands
    assert "A,2.00,0.00" in link.commands
    assert "A,0.00,2.00" in link.commands
    assert link.commands[-1] == "M,0"
    assert assistant.active is False


def test_cancelar_manda_nivel_y_apagado():
    link = LinkFalso()
    assistant = AxisAssistant(link)
    assistant.start()
    assistant.cancel()
    assert assistant.active is False
    assert link.commands[-2:] == ["A,0.00,0.00", "M,0"]
