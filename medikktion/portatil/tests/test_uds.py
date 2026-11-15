import time

import can

from medikktion import collector, simulator, uds


def test_format_dtc():
    assert uds.format_dtc(0x01234A) == "P0123-4A"
    assert uds.format_dtc(0xC07388) == "U0073-88"
    assert uds.format_dtc(0x91A413) == "B11A4-13"


def test_enrich_generic_code_uses_obd_database():
    d = uds.enrich_uds(0x011513, 0x09, "Motor")   # P0115 circuito abierto, activa + confirmada
    assert d["known"] and "Coolant" in d["name"]
    assert d["active"] and d["fault_type"] == "electrico" and d["fmi_text"] == "Circuito abierto"


def test_uds_scan_against_simulated_ecu():
    ch = "uds-test"
    ecu_bus, tool_bus = can.Bus(interface="virtual", channel=ch), can.Bus(interface="virtual", channel=ch)
    sc = simulator.SCENARIOS["fuchs"]["uds"][0]
    ecu = simulator.SimulatedUdsEcu(ecu_bus, sc["addr"], sc["dtcs"], sc["dids"])
    ecu.start()
    st = collector.MachineState()
    sess = collector.DiagnosticSession(tool_bus, st)
    sess.start()
    try:
        targets = [t for t in uds.default_targets() if t.key in ("UDS 29b 0x27", "UDS 29b 0x00")]
        found = uds.UdsScanner(tool_bus, sess.notifier, timeout=0.3).scan(st, targets)
        snap = st.snapshot()
    finally:
        sess.stop(); ecu.stop(); ecu_bus.shutdown(); tool_bus.shutdown()
    assert found == 1
    codes = {d["code"]: d for d in snap["dtcs"]}
    assert codes["B11A4-13"]["active"] and not codes["U0073-88"]["active"]
    assert snap["machine"]["vin"] == "SIMFUCHSMHL350X21"
    assert "UDS" in snap["protocols"]
