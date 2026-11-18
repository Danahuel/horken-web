from types import SimpleNamespace

import obd

from medikktion import collector, j1587, obd_car


def test_j1587_split_and_decode():
    # PID 110 (1 byte), PID 190 (2 bytes), PID 247 (variable: 4 bytes)
    data = bytes([110, 212, 190, 0x40, 0x1F, 247, 4]) + (84268).to_bytes(4, "little")
    pids = dict(j1587.split_pids(data))
    assert j1587.PID_DECODERS[110][1](pids[110]) == 100.0           # 212 °F
    assert j1587.PID_DECODERS[190][1](pids[190]) == 2000            # 0x1F40 * 0.25
    assert j1587.PID_DECODERS[247][1](pids[247]) == 4213.4


def test_j1587_dtcs_and_reader():
    st = collector.MachineState()
    r = j1587.J1587Reader.__new__(j1587.J1587Reader)
    r.state, r.dtcs = st, {}
    # PID 194: PID 100 FMI 1 activa con contador 3; SID 2 (inyector 2) FMI 5 inactiva
    table = bytes([100, 0x80 | 0x01, 3, 2, 0x20 | 0x40 | 0x05])
    r.handle(128, bytes([194, len(table)]) + table + bytes([110, 200, 247, 4]) + (100000).to_bytes(4, "little"))
    snap = st.snapshot()
    codes = {d["code"]: d for d in snap["dtcs"]}
    assert codes["MID 128 PID 100 FMI 1"]["active"] and codes["MID 128 PID 100 FMI 1"]["critical"]
    inj = codes["MID 128 SID 2 FMI 5"]
    assert not inj["active"] and inj["name"] == "Inyector cilindro 2" and inj["known"]
    assert snap["live"]["coolant_c"]["value"] == 93.3
    assert any(e["engine_hours"] == 5000 for e in snap["ecus"])


class FakeObd:
    """Imita obd.OBD con un coche que tiene averías borradas hace 12 km."""

    answers = {
        "VIN": "WVWZZZSIM00000001", "CALIBRATION_ID": "SIMCAL123", "CVN": "1A2B3C4D",
        "GET_DTC": [("P0118", "x"), ("P0300", "y")], "GET_CURRENT_DTC": [("P0171", "z")],
        "PERMANENT_DTC": [("P0118", "x"), ("P0420", "w")], "FREEZE_DTC": "P0118",
        "FF_rpm": 2150.0, "FF_coolant_c": 104.0, "FF_load_pct": 63.0, "FF_speed_kmh": 88.0,
        "DISTANCE_SINCE_DTC_CLEAR": 12.0, "WARMUPS_SINCE_DTC_CLEAR": 2.0,
        "RPM": 820.0, "COOLANT_TEMP": 88.0, "ODOMETER": 145000.0,
    }

    def supports(self, cmd):
        return cmd.name in self.answers

    def query(self, cmd, force=False):
        v = self.answers.get(cmd.name)
        return SimpleNamespace(is_null=lambda: v is None, value=v)


def test_obd_car_reading():
    st = collector.MachineState("coche")
    obd_car.read_car(FakeObd(), st, cluster_km=98000, samples=1)
    snap = st.snapshot()
    codes = {d["code"]: d for d in snap["dtcs"]}
    assert codes["P0118"]["active"] and "Coolant" in codes["P0118"]["name"]
    assert not codes["P0171"]["active"]
    titles = [e["title"] for e in snap["tamper"]["evidence"]]
    assert "Averías borradas recientemente" in titles
    assert "Km del cuadro distintos a los de la centralita de motor" in titles
    assert snap["tamper"]["verdict"] == "manipulado"
    assert snap["machine"]["vin"] == "WVWZZZSIM00000001"
    assert snap["live"]["rpm"]["value"] == 820.0
    assert codes["P0420"]["kind"] == "permanent" and not codes["P0420"]["active"]
    assert codes["P0118"]["kinds"] == ["active", "permanent"]
    assert codes["P0118"]["freeze"] == {"rpm": 2150.0, "coolant_c": 104.0, "load_pct": 63.0, "speed_kmh": 88.0}
    assert "Averías permanentes que alguien borró" in titles


def test_dbc_decodes_proprietary_message(tmp_path):
    from medikktion.dbc import DbcDecoder
    dbc = tmp_path / "maquina.dbc"
    dbc.write_text('''VERSION ""
BS_:
BU_: GRUA
BO_ 2365526246 BrazoGrua: 8 GRUA
 SG_ PresionBrazo : 0|16@1+ (0.1,0) [0|500] "bar" Vector__XXX
 SG_ AnguloBrazo : 16|8@1+ (1,-40) [-40|90] "grados" Vector__XXX
''')
    dec = DbcDecoder(dbc)
    st = collector.MachineState(dbc=dec)
    # 2365526246 = 0x8CFF10E6 → id extendido 0x0CFF10E6: PGN 0xFF10 desde 0xE6
    st.process(0x0CFF10E6, bytes([0xB8, 0x0B, 75, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]))
    live = st.snapshot()["live"]
    assert live["dbc.PresionBrazo"]["value"] == 300.0 and live["dbc.PresionBrazo"]["unit"] == "bar"
    assert live["dbc.AnguloBrazo"]["value"] == 35.0
