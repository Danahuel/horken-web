"""El programa solo puede PREGUNTAR a la máquina: nunca borrar, escribir ni reprogramar."""
import time

import can
import pytest

from medikktion import collector, j1939, seguridad, simulator, uds


def _req(pgn, da=0xFF):
    cid, data = j1939.build_request(pgn, 0xF9, da)
    return can.Message(arbitration_id=cid, data=data, is_extended_id=True)


def _uds29(payload, sa=0x00):
    return can.Message(arbitration_id=0x18DA0000 | (sa << 8) | 0xF9, data=bytes(payload).ljust(8, b"\xCC"),
                       is_extended_id=True)


@pytest.mark.parametrize("msg", [
    _req(j1939.PGN_DM11), _req(j1939.PGN_DM3), _req(0xDF00), _req(0xD900),  # borrar activas/históricas, DM13, DM14
    _uds29([0x04, 0x14, 0xFF, 0xFF, 0xFF]),                              # UDS borrar averías
    _uds29([0x05, 0x2E, 0xF1, 0x90, 0x00, 0x00]),                        # UDS escribir dato
    _uds29([0x04, 0x31, 0x01, 0x02, 0x03]),                              # UDS rutina
    _uds29([0x02, 0x10, 0x02]), _uds29([0x02, 0x27, 0x01]), _uds29([0x02, 0x11, 0x01]),  # sesión, seguridad, reset
    _uds29([0x10, 0x14, 0x34, 0x00, 0x44, 0x00, 0x00, 0x00]),            # petición larga (programación)
    can.Message(arbitration_id=0x7E0, data=bytes([0x04, 0x14, 0xFF, 0xFF, 0xFF, 0, 0, 0]), is_extended_id=False),
    can.Message(arbitration_id=0x7DF, data=bytes([0x01, 0x04, 0, 0, 0, 0, 0, 0]), is_extended_id=False),  # OBD modo 04
    can.Message(arbitration_id=0x0CFE6CEE, data=bytes(8), is_extended_id=True),   # emitir datos propios
    can.Message(arbitration_id=0x1CECFFF9, data=bytes([32, 14, 0, 2, 0xFF, 0xCA, 0xFE, 0]), is_extended_id=True),  # BAM
])
def test_frames_that_change_the_machine_are_blocked(msg):
    with pytest.raises(seguridad.BlockedFrame):
        seguridad.check(msg)


def test_guarded_bus_never_lets_a_clear_reach_the_machine():
    ch = "seg-1"
    machine, tool = can.Bus(interface="virtual", channel=ch), can.Bus(interface="virtual", channel=ch)
    try:
        seguridad.guard(tool)
        with pytest.raises(can.CanError):
            tool.send(_req(j1939.PGN_DM11))
        assert machine.recv(0.2) is None                     # no ha salido nada al bus
        tool.send(_req(j1939.PGN_HOURS))                     # una lectura sí sale
        assert machine.recv(0.5) is not None
    finally:
        machine.shutdown(); tool.shutdown()


@pytest.mark.parametrize("scenario", ["cat320", "fuchs"])
def test_full_reading_only_sends_read_requests(scenario):
    """Lectura completa (J1939 + descubrimiento y escaneo UDS): se espía cada trama del portátil."""
    ch = f"seg-{scenario}"
    mbus, tbus, spy = (can.Bus(interface="virtual", channel=ch) for _ in range(3))
    sim = simulator.SimulatedMachine(mbus, scenario)
    st = collector.MachineState(simulator.SCENARIOS[scenario]["machine_class"])
    sess = collector.DiagnosticSession(tbus, st)
    sim.start(); sess.start()
    try:
        time.sleep(1.0)
        sess.request_all()
        uds.UdsScanner(tbus, sess.notifier, timeout=0.3).scan(st)     # descubre y pregunta a todas
        time.sleep(1.0)
    finally:
        sess.stop(); sim.stop()
    sent = []
    while (m := spy.recv(0)) is not None:
        ours = (m.is_extended_id and (m.arbitration_id & 0xFF) == 0xF9) or \
               (not m.is_extended_id and (m.arbitration_id == 0x7DF or 0x7E0 <= m.arbitration_id <= 0x7E7))
        if ours:
            sent.append(m)
    mbus.shutdown(); tbus.shutdown(); spy.shutdown()
    assert len(sent) > 20
    for m in sent:
        seguridad.check(m)                                   # todas son lecturas permitidas
    assert st.snapshot()["summary"]["active_dtcs"] > 0
