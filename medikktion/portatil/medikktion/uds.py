"""UDS (ISO 14229) sobre CAN/ISO-TP con udsoncan + can-isotp.

Lo usan las centralitas modernas de coches, furgonetas, camiones y muchas
máquinas recientes (además de J1939). Aquí:
  * Busca centralitas en direcciones típicas: 11 bits (0x7E0-0x7E7 → +8) y
    29 bits "normal fixed" (0x18DA<destino><origen>), que es lo habitual en
    redes J1939.
  * Lee averías (servicio 0x19 / 0x02) con su estado.
  * Lee identificación: VIN (F190), referencias y versiones (F187/F188/F189/F191/F18C/F197).
Solo servicios de LECTURA.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import can
import isotp
import udsoncan
from udsoncan.client import Client
from udsoncan.connections import PythonIsoTpConnection

from . import kb

log = logging.getLogger("medikktion.uds")

# Tipo de fallo (byte FTB, ISO 15031-6 / SAE J2012) → texto
FTB = {
    0x00: "Sin subtipo / fallo general", 0x01: "Fallo eléctrico general", 0x02: "Fallo de señal general",
    0x11: "Circuito en corto a masa", 0x12: "Circuito en corto a positivo", 0x13: "Circuito abierto",
    0x14: "Corto a masa o circuito abierto", 0x15: "Corto a positivo o circuito abierto",
    0x16: "Tensión del circuito por debajo del umbral", 0x17: "Tensión del circuito por encima del umbral",
    0x19: "Corriente por encima del umbral", 0x1C: "Tensión del circuito fuera de rango",
    0x1F: "Circuito intermitente", 0x21: "Amplitud de señal por debajo del mínimo",
    0x22: "Amplitud de señal por encima del máximo", 0x29: "Señal no válida", 0x2F: "Señal errática",
    0x31: "Sin señal", 0x36: "Frecuencia de señal demasiado baja", 0x37: "Frecuencia de señal demasiado alta",
    0x4B: "Temperatura excesiva", 0x54: "Falta calibración", 0x55: "No configurado",
    0x62: "Fallo de comparación de señal", 0x64: "Fallo de plausibilidad de señal", 0x71: "Actuador bloqueado",
    0x72: "Actuador bloqueado abierto", 0x73: "Actuador bloqueado cerrado", 0x77: "Posición no alcanzable",
    0x87: "Falta mensaje (comunicación)", 0x88: "Bus desactivado (bus off)", 0x92: "Rendimiento o actuación incorrecta",
    0x96: "Fallo interno del componente", 0x98: "Componente sobrecalentado",
}
ELECTRICAL_FTB = set(range(0x11, 0x20)) | {0x01, 0x21, 0x22, 0x31, 0x36, 0x37}

DIDS = {0xF190: "vin", 0xF187: "part_number", 0xF188: "ecu_software", 0xF189: "software_version",
        0xF191: "hardware_number", 0xF18C: "ecu_serial", 0xF197: "system_name", 0xF18A: "supplier"}

ADDRESS_NAMES_29 = {0x00: "Motor", 0x03: "Transmisión", 0x0B: "Frenos", 0x17: "Cuadro", 0x21: "Cabina",
                    0x3D: "Postratamiento", 0x10: "Retardador", 0x27: "Gestión"}
ADDRESS_NAMES_11 = {0x7E0: "Motor (OBD)", 0x7E1: "Transmisión (OBD)", 0x7E2: "Centralita 0x7E2", 0x7E3: "Centralita 0x7E3",
                    0x7E4: "Centralita 0x7E4", 0x7E5: "Centralita 0x7E5", 0x7E6: "Centralita 0x7E6", 0x7E7: "Centralita 0x7E7"}


class _TextCodec(udsoncan.DidCodec):
    def encode(self, *a):
        raise NotImplementedError

    def decode(self, payload: bytes):
        return payload.decode("ascii", errors="replace").strip("\x00\xff ")

    def __len__(self):
        raise udsoncan.DidCodec.ReadAllRemainingData


def format_dtc(dtc_id: int) -> str:
    """0x01234A → 'P0123-4A' (SAE J2012)."""
    b1, b2, ftb = (dtc_id >> 16) & 0xFF, (dtc_id >> 8) & 0xFF, dtc_id & 0xFF
    letter = "PCBU"[b1 >> 6]
    return f"{letter}{(b1 >> 4) & 3}{b1 & 0xF:X}{b2:02X}-{ftb:02X}"


def _description(code: str) -> tuple[str, bool]:
    base = code.split("-")[0]
    try:
        from obd.codes import DTC  # base de 2.000+ códigos SAE genéricos (python-OBD)
        if base in DTC:
            return DTC[base], True
    except ImportError:
        pass
    if base[1] in "13" or base[0] in "BCU" and base[1] == "1":
        return "Código específico del fabricante", False
    return "Código no catalogado", False


def enrich_uds(dtc_id: int, status: int, source_name: str, labour_rate: float = kb.LABOUR_RATE_EUR_H) -> dict:
    code = format_dtc(dtc_id)
    ftb = dtc_id & 0xFF
    desc, known = _description(code)
    active = bool(status & 0x01)
    confirmed = bool(status & 0x08)
    pending = bool(status & 0x04)
    mil = bool(status & 0x80)
    electrical = ftb in ELECTRICAL_FTB
    severity = 4 if (mil and active) else 3 if active else 2 if confirmed else 1
    if code[0] == "U":
        system = "Comunicación entre centralitas"
    else:
        system = {"P": "Motor / transmisión", "C": "Chasis", "B": "Carrocería / cabina"}[code[0]]
    steps = (kb.ELECTRICAL_STEPS.get({0x11: "4", 0x12: "3", 0x13: "5", 0x14: "5", 0x15: "5", 0x1F: "2"}.get(ftb, ""),
                                     kb.GENERIC_ELECTRICAL_STEPS) if electrical else
             ["Comprobar la descripción del código en la documentación del fabricante",
              "Revisar el componente indicado y su conexión",
              "Borrar el código y comprobar si vuelve a aparecer en una prueba de trabajo"])
    if code[0] == "U":
        steps = kb.spn_table()["639"]["condicion"]["pasos"]
    labour = 1.5 if electrical else 2.0
    return {
        "code": code, "spn": None, "fmi": None, "protocol": "UDS",
        "active": active, "occurrences": 1 if active or confirmed else 0, "mil": mil,
        "status_text": ", ".join(t for t, b in [("activa", active), ("pendiente", pending),
                                                 ("confirmada", confirmed), ("testigo", mil)] if b) or "almacenada",
        "source_name": source_name,
        "name": desc + ("" if known else f" ({code.split('-')[0]})"),
        "name_language": "en" if known else "es",
        "system": system, "fmi_text": FTB.get(ftb, f"Tipo de fallo 0x{ftb:02X}"),
        "fault_type": "electrico" if electrical else "condicion",
        "severity": severity, "critical": False, "warning": None,
        "causes": ["Fallo de circuito: cableado, conector o el propio componente"] if electrical else [],
        "steps": steps, "parts": [], "difficulty": 2 if electrical else 3, "labour_hours": labour,
        "cost_min_eur": round(labour * labour_rate * 0.7), "cost_max_eur": round(labour * labour_rate * 1.3),
        "known": known, "proprietary": not known, "brand_note": "",
    }


@dataclass
class UdsTarget:
    key: str
    name: str
    address: isotp.Address


def default_targets(tester: int = 0xF9) -> list[UdsTarget]:
    t = [UdsTarget(f"UDS 0x{tx:03X}", n, isotp.Address(isotp.AddressingMode.Normal_11bits, txid=tx, rxid=tx + 8))
         for tx, n in ADDRESS_NAMES_11.items()]
    t += [UdsTarget(f"UDS 29b 0x{ta:02X}", n,
                    isotp.Address(isotp.AddressingMode.NormalFixed_29bits, source_address=tester, target_address=ta))
          for ta, n in ADDRESS_NAMES_29.items()]
    return t


class UdsScanner:
    def __init__(self, bus: can.BusABC, notifier: can.Notifier, timeout: float = 0.4):
        self.bus, self.notifier, self.timeout = bus, notifier, timeout

    def _client(self, target: UdsTarget) -> Client:
        stack = isotp.NotifierBasedCanStack(self.bus, self.notifier, address=target.address, params={
            "tx_data_min_length": 8, "tx_padding": 0xCC, "blocking_send": False})
        cfg = dict(udsoncan.configs.default_client_config)
        cfg.update({"request_timeout": self.timeout * 3, "p2_timeout": self.timeout, "p2_star_timeout": 2,
                    "data_identifiers": {did: _TextCodec() for did in DIDS},
                    "exception_on_negative_response": True, "exception_on_unexpected_response": False})
        return Client(PythonIsoTpConnection(stack), config=cfg)

    def scan_target(self, target: UdsTarget) -> dict | None:
        try:
            with self._client(target) as client:
                try:
                    resp = client.get_dtc_by_status_mask(0xFF)
                except udsoncan.exceptions.TimeoutException:
                    return None  # nadie contesta en esa dirección
                except udsoncan.exceptions.NegativeResponseException:
                    resp = None   # existe pero no da averías con esta petición
                dtcs = [] if resp is None else [(d.id, d.status.get_byte_as_int()) for d in resp.service_data.dtcs]
                info = {}
                for did, key in DIDS.items():
                    try:
                        info[key] = client.read_data_by_identifier_first(did)
                    except Exception:  # noqa: BLE001  DID no soportado
                        continue
                return {"key": target.key, "name": target.name, "dtcs": dtcs, "info": info}
        except Exception as e:  # noqa: BLE001
            log.debug("UDS %s: %s", target.key, e)
            return None

    def scan(self, state, targets: list[UdsTarget] | None = None) -> int:
        """Escanea y vuelca el resultado en el MachineState. Devuelve nº de centralitas UDS."""
        found = 0
        for t in targets or default_targets():
            r = self.scan_target(t)
            if not r:
                continue
            found += 1
            info = r["info"]
            sw = [v for k, v in info.items() if k in ("ecu_software", "software_version", "part_number") and v]
            name = f"{t.name}" + (f" · {info['system_name']}" if info.get("system_name") else "")
            state.add_ecu(t.key, name, "UDS", software=sw, vin=info.get("vin"),
                          ecu_id={"part_number": info.get("part_number", ""), "serial": info.get("ecu_serial", ""),
                                  "manufacturer": info.get("supplier", "")})
            state.set_dtcs(t.key, [enrich_uds(i, s, name, state.labour_rate) for i, s in r["dtcs"]])
        return found
