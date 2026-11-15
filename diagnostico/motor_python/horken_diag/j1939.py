"""Decodificación del protocolo SAE J1939 (CAN 29 bits, 250/500 kbit/s).

J1939 es el estándar que usan casi todos los motores diésel de maquinaria pesada
(Caterpillar, Cummins, Deutz, Volvo, Perkins, John Deere, Liebherr, ...) en el
conector de diagnóstico Deutsch de 9 pines.

Aquí se implementa:
  * Despiece del identificador de 29 bits (prioridad, PGN, origen, destino).
  * Reensamblado de mensajes multitrama (Transport Protocol BAM y RTS/CTS).
  * DM1 (averías activas) y DM2 (averías históricas) con lámparas, SPN, FMI y
    contador de ocurrencias.
  * Parámetros (SPN) de los PGN más importantes: horas, km, combustible total,
    revoluciones totales, temperaturas, presiones, tensión, etc.
  * Identificación de máquina, centralita y versión de software.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# --- PGN relevantes ---------------------------------------------------------
PGN_REQUEST = 0xEA00          # 59904  Petición de PGN
PGN_TP_CM = 0xEC00            # 60416  Transport Protocol - Connection Mgmt
PGN_TP_DT = 0xEB00            # 60160  Transport Protocol - Data Transfer
PGN_ADDRESS_CLAIM = 0xEE00    # 60928  Reclamación de dirección
PGN_DM1 = 0xFECA              # 65226  Averías activas
PGN_DM2 = 0xFECB              # 65227  Averías históricas (previamente activas)
PGN_DM3 = 0xFECC              # 65228  Borrar averías históricas
PGN_DM11 = 0xFED3             # 65235  Borrar averías activas
PGN_EEC1 = 0xF004             # 61444  Régimen motor, par
PGN_HOURS = 0xFEE5            # 65253  Horas motor, revoluciones totales
PGN_VD = 0xFEE0               # 65248  Distancia vehículo
PGN_VDHR = 0xFEC1             # 65217  Distancia alta resolución
PGN_LFC = 0xFEE9              # 65257  Combustible consumido total
PGN_LFE = 0xFEF2              # 65266  Consumo instantáneo
PGN_ET1 = 0xFEEE              # 65262  Temperaturas motor
PGN_EFLP1 = 0xFEEF            # 65263  Presión/nivel aceite
PGN_IC1 = 0xFEF6              # 65270  Admisión (turbo)
PGN_VEP1 = 0xFEF7             # 65271  Tensión batería
PGN_AMB = 0xFEF5              # 65269  Condiciones ambiente
PGN_DD = 0xFEFC               # 65276  Nivel combustible
PGN_TRF1 = 0xFEF8             # 65272  Transmisión: temperatura aceite
PGN_HYD = 0xFE68              # 65128  Fluidos: temperatura aceite hidráulico
PGN_AT1T1 = 0xFE56            # 65110  Nivel AdBlue/DEF
PGN_COMPONENT_ID = 0xFEEB     # 65259  Marca*Modelo*Nº serie*Unidad
PGN_SOFTWARE_ID = 0xFEDA      # 65242  Versión de software
PGN_ECU_ID = 0xFDC5           # 64965  Identificación de centralita
PGN_DM19 = 0xD300             # 54016  Calibraciones (Cal ID + CVN): huella del software

ON_REQUEST_PGNS = [
    PGN_COMPONENT_ID, PGN_SOFTWARE_ID, PGN_ECU_ID, PGN_HOURS,
    PGN_VD, PGN_VDHR, PGN_LFC, PGN_DM2, PGN_DM19,
]

# Direcciones de origen preferentes (SAE J1939 tabla B2). Los fabricantes
# usan además direcciones propias (128-247) para sus controladores.
SOURCE_ADDRESS_NAMES = {
    0x00: "Motor #1 (ECM)",
    0x01: "Motor #2",
    0x03: "Transmisión #1 (TCM)",
    0x0B: "Sistema de frenos",
    0x0F: "Retardador motor",
    0x10: "Retardador transmisión",
    0x17: "Cuadro de instrumentos",
    0x19: "Climatización",
    0x21: "Controlador de carrocería / cabina",
    0x27: "Ordenador de gestión #1",
    0x3D: "Postratamiento escape #1 (DPF/SCR)",
    0x3E: "Postratamiento escape #2",
    0xF9: "Herramienta diagnóstico #1",
    0xFA: "Herramienta diagnóstico #2",
}


def source_name(sa: int) -> str:
    if sa in SOURCE_ADDRESS_NAMES:
        return SOURCE_ADDRESS_NAMES[sa]
    if 0x80 <= sa <= 0xF7:
        return f"Controlador del fabricante 0x{sa:02X} (hidráulico/implementos)"
    return f"Centralita 0x{sa:02X}"


# --- Identificador ----------------------------------------------------------
@dataclass(frozen=True)
class J1939Id:
    priority: int
    pgn: int
    source: int
    destination: int  # 0xFF = global

    @classmethod
    def parse(cls, can_id: int) -> "J1939Id":
        priority = (can_id >> 26) & 0x7
        dp_edp = (can_id >> 24) & 0x3
        pf = (can_id >> 16) & 0xFF
        ps = (can_id >> 8) & 0xFF
        sa = can_id & 0xFF
        if pf < 240:  # PDU1: PS es la dirección de destino
            return cls(priority, (dp_edp << 16) | (pf << 8), sa, ps)
        return cls(priority, (dp_edp << 16) | (pf << 8) | ps, sa, 0xFF)

    def to_can_id(self) -> int:
        pf = (self.pgn >> 8) & 0xFF
        ps = self.destination if pf < 240 else self.pgn & 0xFF
        return ((self.priority & 7) << 26) | ((self.pgn >> 16 & 3) << 24) | (pf << 16) | (ps << 8) | self.source


def build_request(pgn: int, source: int = 0xF9, destination: int = 0xFF) -> tuple[int, bytes]:
    cid = J1939Id(6, PGN_REQUEST, source, destination).to_can_id()
    return cid, bytes([pgn & 0xFF, (pgn >> 8) & 0xFF, (pgn >> 16) & 0xFF])


# --- Transport Protocol -----------------------------------------------------
@dataclass
class _TpSession:
    pgn: int
    size: int
    packets: int
    data: dict = field(default_factory=dict)


class TransportReassembler:
    """Reensambla mensajes de más de 8 bytes (TP.CM BAM o RTS + TP.DT).

    Para RTS/CTS dirigido a nuestra herramienta, ``send`` (si se da) se usa
    para contestar con CTS y acuse de fin de mensaje.
    """

    def __init__(self, our_address: int = 0xF9, send: Optional[Callable[[int, bytes], None]] = None):
        self.our_address = our_address
        self.send = send
        self._sessions: dict[tuple[int, int], _TpSession] = {}

    def feed(self, jid: J1939Id, data: bytes) -> Optional[tuple[int, int, bytes]]:
        """Devuelve (pgn, origen, payload) cuando un mensaje se completa."""
        key = (jid.source, jid.destination)
        if jid.pgn == PGN_TP_CM and len(data) >= 8:
            ctrl = data[0]
            pgn = data[5] | (data[6] << 8) | (data[7] << 16)
            if ctrl in (0x20, 0x10):  # BAM o RTS
                size = data[1] | (data[2] << 8)
                self._sessions[key] = _TpSession(pgn, size, data[3])
                if ctrl == 0x10 and self.send and jid.destination == self.our_address:
                    cts = bytes([0x11, data[3], 1, 0xFF, 0xFF, data[5], data[6], data[7]])
                    self.send(J1939Id(7, PGN_TP_CM, self.our_address, jid.source).to_can_id(), cts)
            elif ctrl == 0xFF:  # abort
                self._sessions.pop(key, None)
            return None
        if jid.pgn == PGN_TP_DT and data:
            s = self._sessions.get(key)
            if not s:
                return None
            s.data[data[0]] = bytes(data[1:8])
            if len(s.data) >= s.packets:
                payload = b"".join(s.data[i] for i in sorted(s.data))[: s.size]
                del self._sessions[key]
                if self.send and jid.destination == self.our_address:
                    eom = bytes([0x13, s.size & 0xFF, s.size >> 8, s.packets, 0xFF,
                                 s.pgn & 0xFF, (s.pgn >> 8) & 0xFF, s.pgn >> 16])
                    self.send(J1939Id(7, PGN_TP_CM, self.our_address, jid.source).to_can_id(), eom)
                return s.pgn, jid.source, payload
        return None


def bam_frames(pgn: int, source: int, payload: bytes) -> list[tuple[int, bytes]]:
    """Genera las tramas BAM (lo usa el simulador y los tests)."""
    n = (len(payload) + 6) // 7
    cm = bytes([0x20, len(payload) & 0xFF, len(payload) >> 8, n, 0xFF,
                pgn & 0xFF, (pgn >> 8) & 0xFF, (pgn >> 16) & 0xFF])
    frames = [(J1939Id(7, PGN_TP_CM, source, 0xFF).to_can_id(), cm)]
    dt_id = J1939Id(7, PGN_TP_DT, source, 0xFF).to_can_id()
    for i in range(n):
        chunk = payload[i * 7:(i + 1) * 7].ljust(7, b"\xFF")
        frames.append((dt_id, bytes([i + 1]) + chunk))
    return frames


# --- DM1 / DM2 --------------------------------------------------------------
LAMP_STATES = {0: "apagada", 1: "encendida", 2: "error", 3: "no disponible"}


@dataclass
class Lamps:
    mil: int = 0          # Malfunction Indicator (emisiones)
    red_stop: int = 0     # Parada (rojo)
    amber_warning: int = 0
    protect: int = 0

    def as_dict(self) -> dict:
        return {"mil": self.mil == 1, "red_stop": self.red_stop == 1,
                "amber_warning": self.amber_warning == 1, "protect": self.protect == 1}


@dataclass
class Dtc:
    spn: int
    fmi: int
    occurrences: int
    source: int
    active: bool
    conversion_method: int = 0

    @property
    def code(self) -> str:
        return f"SPN {self.spn} FMI {self.fmi}"


def decode_dm(payload: bytes, source: int, active: bool) -> tuple[Lamps, list[Dtc]]:
    if len(payload) < 2:
        return Lamps(), []
    b0 = payload[0]
    lamps = Lamps(mil=(b0 >> 6) & 3, red_stop=(b0 >> 4) & 3, amber_warning=(b0 >> 2) & 3, protect=b0 & 3)
    dtcs = []
    for i in range(2, len(payload) - 3, 4):
        b = payload[i:i + 4]
        spn = b[0] | (b[1] << 8) | ((b[2] >> 5) << 16)
        fmi = b[2] & 0x1F
        cm = b[3] >> 7
        oc = b[3] & 0x7F
        if spn == 0 and fmi == 0:
            continue  # "sin averías"
        if spn == 0x7FFFF:
            continue  # no disponible
        dtcs.append(Dtc(spn, fmi, 0 if oc == 0x7F else oc, source, active, cm))
    return lamps, dtcs


def encode_dm(lamps: Lamps, dtcs: list[tuple[int, int, int]]) -> bytes:
    b0 = (lamps.mil << 6) | (lamps.red_stop << 4) | (lamps.amber_warning << 2) | lamps.protect
    out = bytearray([b0, 0xFF])
    if not dtcs:
        out += bytes([0, 0, 0, 0, 0xFF, 0xFF])
    for spn, fmi, oc in dtcs:
        out += bytes([spn & 0xFF, (spn >> 8) & 0xFF, ((spn >> 16) & 7) << 5 | (fmi & 0x1F), oc & 0x7F])
    return bytes(out)


# --- Parámetros -------------------------------------------------------------
def _u(data: bytes, start: int, length: int) -> Optional[int]:
    """Entero little-endian; None si el valor es 'no disponible' o 'error'."""
    if len(data) < start + length:
        return None
    v = int.from_bytes(data[start:start + length], "little")
    full = (1 << (8 * length)) - 1
    # Rangos reservados J1939: >= 0xFB.. (1 byte) / >= 0xFA00 (2) / >= 0xFAFFFFFF (4)
    limit = {1: 0xFA, 2: 0xFAFF, 4: 0xFAFFFFFF}.get(length, full)
    if v > limit:
        return None
    return v


def _scaled(data, start, length, res, offset=0.0):
    v = _u(data, start, length)
    return None if v is None else round(v * res + offset, 3)


# (nombre clave, descripción, unidad, función)
PGN_DECODERS: dict[int, list[tuple[str, str, str, Callable[[bytes], Optional[float]]]]] = {
    PGN_EEC1: [
        ("rpm", "Régimen motor", "rpm", lambda d: _scaled(d, 3, 2, 0.125)),
        ("torque_pct", "Par motor real", "%", lambda d: _scaled(d, 2, 1, 1, -125)),
    ],
    PGN_HOURS: [
        ("engine_hours", "Horas de motor", "h", lambda d: _scaled(d, 0, 4, 0.05)),
        ("total_revolutions", "Revoluciones totales", "rev", lambda d: _scaled(d, 4, 4, 1000)),
    ],
    PGN_VD: [
        ("trip_km", "Distancia viaje", "km", lambda d: _scaled(d, 0, 4, 0.125)),
        ("total_km", "Distancia total", "km", lambda d: _scaled(d, 4, 4, 0.125)),
    ],
    PGN_VDHR: [
        ("total_km_hr", "Distancia total (alta resolución)", "km", lambda d: _scaled(d, 0, 4, 0.005)),
    ],
    PGN_LFC: [
        ("trip_fuel_l", "Combustible viaje", "L", lambda d: _scaled(d, 0, 4, 0.5)),
        ("total_fuel_l", "Combustible total consumido", "L", lambda d: _scaled(d, 4, 4, 0.5)),
    ],
    PGN_LFE: [
        ("fuel_rate_lh", "Consumo instantáneo", "L/h", lambda d: _scaled(d, 0, 2, 0.05)),
    ],
    PGN_ET1: [
        ("coolant_c", "Temperatura refrigerante", "°C", lambda d: _scaled(d, 0, 1, 1, -40)),
        ("fuel_temp_c", "Temperatura combustible", "°C", lambda d: _scaled(d, 1, 1, 1, -40)),
        ("oil_temp_c", "Temperatura aceite motor", "°C", lambda d: _scaled(d, 2, 2, 0.03125, -273)),
    ],
    PGN_EFLP1: [
        ("oil_level_pct", "Nivel aceite motor", "%", lambda d: _scaled(d, 2, 1, 0.4)),
        ("oil_pressure_kpa", "Presión aceite motor", "kPa", lambda d: _scaled(d, 3, 1, 4)),
        ("coolant_level_pct", "Nivel refrigerante", "%", lambda d: _scaled(d, 7, 1, 0.4)),
    ],
    PGN_IC1: [
        ("boost_kpa", "Presión de sobrealimentación", "kPa", lambda d: _scaled(d, 1, 1, 2)),
        ("intake_temp_c", "Temperatura colector admisión", "°C", lambda d: _scaled(d, 2, 1, 1, -40)),
    ],
    PGN_VEP1: [
        ("battery_v", "Tensión batería", "V", lambda d: _scaled(d, 4, 2, 0.05)),
    ],
    PGN_AMB: [
        ("ambient_c", "Temperatura ambiente", "°C", lambda d: _scaled(d, 3, 2, 0.03125, -273)),
    ],
    PGN_DD: [
        ("fuel_level_pct", "Nivel combustible", "%", lambda d: _scaled(d, 1, 1, 0.4)),
    ],
    PGN_TRF1: [
        ("trans_oil_temp_c", "Temperatura aceite transmisión", "°C", lambda d: _scaled(d, 4, 2, 0.03125, -273)),
    ],
    PGN_HYD: [
        ("hyd_oil_temp_c", "Temperatura aceite hidráulico", "°C", lambda d: _scaled(d, 0, 1, 1, -40)),
    ],
    PGN_AT1T1: [
        ("def_level_pct", "Nivel AdBlue (DEF)", "%", lambda d: _scaled(d, 0, 1, 0.4)),
    ],
}

PARAM_INFO = {k: (desc, unit) for decs in PGN_DECODERS.values() for k, desc, unit, _ in decs}


def decode_params(pgn: int, data: bytes) -> dict[str, float]:
    out = {}
    for key, _desc, _unit, fn in PGN_DECODERS.get(pgn, []):
        v = fn(data)
        if v is not None:
            out[key] = v
    return out


def decode_ascii_fields(payload: bytes, with_count: bool = False) -> list[str]:
    raw = payload[1:] if with_count else payload
    text = raw.decode("ascii", errors="replace")
    parts = text.split("*")
    if parts and parts[-1].strip("\xff ") == "":
        parts = parts[:-1]
    return [p.strip() for p in parts]


def decode_component_id(payload: bytes) -> dict:
    f = decode_ascii_fields(payload) + ["", "", "", ""]
    return {"make": f[0], "model": f[1], "serial": f[2], "unit": f[3]}


def decode_software_id(payload: bytes) -> list[str]:
    return [s for s in decode_ascii_fields(payload, with_count=True) if s]


def decode_ecu_id(payload: bytes) -> dict:
    f = decode_ascii_fields(payload) + [""] * 5
    return {"part_number": f[0], "serial": f[1], "location": f[2], "type": f[3], "manufacturer": f[4]}


def decode_dm19(payload: bytes) -> list[dict]:
    """DM19: bloques de 20 bytes = CVN (4 bytes) + Calibration ID (16 ASCII).
    Si alguien reprograma la centralita, el CVN (checksum) cambia."""
    out = []
    for i in range(0, len(payload) - 19, 20):
        cvn = int.from_bytes(payload[i:i + 4], "little")
        cal = payload[i + 4:i + 20].decode("ascii", errors="replace").strip("\x00\xff ")
        out.append({"cal_id": cal, "cvn": f"{cvn:08X}"})
    return out


def encode_dm19(cals: list[tuple[str, int]]) -> bytes:
    return b"".join(cvn.to_bytes(4, "little") + cal.encode()[:16].ljust(16, b"\x00") for cal, cvn in cals)
