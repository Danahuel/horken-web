import time

import can
import pytest

from horken_diag import analysis, collector, j1939, kb, simulator


def test_id_roundtrip_pdu1_and_pdu2():
    # DM1 desde el motor: 0x18FECA00
    jid = j1939.J1939Id.parse(0x18FECA00)
    assert (jid.priority, jid.pgn, jid.source, jid.destination) == (6, 65226, 0, 0xFF)
    # Petición dirigida a 0x00 desde 0xF9
    req = j1939.J1939Id.parse(0x18EA00F9)
    assert (req.pgn, req.destination, req.source) == (0xEA00, 0x00, 0xF9)
    assert req.to_can_id() == 0x18EA00F9


def test_dm1_decode_known_bytes():
    # Lámpara ámbar, SPN 100 FMI 1 OC 3 (ejemplo J1939-73)
    payload = bytes([0b00000100, 0xFF, 0x64, 0x00, 0x01, 0x03, 0xFF, 0xFF])
    lamps, dtcs = j1939.decode_dm(payload, 0, True)
    assert lamps.amber_warning == 1 and lamps.red_stop == 0
    assert len(dtcs) == 1 and (dtcs[0].spn, dtcs[0].fmi, dtcs[0].occurrences) == (100, 1, 3)


def test_dm1_no_faults():
    _, dtcs = j1939.decode_dm(bytes([0, 0xFF, 0, 0, 0, 0, 0xFF, 0xFF]), 0, True)
    assert dtcs == []


def test_dm_encode_decode_19bit_spn():
    raw = j1939.encode_dm(j1939.Lamps(mil=1), [(520210, 2, 1), (4364, 18, 5)])
    lamps, d = j1939.decode_dm(raw, 0x3D, True)
    assert lamps.mil == 1
    assert [(x.spn, x.fmi, x.occurrences) for x in d] == [(520210, 2, 1), (4364, 18, 5)]


def test_bam_reassembly():
    payload = bytes(range(30))
    tp = j1939.TransportReassembler()
    out = None
    for cid, data in j1939.bam_frames(j1939.PGN_DM1, 0x3D, payload):
        out = tp.feed(j1939.J1939Id.parse(cid), data) or out
    assert out == (j1939.PGN_DM1, 0x3D, payload)


def test_engine_hours_scaling_and_not_available():
    data = (round(4213.4 / 0.05)).to_bytes(4, "little") + b"\xFF\xFF\xFF\xFF"
    p = j1939.decode_params(j1939.PGN_HOURS, data)
    assert p["engine_hours"] == pytest.approx(4213.4)
    assert "total_revolutions" not in p  # 0xFFFFFFFF = no disponible


def test_enrich_known_and_proprietary():
    d = kb.enrich_dtc(j1939.Dtc(100, 1, 1, 0, True))
    assert d["critical"] and d["severity"] == 5 and d["warning"]
    e = kb.enrich_dtc(j1939.Dtc(100, 4, 1, 0, True))  # eléctrico -> sensor, no crítico
    assert not e["critical"] and "Sensor" in e["parts"][0]["nombre"]
    p = kb.enrich_dtc(j1939.Dtc(520210, 2, 1, 0xE6, True))
    assert p["proprietary"] and not p["known"]
    assert 1 <= p["difficulty"] <= 5


def test_tamper_clean_machine():
    ecus = {0: {"name": "Motor", "engine_hours": 3000, "total_revolutions": 3000 * 60 * 1500, "total_fuel_l": 3000 * 15},
            0x17: {"name": "Cuadro", "engine_hours": 3001}}
    r = analysis.analyze_counters(ecus, "excavadora_20t")
    assert r["verdict"] == "ok" and r["checks"] == 3


def test_tamper_history_rollback():
    ecus = {0: {"name": "Motor", "engine_hours": 2000}}
    r = analysis.analyze_counters(ecus, history=[{"date": "2026-01-10", "engine_hours": 5000}])
    assert r["verdict"] == "manipulado"


@pytest.mark.parametrize("scenario,verdict,mods", [("cat320", "manipulado", "ok"),
                                                   ("hamm", "ok", "ok"),
                                                   ("arjes", "manipulado", "alta")])
def test_end_to_end_simulator(scenario, verdict, mods):
    ch = f"test-{scenario}"
    mbus, tbus = can.Bus(interface="virtual", channel=ch), can.Bus(interface="virtual", channel=ch)
    sim = simulator.SimulatedMachine(mbus, scenario)
    st = collector.MachineState(simulator.SCENARIOS[scenario]["machine_class"])
    sess = collector.DiagnosticSession(tbus, st)
    sim.start(); sess.start()
    try:
        time.sleep(1.3)
        sess.request_all()
        time.sleep(1.5)
        snap = st.snapshot()
    finally:
        sess.stop(); sim.stop(); mbus.shutdown(); tbus.shutdown()
    expected = sum(len(e["dm1"]) for e in simulator.SCENARIOS[scenario]["ecus"].values())
    assert snap["summary"]["active_dtcs"] == expected
    assert snap["tamper"]["verdict"] == verdict
    assert snap["modifications"]["level"] == mods
    assert snap["live"]["rpm"]["value"] > 500
