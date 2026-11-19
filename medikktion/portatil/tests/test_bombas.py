"""Prueba de bombas: veredictos, lectura por centralita y aprendizaje desde el manómetro."""
import time

import can

from medikktion import collector, hidraulica, simulator
from medikktion.pricing import Pricing
from medikktion.recorder import Recorder


def _readings(p1, p2, pil=40, sb=(32, 33)):
    return {"reposo": {"pump1_bar": {"value": sb[0]}, "pump2_bar": {"value": sb[1]}},
            "alivio_p1": {"pump1_bar": {"value": p1}}, "alivio_p2": {"pump2_bar": {"value": p2}},
            "pilotaje": {"pilot_bar": {"value": pil}}}


def test_evaluate_worn_pump_gets_fault_and_cost():
    steps = hidraulica.steps_for("excavadora_20t", 343, 40)
    r = hidraulica.evaluate(steps, _readings(345, 305), Pricing(rate=75, machine_class="excavadora_20t"))
    assert r["verdict"] == "mal"
    assert [f["code"] for f in r["faults"]] == ["BOMBA 2 · ALIVIO"]
    assert r["faults"][0]["cost_max_eur"] > 18000          # peor caso: bomba nueva original
    assert r["comparison"]["diff_pct"] > 10


def test_evaluate_both_low_points_to_main_relief_and_high_is_flagged():
    steps = hidraulica.steps_for("excavadora_20t", 343, 40)
    r = hidraulica.evaluate(steps, _readings(300, 302))
    assert [f["code"] for f in r["faults"]] == ["BOMBAS 1+2"]
    r = hidraulica.evaluate(steps, _readings(372, 344, pil=31))
    codes = [f["code"] for f in r["faults"]]
    assert "BOMBA 1 · ALTA" in codes and "PILOTAJE" in codes
    r = hidraulica.evaluate(steps, _readings(344, 341))
    assert r["verdict"] == "ok" and not r["faults"]


def _run_test(st, sim, value_of=None, wait=3.0):
    st.start_pump_test(343, 40, on_step=sim.set_operator)
    for _ in range(4):
        time.sleep(wait)
        if value_of:      # mecánico leyendo el manómetro
            st.pump_action("manual", {ch: value_of(ch) for ch in st.pump_test.step["channels"]})
        else:
            st.pump_action("capturar")
        st.pump_action("siguiente")
    st.pump_action("terminar")


def test_pump_test_reads_pressures_from_can_profile():
    ch = "bomb-can"
    mb, tb = can.Bus(interface="virtual", channel=ch), can.Bus(interface="virtual", channel=ch)
    sim = simulator.SimulatedMachine(mb, "cat320")
    st = collector.MachineState("excavadora_20t")
    sess = collector.DiagnosticSession(tb, st)
    sim.start(); sess.start()
    try:
        time.sleep(1.0); sess.request_all(); time.sleep(1.5)
        _run_test(st, sim)
        snap = st.snapshot()
    finally:
        sess.stop(); sim.stop(); mb.shutdown(); tb.shutdown()
    assert snap["pressures"]["profile"] == "simulador_cat320.json"
    res = snap["pump_test"]["result"]
    status = {(c["step"], c["channel"]): c["status"] for c in res["checks"]}
    assert status[("alivio_p1", "pump1_bar")] == "ok" and status[("alivio_p2", "pump2_bar")] == "baja"
    assert {c["source"] for c in res["checks"]} == {"centralita"}
    assert any(d["kind"] == "prueba" for d in snap["dtcs"])          # cuenta en averías, coste y compra


def test_profile_is_learned_from_a_manometer_test(tmp_path):
    """Máquina sin perfil: el mecánico escribe el manómetro; la grabación revela qué bytes son."""
    ch = "bomb-learn"
    mb, tb = can.Bus(interface="virtual", channel=ch), can.Bus(interface="virtual", channel=ch)
    sim = simulator.SimulatedMachine(mb, "cat320")
    st = collector.MachineState("excavadora_20t")
    st.pressure_profiles = []                                        # sin perfil: no sabemos dónde van
    sess = collector.DiagnosticSession(tb, st)
    rec = Recorder(tmp_path, "aprende")
    sim.start(); sess.start()
    try:
        time.sleep(1.0)
        rec.start(sess.notifier)
        gauge = {"pump1_bar": "p1", "pump2_bar": "p2", "pilot_bar": "pilot"}
        # la aguja del manómetro: el valor real con un error de lectura de ±1 %
        _run_test(st, sim, value_of=lambda c: round(sim.motor.s[gauge[c]] * 1.01))
        time.sleep(0.5)
        path = rec.stop()
    finally:
        sess.stop(); sim.stop(); mb.shutdown(); tb.shutdown()
    assert "pump1_bar" not in st.live                                # nada se decodificó por CAN
    prof = hidraulica.profile_from_recording(path, 343, 40, {"pump_test": {"marks": st.pump_test.marks}},
                                             "caterpillar", "320")
    sig = prof["senales"]
    assert prof["verificado"] == "manometro"
    assert (sig["pump1_bar"]["pgn"], sig["pump1_bar"]["byte"], sig["pump1_bar"]["escala"]) == (0xFF2A, 0, 0.1)
    assert (sig["pump2_bar"]["byte"], sig["pump2_bar"]["escala"]) == (2, 0.1)
    assert sig["pilot_bar"]["byte"] == 4
