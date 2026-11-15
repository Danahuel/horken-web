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
from .j1939 import J1939Id, Lamps


def _u(v, n):
    return int(round(v)).to_bytes(n, "little")


def _pad(b: bytes) -> bytes:
    return b.ljust(8, b"\xFF")


SCENARIOS = {
    "cat320": {
        "descripcion": "Caterpillar 320 (excavadora) con horas rebajadas en la ECU de motor y 6 averías activas",
        "machine_class": "excavadora_20t",
        "ecus": {
            0x00: {"component": "CAT*320*SIM0001234*FLOTA-07*", "software": ["SIM-ENG-5432109-00", "SIM-FLASH-2023"],
                   "ecu_id": "SIM-472-1234*SIMECU001*MOTOR*ECM*CATERPILLAR*",
                   "hours": 4213.4, "revs": 829_600_000, "fuel": 148_100,
                   "dm19": [("SIM-CAL-C7.1-A07", 0x5A3C91E2)],
                   "dm1": [(651, 5, 3), (100, 18, 2)], "lamps": Lamps(amber_warning=1),
                   "dm2": [(97, 15, 12), (168, 18, 4), (3719, 16, 7)]},
            0x3D: {"software": ["SIM-ATC-3311-02"], "dm1": [(4364, 18, 5), (3226, 2, 1)],
                   "lamps": Lamps(mil=1, amber_warning=1), "dm2": [(3364, 18, 2)]},
            0x17: {"component": "CAT*320*SIM0001234*FLOTA-07*", "software": ["SIM-MON-8812-01"],
                   "hours": 9876.2, "dm1": [], "dm2": []},
            0xE6: {"component": "CAT*320*SIM0001234*FLOTA-07*", "software": ["SIM-MCH-5590-04"],
                   "hours": 9874.9, "dm1": [(1638, 16, 2), (520210, 2, 1)], "lamps": Lamps(amber_warning=1),
                   "dm2": []},
        },
        "live": {"oil_pressure_kpa": 150, "coolant_c": 96, "hyd_oil_temp_c": 94},
    },
    "fuchs": {
        "descripcion": "Fuchs MHL (manipuladora) con motor Deutz por J1939 y controlador de máquina UDS",
        "machine_class": "manipuladora",
        "ecus": {
            0x00: {"component": "FUCHS*MHL350*SIM-MHL-03521*GRUA-2*", "software": ["SIM-DEUTZ-EMR5-4.03"],
                   "hours": 7340.5, "revs": 7340.5 * 60 * 1450, "fuel": 7340.5 * 19,
                   "dm19": [("SIM-DEUTZ-TCD6.1", 0x1F22A0B7)],
                   "dm1": [(3719, 16, 3)], "lamps": Lamps(amber_warning=1), "dm2": [(110, 16, 2)]},
            0x17: {"component": "FUCHS*MHL350*SIM-MHL-03521*GRUA-2*", "software": ["SIM-FUCHS-DSP-7.2"],
                   "hours": 7341.1, "dm1": [], "dm2": []},
        },
        "uds": [{"addr": 0x27, "dtcs": [(0x91A413, 0x09), (0xC07388, 0x08)],
                 "dids": {0xF190: "SIMFUCHSMHL350X21", 0xF188: "SIM-MHL-CTRL-3.11", 0xF197: "Control maquina"}}],
        "live": {"oil_pressure_kpa": 360, "coolant_c": 88, "hyd_oil_temp_c": 71},
    },
    "hamm": {
        "descripcion": "Rodillo Hamm sin manipulación, 1 avería leve de combustible",
        "machine_class": "rodillo",
        "ecus": {
            0x00: {"component": "HAMM*H13i*SIM-H13-00042*R-03*", "software": ["SIM-DEUTZ-EMR4-1.2"],
                   "hours": 3120.6, "revs": 3120.6 * 60 * 1550, "fuel": 3120.6 * 9.5,
                   "dm1": [(94, 18, 1)], "lamps": Lamps(amber_warning=1), "dm2": [(168, 17, 2)]},
            0x17: {"component": "HAMM*H13i*SIM-H13-00042*R-03*", "software": ["SIM-HAMM-DSP-3.4"],
                   "hours": 3120.4, "dm1": [], "dm2": []},
        },
        "live": {"oil_pressure_kpa": 380, "coolant_c": 84, "hyd_oil_temp_c": 62},
    },
    "arjes": {
        "descripcion": "Trituradora Arjes con centralita de motor procedente de otra máquina",
        "machine_class": "trituradora",
        "ecus": {
            0x00: {"component": "ARJES*VZ950*SIM-ARJ-OTRA-77*", "software": ["SIM-ENG-ARJ-7.1"],
                   "hours": 850.2, "revs": 850.2 * 60 * 1600, "fuel": 850.2 * 38,
                   "dm1": [(3251, 16, 4), (110, 16, 1)], "lamps": Lamps(amber_warning=1), "dm2": []},
            0x17: {"component": "ARJES*VZ950*SIM-ARJ-00911*", "software": ["SIM-ARJ-HMI-2.0"],
                   "hours": 6420.7, "dm1": [], "dm2": []},
        },
        "live": {"oil_pressure_kpa": 340, "coolant_c": 101, "hyd_oil_temp_c": 78},
    },
}


