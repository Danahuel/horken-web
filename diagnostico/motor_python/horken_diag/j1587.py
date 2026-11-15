"""SAE J1708 / J1587: el protocolo anterior a J1939 (camiones y máquinas de
antes de ~2005: Volvo, Caterpillar, Cummins, Detroit, Allison...). Va por los
pines F y G del conector Deutsch de 6 o 9 pines y se lee con un lector RP1210
(protocolo "J1708").

Mensaje: MID (quién habla) + parámetros PID con sus datos. Los PID < 256
tienen el mismo número que el SPN de J1939 (PID 110 = SPN 110 temperatura de
refrigerante), así que se reutiliza la base de averías J1939.

NOTA: implementado según la norma; confirmar escalas con la primera máquina real.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from . import kb
from .j1939 import Dtc

log = logging.getLogger("horken.j1587")

MID_NAMES = {128: "Motor #1", 130: "Transmisión", 136: "Frenos (ABS) tractora", 137: "Frenos remolque",
             140: "Cuadro de instrumentos", 142: "Gestión de vehículo", 144: "Unidad de control del vehículo",
             175: "Motor #2", 179: "Grabador de datos", 172: "Herramienta de diagnóstico", 232: "Postratamiento"}

SID_NAMES = {**{i: f"Inyector cilindro {i}" for i in range(1, 17)},
             21: "Sensor de posición de motor", 22: "Sensor de régimen (sincronización)",
             151: "Sistema de diagnóstico", 230: "Interruptor de ralentí", 231: "Enlace de datos J1939",
             240: "Memoria de programa", 248: "Enlace de datos propietario", 250: "Enlace de datos J1708",
             251: "Alimentación eléctrica", 252: "Software / calibración", 253: "Memoria de calibración",
             254: "Centralita (fallo interno)"}

TOOL_MID = 172


def _f_to_c(f):
    return round((f - 32) * 5 / 9, 1)


# PID → (clave, función decodificadora). Escalas según SAE J1587.
PID_DECODERS = {
    84: ("speed_kmh", lambda d: round(d[0] * 0.805, 1)),
    92: ("load_pct", lambda d: d[0] * 0.5),
    96: ("fuel_level_pct", lambda d: d[0] * 0.5),
    100: ("oil_pressure_kpa", lambda d: round(d[0] * 0.6 * 6.895, 1)),
    102: ("boost_kpa", lambda d: round(d[0] * 0.125 * 6.895, 1)),
    105: ("intake_temp_c", lambda d: _f_to_c(d[0])),
    110: ("coolant_c", lambda d: _f_to_c(d[0])),
    111: ("coolant_level_pct", lambda d: d[0] * 0.5),
    168: ("battery_v", lambda d: round(int.from_bytes(d[:2], "little") * 0.05, 2)),
    175: ("oil_temp_c", lambda d: _f_to_c(int.from_bytes(d[:2], "little", signed=True) * 0.25)),
    177: ("trans_oil_temp_c", lambda d: _f_to_c(int.from_bytes(d[:2], "little", signed=True) * 0.25)),
    183: ("fuel_rate_lh", lambda d: round(int.from_bytes(d[:2], "little") * 4.34e-6 * 3.785 * 3600, 2)),
    190: ("rpm", lambda d: int.from_bytes(d[:2], "little") * 0.25),
    245: ("total_km", lambda d: round(int.from_bytes(d[:4], "little") * 0.161, 1)),
    247: ("engine_hours", lambda d: round(int.from_bytes(d[:4], "little") * 0.05, 2)),
    250: ("total_fuel_l", lambda d: round(int.from_bytes(d[:4], "little") * 0.473, 1)),
}


def split_pids(data: bytes) -> list[tuple[int, bytes]]:
    """Separa los PID de un mensaje J1587 (sin MID ni checksum)."""
    out, i, page = [], 0, 0
    while i < len(data):
        pid = data[i]
        i += 1
        if pid == 255:          # extensión a página 2
            page = 256
            continue
        if pid == 254:          # data link escape: resto propietario
            break
        if pid < 128:
            n = 1
        elif pid < 192:
            n = 2
        else:
            if i >= len(data):
                break
            n = data[i]
            i += 1
        out.append((pid + page, bytes(data[i:i + n])))
        i += n
        page = 0
    return out


def decode_dtcs(payload: bytes) -> list[dict]:
    """PID 194: tabla de códigos de avería del transmisor."""
    out, i = [], 0
    while i + 1 < len(payload):
        code, ch = payload[i], payload[i + 1]
        i += 2
        count = None
        if ch & 0x80:           # incluye contador de ocurrencias
            count = payload[i] if i < len(payload) else None
            i += 1
        out.append({"id": code + (256 if (ch & 0x10 and not ch & 0x20) else 0),
                    "is_sid": bool(ch & 0x20), "active": not (ch & 0x40),
                    "fmi": ch & 0x0F, "count": count or 1})
    return out


def enrich_j1587(mid: int, d: dict, labour_rate: float = kb.LABOUR_RATE_EUR_H) -> dict:
    src = f"J1587 MID {mid}"
    name_src = MID_NAMES.get(mid, f"MID {mid}")
    if not d["is_sid"]:
        # PID = SPN J1939 para < 512: se aprovecha toda la base de averías
        e = kb.enrich_dtc(Dtc(d["id"], d["fmi"], d["count"], 0, d["active"]), labour_rate=labour_rate)
        e["code"] = f"MID {mid} PID {d['id']} FMI {d['fmi']}"
    else:
        e = kb.enrich_dtc(Dtc(0x7FFFE, d["fmi"], d["count"], 0, d["active"]), labour_rate=labour_rate)
        sid_name = SID_NAMES.get(d["id"], f"Subsistema SID {d['id']}")
        if mid in (128, 175) and 1 <= d["id"] <= 16:
            inj = kb.enrich_dtc(Dtc(650 + d["id"], d["fmi"], d["count"], 0, d["active"]), labour_rate=labour_rate)
            e.update({k: inj[k] for k in ("system", "causes", "steps", "parts", "difficulty", "labour_hours",
                                          "cost_min_eur", "cost_max_eur", "known")})
        e.update({"code": f"MID {mid} SID {d['id']} FMI {d['fmi']}", "name": sid_name,
                  "known": e["known"] or d["id"] in SID_NAMES, "proprietary": d["id"] not in SID_NAMES})
        if e["system"] == "Desconocido":
            e["system"] = name_src
    e.update({"protocol": "J1587", "source": src, "source_name": name_src, "spn": None})
    return e


class J1587Reader:
    """Lee J1708 con un lector RP1210 en paralelo a J1939 y vuelca en el MachineState."""

    def __init__(self, api: str, device_id: int, state, dll=None):
        from .rp1210 import _load_dll
        import ctypes
        self.dll = dll or _load_dll(api)
        self.state = state
        self.client = self.dll.RP1210_ClientConnect(0, device_id, b"J1708", 0, 0, 0)
        if self.client > 127:
            raise OSError(f"El lector no abre J1708 (código {self.client})")
        self.dll.RP1210_SendCommand(3, self.client, b"", 0)  # todos los filtros abiertos
        self._buf = ctypes.create_string_buffer(512)
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self.dtcs: dict[int, dict] = {}

    def handle(self, mid: int, data: bytes) -> None:
        key = f"J1587 MID {mid}"
        values, info = {}, {}
        for pid, raw in split_pids(data):
            if pid in PID_DECODERS:
                k, fn = PID_DECODERS[pid]
                try:
                    values[k] = fn(raw)
                except Exception:  # noqa: BLE001
                    continue
            elif pid == 194:
                for d in decode_dtcs(raw):
                    self.dtcs.setdefault(mid, {})[(d["id"], d["is_sid"], d["fmi"])] = d
            elif pid == 234:
                info["software"] = [raw.decode("ascii", errors="replace").strip("*\x00 ")]
            elif pid == 243:
                f = raw.decode("ascii", errors="replace").split("*") + ["", "", ""]
                info["component"] = {"make": f[0], "model": f[1], "serial": f[2], "unit": ""}
        self.state.add_ecu(key, MID_NAMES.get(mid, f"MID {mid}"), "J1587", **info)
        if values:
            with self.state.lock:
                self.state.set_values(key, values)
        if mid in self.dtcs:
            self.state.set_dtcs(key, [enrich_j1587(mid, d, self.state.labour_rate) for d in self.dtcs[mid].values()])

    def request(self, mid: int, pid: int) -> None:
        msg = bytes([8, TOOL_MID, 0, pid, mid])  # prioridad 8, PID 0 = petición del parámetro "pid" al "mid"
        self.dll.RP1210_SendMessage(self.client, msg, len(msg), 0, 0)

    def request_all(self):
        for mid in (128, 130, 136, 140, 142):
            for pid in (194, 234, 243, 245, 247, 250):
                self.request(mid, pid)
                time.sleep(0.05)

    def _loop(self):
        while not self._stop.is_set():
            n = self.dll.RP1210_ReadMessage(self.client, self._buf, len(self._buf), 0)
            if n > 5:
                raw = self._buf.raw[:n]
                self.handle(raw[4], raw[5:])
            else:
                time.sleep(0.005)

    def start(self):
        self._t.start()
        self.request_all()

    def stop(self):
        self._stop.set()
        self._t.join(timeout=1)
        self.dll.RP1210_ClientDisconnect(self.client)
