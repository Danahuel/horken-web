"""Simulador de máquinas: genera en un bus CAN las mismas tramas J1939 que una
máquina real (varias centralitas, averías activas/históricas, contadores,
datos en vivo y respuesta a peticiones). Sirve para probar todo el sistema
sin adaptador. Los números de serie/software son ficticios (prefijo SIM).
"""
from __future__ import annotations

import math
import random
import threading
import time

import can
import isotp

from . import j1939
from .fisica import Motor, Perfil
from .j1939 import J1939Id, Lamps


def _u(v, n):
    return int(round(v)).to_bytes(n, "little")


def _pad(b: bytes) -> bytes:
    return b.ljust(8, b"\xFF")


SCENARIOS = {
    "cat320": {
        "placa": {"make": "Caterpillar", "model": "320", "serial": "SIM0001234", "year": 2014, "hours": 4213},
        "descripcion": "Caterpillar 320 (excavadora) con horas rebajadas en la ECU de motor y 6 averías activas",
        "machine_class": "excavadora_20t",
        "ecus": {
            0x00: {"component": "CAT*320*SIM0001234*FLOTA-07*", "software": ["SIM-ENG-5432109-00", "SIM-FLASH-2023"],
                   "ecu_id": "SIM-472-1234*SIMECU001*MOTOR*ECM*CATERPILLAR*",
                   "hours": 4213.4, "revs": 829_600_000, "fuel": 148_100,
                   "dm19": [("SIM-CAL-C7.1-A07", 0x5A3C91E2)],
                   "vin": "SIMCAT32000001234", "idle_h": 4444.6, "idle_fuel": 15110, "cleared_min": 95, "mil_min": 610,
                   "dm1": [(651, 5, 3), (100, 18, 2)], "lamps": Lamps(amber_warning=1),
                   "dm2": [(97, 15, 12), (168, 18, 4), (3719, 16, 7)],
                   "dm6": [(102, 18, 1)],
                   "dm4": [{"spn": 100, "fmi": 18, "occurrences": 2, "rpm": 1650, "coolant_c": 94, "load_pct": 78,
                            "boost_kpa": 150, "speed_kmh": 0}]},
            0x3D: {"software": ["SIM-ATC-3311-02"], "dm1": [(4364, 18, 5), (3226, 2, 1)],
                   "lamps": Lamps(mil=1, amber_warning=1), "dm2": [(3364, 18, 2)],
                   "dm28": [(3364, 18, 0), (3216, 2, 0)]},
            0x17: {"component": "CAT*320*SIM0001234*FLOTA-07*", "software": ["SIM-MON-8812-01"],
                   "hours": 9876.2, "dm1": [], "dm2": []},
            0xE6: {"component": "CAT*320*SIM0001234*FLOTA-07*", "software": ["SIM-MCH-5590-04"],
                   "hours": 9874.9, "dm1": [(1638, 16, 2), (520210, 2, 1)], "lamps": Lamps(amber_warning=1),
                   "dm2": []},
        },
        "perfil": Perfil(rated_rpm=1800, coolant_set=93, hyd_set=90.5, oil_p_rated=215, boost_max=165, fuel_idle=3.4,
                          fuel_max=24, ambient=8.5, start_coolant=66, start_hyd=78.2, start_oil=70, tank_l=410,
                          fuel_level=63.8, def_level=41.2, load_mean=0.62, seed=320,
                          relief_p1=344.0, relief_p2=304.0, pilot_bar=40.6),   # bomba 2 gastada
        # Presiones de bomba en un mensaje propio (formato inventado del simulador, no el de Cat)
        "presiones": {"pgn": 0xFF2A, "sa": 0xE6},
    },
    "fuchs": {
        "placa": {"make": "Fuchs", "model": "MHL350", "serial": "SIM-MHL-03521", "year": 2019, "hours": 7341},
        "descripcion": "Fuchs MHL (manipuladora) con motor Deutz por J1939 y controlador de máquina UDS",
        "machine_class": "manipuladora",
        "ecus": {
            0x00: {"component": "FUCHS*MHL350*SIM-MHL-03521*GRUA-2*", "software": ["SIM-DEUTZ-EMR5-4.03"],
                   "hours": 7340.5, "revs": 7340.5 * 60 * 1450, "fuel": 7340.5 * 19,
                   "dm19": [("SIM-DEUTZ-TCD6.1", 0x1F22A0B7)],
                   "idle_h": 2055.3, "idle_fuel": 8430, "cleared_min": 41000, "mil_min": 0,
                   "dm1": [(3719, 16, 3)], "lamps": Lamps(amber_warning=1), "dm2": [(110, 16, 2)],
                   "dm6": [(1638, 16, 0)]},
            0x17: {"component": "FUCHS*MHL350*SIM-MHL-03521*GRUA-2*", "software": ["SIM-FUCHS-DSP-7.2"],
                   "hours": 7341.1, "dm1": [], "dm2": []},
        },
        "uds": [{"addr": 0x27, "dtcs": [(0x91A413, 0x09), (0xC07388, 0x08)],
                 "dids": {0xF190: "SIMFUCHSMHL350X21", 0xF188: "SIM-MHL-CTRL-3.11", 0xF197: "Control maquina"}}],
        "perfil": Perfil(rated_rpm=1900, coolant_set=87, hyd_set=76.4, oil_p_rated=430, boost_max=190, fuel_idle=4.1,
                          fuel_max=29, ambient=6.0, start_coolant=71, start_hyd=63.0, start_oil=68, tank_l=480,
                          fuel_level=72.5, def_level=66.0, load_mean=0.5, cycle_s=34, seed=350),
    },
    "hamm": {
        "placa": {"make": "Hamm", "model": "H13i", "serial": "SIM-H13-00042", "year": 2020, "hours": 3121},
        "descripcion": "Rodillo Hamm sin manipulación, 1 avería leve de combustible",
        "machine_class": "rodillo",
        "ecus": {
            0x00: {"component": "HAMM*H13i*SIM-H13-00042*R-03*", "software": ["SIM-DEUTZ-EMR4-1.2"],
                   "hours": 3120.6, "revs": 3120.6 * 60 * 1550, "fuel": 3120.6 * 9.5,
                   "idle_h": 967.4, "idle_fuel": 2030, "cleared_min": 60000, "mil_min": 45,
                   "dm1": [(94, 18, 1)], "lamps": Lamps(amber_warning=1), "dm2": [(168, 17, 2)]},
            0x17: {"component": "HAMM*H13i*SIM-H13-00042*R-03*", "software": ["SIM-HAMM-DSP-3.4"],
                   "hours": 3120.4, "dm1": [], "dm2": []},
        },
        "perfil": Perfil(rated_rpm=2200, idle_rpm=900, coolant_set=84, hyd_set=58.6, oil_p_rated=360, boost_max=120,
                          fuel_idle=2.1, fuel_max=13.5, ambient=11.0, start_coolant=74, start_hyd=49, start_oil=70,
                          tank_l=190, fuel_level=48.0, def_level=80.0, load_mean=0.45, cycle_s=40, has_trans=True,
                          seed=13),
    },
    "arjes": {
        "placa": {"make": "Arjes", "model": "VZ950", "serial": "SIM-ARJ-00911", "year": 2018, "hours": 850},
        "descripcion": "Trituradora Arjes con centralita de motor procedente de otra máquina",
        "machine_class": "trituradora",
        "ecus": {
            0x00: {"component": "ARJES*VZ950*SIM-ARJ-OTRA-77*", "software": ["SIM-ENG-ARJ-7.1"],
                   "hours": 850.2, "revs": 850.2 * 60 * 1600, "fuel": 850.2 * 38,
                   "idle_h": 170.1, "idle_fuel": 1020, "cleared_min": 2400, "mil_min": 0,
                   "dm1": [(3251, 16, 4), (110, 16, 1)], "lamps": Lamps(amber_warning=1), "dm2": []},
            0x17: {"component": "ARJES*VZ950*SIM-ARJ-00911*", "software": ["SIM-ARJ-HMI-2.0"],
                   "hours": 6420.7, "dm1": [], "dm2": []},
        },
        "perfil": Perfil(rated_rpm=2100, idle_rpm=900, coolant_set=101.5, hyd_set=80.0, oil_p_rated=390, boost_max=230,
                          fuel_idle=6.0, fuel_max=58, ambient=15.5, start_coolant=88, start_hyd=72.0, start_oil=86,
                          tank_l=900, fuel_level=38.0, def_level=29.0, load_mean=0.72, cycle_s=12, seed=950),
    },
}