class SimulatedMachine:
    def __init__(self, bus: can.BusABC, scenario: str = "cat320"):
        self.bus = bus
        self.sc = SCENARIOS[scenario]
        self.name = scenario
        self._stop = threading.Event()
        self._t0 = time.time()
        self._threads = [threading.Thread(target=self._periodic, daemon=True),
                         threading.Thread(target=self._responder, daemon=True)]

    # --- envío ---------------------------------------------------------
    def _send(self, pgn, sa, data: bytes, prio=6, dest=0xFF):
        if len(data) <= 8:
            cid = J1939Id(prio, pgn, sa, dest).to_can_id()
            self.bus.send(can.Message(arbitration_id=cid, data=_pad(data), is_extended_id=True))
        else:
            for cid, d in j1939.bam_frames(pgn, sa, data):
                self.bus.send(can.Message(arbitration_id=cid, data=d, is_extended_id=True))
                time.sleep(0.01)  # J1939: 10-200 ms entre tramas BAM

    def _dm(self, sa, which):
        e = self.sc["ecus"][sa]
        lamps = e.get("lamps", Lamps()) if which == "dm1" else Lamps()
        return j1939.encode_dm(lamps, e.get(which, []))

    def _live(self, key, t):
        base = self.sc["live"]
        working = (math.sin(t / 6) + 1) / 2  # ciclo de trabajo simulado
        noise = random.uniform(-1, 1)
        if key == "rpm":
            return 850 + working * 950 + noise * 15
        if key == "coolant_c":
            return min(base["coolant_c"], 60 + t * 2) + noise * 0.5
        if key == "oil_pressure_kpa":
            return base["oil_pressure_kpa"] * (0.7 + 0.3 * working) + noise * 4
        if key == "hyd_oil_temp_c":
            return min(base["hyd_oil_temp_c"], 45 + t * 2) + noise * 0.4
        return 0

    def _periodic(self):
        tick = 0
        while not self._stop.is_set():
            t = time.time() - self._t0
            rpm = self._live("rpm", t)
            torque = 125 + 20 + 55 * ((rpm - 850) / 950)
            self._send(j1939.PGN_EEC1, 0x00, bytes([0xFF, 0xFF, int(torque)]) + _u(rpm / 0.125, 2) + b"\xFF\xFF\xFF", prio=3)
            if tick % 10 == 0:
                cool = self._live("coolant_c", t)
                self._send(j1939.PGN_ET1, 0x00, bytes([int(cool + 40), int(42 + 40)]) + _u((cool + 6 + 273) / 0.03125, 2))
                op = self._live("oil_pressure_kpa", t)
                self._send(j1939.PGN_EFLP1, 0x00, bytes([0xFF, 0xFF, int(92 / 0.4), int(op / 4), 0xFF, 0xFF, 0xFF, int(95 / 0.4)]))
                self._send(j1939.PGN_IC1, 0x00, bytes([0xFF, int((60 + 120 * (rpm - 850) / 950) / 2), int(48 + 40)]))
                self._send(j1939.PGN_VEP1, 0x00, b"\xFF\xFF\xFF\xFF" + _u((27.6 + random.uniform(-0.1, 0.1)) / 0.05, 2))
                self._send(j1939.PGN_LFE, 0x00, _u((6 + 16 * (rpm - 850) / 950) / 0.05, 2))
                self._send(j1939.PGN_DD, 0x17 if 0x17 in self.sc["ecus"] else 0x00, bytes([0xFF, int(max(5, 64 - t * 0.05) / 0.4)]))
                self._send(j1939.PGN_AMB, 0x00, b"\xFF\xFF\xFF" + _u((14.5 + 273) / 0.03125, 2))
                hyd_sa = 0xE6 if 0xE6 in self.sc["ecus"] else 0x00
                self._send(j1939.PGN_HYD, hyd_sa, bytes([int(self._live("hyd_oil_temp_c", t) + 40)]))
                if 0x3D in self.sc["ecus"]:
                    self._send(j1939.PGN_AT1T1, 0x3D, bytes([int(41 / 0.4)]))
                for sa in self.sc["ecus"]:
                    self._send(j1939.PGN_DM1, sa, self._dm(sa, "dm1"))
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
        elif pgn == j1939.PGN_DM19 and e.get("dm19"):
            self._send(pgn, sa, j1939.encode_dm19(e["dm19"]))
        elif pgn == j1939.PGN_DM2:
            self._send(pgn, sa, self._dm(sa, "dm2"))

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
