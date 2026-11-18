"""Grabar una máquina y reproducirla da el mismo diagnóstico."""
import threading
import time

import can

from medikktion import collector, simulator
from medikktion.recorder import Recorder, duration, replay


def _read(bus, scenario_class, seconds, rec=None, folder=None):
    st = collector.MachineState(scenario_class)
    sess = collector.DiagnosticSession(bus, st)
    sess.start()
    if rec:
        rec.start(sess.notifier)
    time.sleep(1.2)
    sess.request_all()
    time.sleep(seconds)
    if rec:
        rec.stop()
    snap = st.snapshot()
    sess.stop()
    return snap


def test_record_then_replay_gives_same_diagnosis(tmp_path):
    sc = simulator.SCENARIOS["cat320"]
    mbus, tbus = can.Bus(interface="virtual", channel="rec1"), can.Bus(interface="virtual", channel="rec1")
    sim = simulator.SimulatedMachine(mbus, "cat320")
    sim.start()
    rec = Recorder(tmp_path, "prueba")
    try:
        original = _read(tbus, sc["machine_class"], 1.5, rec)
    finally:
        sim.stop(); mbus.shutdown(); tbus.shutdown()
    assert rec.path.exists() and rec.frames > 100 and rec.status()["file"] == "prueba.blf"
    assert duration(rec.path) > 2

    pbus, rbus = can.Bus(interface="virtual", channel="rep1"), can.Bus(interface="virtual", channel="rep1")
    th = threading.Thread(target=replay, args=(rec.path, pbus, 4.0), daemon=True)
    st = collector.MachineState(sc["machine_class"])
    sess = collector.DiagnosticSession(rbus, st)
    sess.start()
    th.start()
    th.join(timeout=10)
    time.sleep(0.3)
    replayed = st.snapshot()
    sess.stop(); pbus.shutdown(); rbus.shutdown()

    for key in ("active_dtcs", "history_dtcs", "ecus"):
        assert replayed["summary"][key] == original["summary"][key]
    assert replayed["tamper"]["verdict"] == original["tamper"]["verdict"] == "manipulado"
    assert replayed["machine"]["serial"] == "SIM0001234"