class SimulatedMachine:
    def __init__(self, bus: can.BusABC, scenario: str = "cat320"):
        self.bus = bus
        self.sc = SCENARIOS[scenario]
        self.name = scenario
        self._stop = threading.Event()
        self._t0 = time.time()
        self.motor = Motor(self.sc["perfil"])
        self._bam_locks: dict[int, threading.Lock] = {}
        self.values: dict = {}
        self._threads = [threading.Thread(target=self._periodic, daemon=True),
                         threading.Thread(target=self._responder, daemon=True)]

    # --- envío ---------------------------------------------------------
    def _send(self, pgn, sa, data: bytes, prio=6, dest=0xFF):
        if len(data) <= 8:
            cid = J1939Id(prio, pgn, sa, dest).to_can_id()
            self.bus.send(can.Message(arbitration_id=cid, data=_pad(data), is_extended_id=True))
        else:
            # J1939: una centralita no puede tener dos BAM a la vez; se espera turno
            with self._bam_locks.setdefault(sa, threading.Lock()):
                for cid, d in j1939.bam_frames(pgn, sa, data):
                    self.bus.send(can.Message(arbitration_id=cid, data=d, is_extended_id=True))
                    time.sleep(0.01)  # 10-200 ms entre tramas BAM

    def _dm(self, sa, which):
        e = self.sc["ecus"][sa]
        lamps = e.get("lamps", Lamps()) if which == "dm1" else Lamps()
        return j1939.encode_dm(lamps, e.get(which, []))

    def _periodic(self):
        """Emite las tramas con los valores del modelo físico (cada 100 ms)."""
        tick = 0
        while not self._stop.is_set():
            v = self.motor.step(0.1)
            self.values = v
            eng = 0x00
            self._send(j1939.PGN_EEC1, eng, bytes([0xFF, 0xFF, int(v["torque_pct"] + 125)])
                       + _u(v["rpm"] / 0.125, 2) + b"\xFF\xFF\xFF", prio=3)
            if tick % 10 == 0:
                self._send(j1939.PGN_ET1, eng, bytes([int(round(v["coolant_c"] + 40)), int(42 + 40)])
                           + _u((v["oil_temp_c"] + 273) / 0.03125, 2))
                self._send(j1939.PGN_EFLP1, eng, bytes([0xFF, 0xFF, int(92 / 0.4), int(round(v["oil_pressure_kpa"] / 4)),
                                                        0xFF, 0xFF, 0xFF, int(95 / 0.4)]))
                self._send(j1939.PGN_IC1, eng, bytes([0xFF, int(round(v["boost_kpa"] / 2)), int(round(v["intake_temp_c"] + 40))]))
                self._send(j1939.PGN_VEP1, eng, b"\xFF\xFF\xFF\xFF" + _u(v["battery_v"] / 0.05, 2))
                self._send(j1939.PGN_LFE, eng, _u(v["fuel_rate_lh"] / 0.05, 2))
                self._send(j1939.PGN_DD, 0x17 if 0x17 in self.sc["ecus"] else eng, bytes([0xFF, int(v["fuel_level_pct"] / 0.4)]))
                self._send(j1939.PGN_AMB, eng, b"\xFF\xFF\xFF" + _u((v["ambient_c"] + 273) / 0.03125, 2))
                hyd_sa = 0xE6 if 0xE6 in self.sc["ecus"] else eng
                self._send(j1939.PGN_HYD, hyd_sa, bytes([int(round(v["hyd_oil_temp_c"] + 40))]))
                if "trans_oil_temp_c" in v:
                    self._send(j1939.PGN_TRF1, 0x03 if 0x03 in self.sc["ecus"] else eng,
                               b"\xFF\xFF\xFF\xFF" + _u((v["trans_oil_temp_c"] + 273) / 0.03125, 2))
                if 0x3D in self.sc["ecus"]:
                    self._send(j1939.PGN_AT1T1, 0x3D, bytes([int(v["def_level_pct"] / 0.4)]))
                for sa in self.sc["ecus"]:
                    self._send(j1939.PGN_DM1, sa, self._dm(sa, "dm1"))
                pr = self.sc.get("presiones")
                if pr:   # mensaje "señuelo" del fabricante: caudal %, temperatura interna y contador
                    self._send(0xFF10, pr["sa"], _u(v["torque_pct"] * 10, 2) + _u((v["hyd_oil_temp_c"] + 40) * 10, 2)
                               + bytes([tick // 10 % 256]))
            pr = self.sc.get("presiones")
            if pr and "pump1_bar" in v:
                self._send(pr["pgn"], pr["sa"], _u(v["pump1_bar"] * 10, 2) + _u(v["pump2_bar"] * 10, 2)
                           + _u(v["pilot_bar"] * 10, 2) + bytes([tick % 256]))
            tick += 1
            time.sleep(0.1)

    def _respond(self, pgn, sa):
        e = self.sc["ecus"].get(sa)
        if e is None:
            return
        if pgn == j1939.PGN_COMPONENT_ID and e.get("component"):
            self._send(pgn, sa, e["component"].encode())
        elif pgn == j1939.PGN_SOFTWARE_ID and e.get("software"):
            self._send(pgn, sa, bytes([len(e["software"])]) + ("*".join(e["software"]) + "*").encode())
        elif pgn == j1939.PGN_ECU_ID and e.get("ecu_id"):
            self._send(pgn, sa, e["ecu_id"].encode())
        elif pgn == j1939.PGN_HOURS and e.get("hours") is not None:
            revs = e.get("revs")
            self._send(pgn, sa, _u(e["hours"] / 0.05, 4) + (_u(revs / 1000, 4) if revs else b"\xFF" * 4))
        elif pgn == j1939.PGN_LFC and e.get("fuel"):
            self._send(pgn, sa, _u(30 / 0.5, 4) + _u(e["fuel"] / 0.5, 4))
        elif pgn == j1939.PGN_VI and e.get("vin"):
            self._send(pgn, sa, (e["vin"] + "*").encode())
        elif pgn == j1939.PGN_IO and e.get("idle_h") is not None:
            self._send(pgn, sa, _u(e["idle_fuel"] / 0.5, 4) + _u(e["idle_h"] / 0.05, 4))
        elif pgn == j1939.PGN_DM21 and e.get("cleared_min") is not None:
            self._send(pgn, sa, b"\xFF\xFF\xFF\xFF" + _u(e["mil_min"], 2) + _u(e["cleared_min"], 2))
        elif pgn == j1939.PGN_DM19 and e.get("dm19"):
            self._send(pgn, sa, j1939.encode_dm19(e["dm19"]))
        elif pgn in (j1939.PGN_DM2, j1939.PGN_DM6, j1939.PGN_DM27, j1939.PGN_DM28, j1939.PGN_DM12, j1939.PGN_DM23):
            key = {j1939.PGN_DM2: "dm2", j1939.PGN_DM6: "dm6", j1939.PGN_DM27: "dm6", j1939.PGN_DM28: "dm28",
                   j1939.PGN_DM12: "dm12", j1939.PGN_DM23: "dm23"}[pgn]
            if e.get(key) or pgn == j1939.PGN_DM2:
                self._send(pgn, sa, self._dm(sa, key))
        elif pgn == j1939.PGN_DM4 and e.get("dm4"):
            self._send(pgn, sa, j1939.encode_dm4(e["dm4"]))

    def _responder(self):
        while not self._stop.is_set():
            msg = self.bus.recv(0.2)
            if msg is None or not msg.is_extended_id:
                continue
            jid = J1939Id.parse(msg.arbitration_id)
            if jid.pgn != j1939.PGN_REQUEST or len(msg.data) < 3:
                continue
            pgn = msg.data[0] | (msg.data[1] << 8) | (msg.data[2] << 16)
            targets = self.sc["ecus"] if jid.destination == 0xFF else [jid.destination]
            for sa in targets:
                self._respond(pgn, sa)

    def set_operator(self, action: str | None) -> None:
        """Simula lo que hace el operador en una prueba guiada (p. ej. 'alivio_p1')."""
        self.motor.operator = action

    def start(self):
        for t in self._threads:
            t.start()

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=1)


class SimulatedUdsEcu:
    """Centralita UDS mínima (0x19 averías, 0x22 identificación, 0x3E) sobre ISO-TP."""

    def __init__(self, bus: can.BusABC, address: int, dtcs, dids: dict, tester: int = 0xF9):
        self.bus, self.dtcs, self.dids = bus, dtcs, dids
        self.notifier = can.Notifier(bus, [], timeout=0.1)
        addr = isotp.Address(isotp.AddressingMode.NormalFixed_29bits, source_address=address, target_address=tester)
        self.stack = isotp.NotifierBasedCanStack(bus, self.notifier, address=addr,
                                                 params={"tx_data_min_length": 8, "blocking_send": False})
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self.address, self.tester = address, tester
        ecu = self

        class _Functional(can.Listener):
            """Contesta al "¿quién está?" funcional (TesterPresent a 0x18DBFF..)."""
            def on_message_received(self, m):
                if m.is_extended_id and (m.arbitration_id >> 16) & 0xFF == 0xDB and len(m.data) >= 2 and m.data[1] == 0x3E:
                    bus.send(can.Message(arbitration_id=0x18DA0000 | (ecu.tester << 8) | ecu.address,
                                         data=bytes([0x02, 0x7E, 0x00, 0xCC, 0xCC, 0xCC, 0xCC, 0xCC]), is_extended_id=True))
        self.notifier.add_listener(_Functional())

    def _answer(self, req: bytes) -> bytes:
        sid = req[0]
        if sid == 0x19 and len(req) >= 3 and req[1] == 0x02:
            out = bytearray([0x59, 0x02, 0xFF])
            for code, status in self.dtcs:
                if status & req[2]:
                    out += code.to_bytes(3, "big") + bytes([status])
            return bytes(out)
        if sid == 0x22 and len(req) >= 3:
            did = req[1] << 8 | req[2]
            if did in self.dids:
                return bytes([0x62, req[1], req[2]]) + self.dids[did].encode()
            return bytes([0x7F, 0x22, 0x31])
        if sid == 0x3E:
            return bytes([0x7E, 0x00])
        return bytes([0x7F, sid, 0x11])

    def _loop(self):
        while not self._stop.is_set():
            req = self.stack.recv(block=True, timeout=0.1)
            if req:
                self.stack.send(self._answer(bytes(req)))

    def start(self):
        self.stack.start()
        self._t.start()

    def stop(self):
        self._stop.set()
        self._t.join(timeout=1)
        self.stack.stop()
        self.notifier.stop()
