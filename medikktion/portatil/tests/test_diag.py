import time

import can
import pytest

from medikktion import analysis, collector, j1939, kb, simulator


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


def test_plate_and_usage_cross_checks():
    ecus = {0: {"name": "Motor", "engine_hours": 2000.0, "idle_hours": 2300.0, "cleared_min": 30,
                "component": {"serial": "ABC12345"}, "vin": "WVWZZZ1KZ6W000001"}}
    usage, ev, mods = analysis.cross_checks(ecus, {"serial": "ABC12345", "hours": 6100, "year": 2012}, year_now=2026)
    titles = {e["title"] for e in ev}
    assert "Horas al ralentí mayores que las horas totales" in titles
    assert "Averías borradas hace muy poco" in titles
    assert "Las horas del cuadro no coinciden con la centralita" in titles
    assert "Muy pocas horas para su antigüedad" in titles
    assert mods == []                                   # mismo nº de serie; el VIN no se compara
    _, _, mods = analysis.cross_checks(ecus, {"serial": "XYZ99999"})
    assert mods and "no coincide" in mods[0]["title"]
    assert usage["idle_pct"] == 115.0 and usage["hours_per_year"] == 138


def test_new_j1939_pgns():
    from medikktion import j1939 as J
    assert J.decode_vin(b"SIMCAT32000001234*") == "SIMCAT32000001234"
    io = J.decode_params(J.PGN_IO, (int(1000 / 0.5)).to_bytes(4, "little") + (int(250 / 0.05)).to_bytes(4, "little"))
    assert io == {"idle_fuel_l": 1000.0, "idle_hours": 250.0}
    dm21 = J.decode_params(J.PGN_DM21, b"\xff\xff\xff\xff" + (90).to_bytes(2, "little") + (600).to_bytes(2, "little"))
    assert dm21 == {"mil_min": 90.0, "cleared_min": 600.0}


def test_dm4_freeze_frame_roundtrip_and_dm_kinds():
    from medikktion import j1939 as J
    raw = J.encode_dm4([{"spn": 100, "fmi": 18, "occurrences": 2, "rpm": 1650, "coolant_c": 94, "load_pct": 78,
                         "boost_kpa": 150, "speed_kmh": 0}])
    fr = J.decode_dm4(raw)[0]
    assert (fr["spn"], fr["fmi"], fr["rpm"], fr["coolant_c"], fr["load_pct"], fr["boost_kpa"]) == (100, 18, 1650, 94, 78, 150)
    st = collector.MachineState()
    st.process(J.J1939Id(6, J.PGN_DM28, 0x3D, 0xFF).to_can_id(), J.encode_dm(J.Lamps(), [(3364, 18, 0)]))
    st.process(J.J1939Id(6, J.PGN_DM6, 0x00, 0xFF).to_can_id(), J.encode_dm(J.Lamps(), [(102, 18, 1)]))
    snap = st.snapshot()
    kinds = {d["code"]: d["kind"] for d in snap["dtcs"]}
    assert kinds == {"SPN 3364 FMI 18": "permanent", "SPN 102 FMI 18": "pending"}
    assert snap["summary"]["active_dtcs"] == 0 and snap["summary"]["permanent_dtcs"] == 1
    assert any(e["title"] == "Averías permanentes que alguien borró" for e in snap["tamper"]["evidence"])


def test_maintenance_and_purchase_report():
    from medikktion import purchase
    from medikktion.pricing import Pricing
    pr = Pricing.from_config({"pais": "ES"}, "excavadora_20t", travel_km=30)
    m = purchase.maintenance(4380, "excavadora_20t", pr, has_scr=True)
    ids = {i["id"]: i for i in m["items"]}
    assert ids["aceite_motor"]["next_due_h"] == 4500 and ids["aceite_motor"]["remaining_h"] == 120
    assert ids["aceite_hidraulico"]["next_due_h"] == 8000 and "transmision" not in ids     # excavadora de cadenas
    assert "Aceite y filtro de motor" in m["entry"]["items"] and m["entry"]["cost_min_eur"] > 0
    dtcs = [{"active": True, "kind": "active", "cost_min_eur": 1000, "cost_max_eur": 3000},
            {"active": False, "kind": "permanent", "cost_min_eur": 500, "cost_max_eur": 900}]
    tamper = {"verdict": "manipulado", "reported_hours": 4000, "estimated_real_hours": 9000}
    r = purchase.purchase_report(dtcs, tamper, {"score": 30}, {}, m, pr, "excavadora_20t", asking_price=80000)
    assert r["verdict"] == "no_comprar" and r["hidden_hours"] == 5000 and r["hidden_hours_value_eur"] == 30000
    assert r["repairs_max_eur"] == 3900 and r["recommended_discount_eur"] >= 30000 + 3900
    assert r["max_offer_eur"] == 80000 - r["recommended_discount_eur"] or r["max_offer_eur"] >= 80000 - r["recommended_discount_eur"]


def test_real_repair_costs_override_estimate():
    from medikktion.j1939 import Dtc
    from medikktion.pricing import Pricing
    from medikktion.sinks import _collect_costs
    costs = _collect_costs([{"work_orders": [{"code": "SPN 3226 FMI 2", "cost_eur": 1850}]}])
    pr = Pricing.from_config({"pais": "ES", "labour_rate": 40}, "excavadora_20t", real_costs=costs)
    assert pr.rate == 75                                       # nunca por debajo del mínimo de España
    d = kb.enrich_dtc(Dtc(3226, 2, 1, 0x3D, True), labour_rate=pr)
    assert d["cost_min_eur"] >= 1850 and d["cost_max_eur"] >= 1850 * 1.1
    assert d["price_source"] == "1 reparación(es) real(es)"
    assert Pricing.from_config({"pais": "DE"}).rate == 120


def test_j1939da_import(tmp_path, monkeypatch):
    from openpyxl import Workbook
    from medikktion import j1939da
    wb = Workbook()
    ws = wb.active
    ws.title = "SPNs & PGNs"
    ws.append(["J1939 Digital Annex"])
    ws.append(["PGN", "Parameter Group Label", "SPN", "SPN Name", "SPN Description", "Units"])
    ws.append([65262, "Engine Temperature 1", 110, "Engine Coolant Temperature", "Temperature of liquid...", "°C"])
    ws.append([64892, "DPF Control", 3700, "Aftertreatment DPF Active Regeneration Status", "State of DPF regen", "bit"])
    xl = tmp_path / "da.xlsx"
    wb.save(xl)
    out = tmp_path / "spn_da.json"
    assert j1939da.import_xlsx(xl, out) == 2
    monkeypatch.setattr(kb, "_DIR", tmp_path)
    kb.spn_da.cache_clear()
    d = kb.enrich_dtc(j1939.Dtc(3700, 31, 1, 0x3D, True))
    assert d["name"] == "Aftertreatment DPF Active Regeneration Status" and d["known"] and d["name_language"] == "en"
    kb.spn_da.cache_clear()
