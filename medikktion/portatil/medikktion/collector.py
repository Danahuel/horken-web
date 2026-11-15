"""Lectura del bus: agrupa en un estado único todo lo que emiten las centralitas,
venga del protocolo que venga (J1939, UDS, J1587, OBD-II)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import can

from . import analysis, j1939, kb

log = logging.getLogger("medikktion.collector")

COUNTER_KEYS = ("engine_hours", "total_revolutions", "total_fuel_l", "total_km", "total_km_hr")


class MachineState:
    def __init__(self, machine_class: str = "generica", history: list | None = None,
                 previous_software: dict | None = None, labour_rate: float = kb.LABOUR_RATE_EUR_H,
                 dbc=None):
        self.machine_class = machine_class
        self.history = history or []
        self.previous_software = previous_software
        self.labour_rate = labour_rate
        self.ecus: dict = {}            # clave: dirección J1939 (int) o texto ("UDS 0x7E0", "J1587 MID 128")
        self.live: dict[str, dict] = {}
        self.dm1: dict[int, tuple] = {}
        self.dm2: dict[int, tuple] = {}
        self.extra_dtcs: dict[str, list[dict]] = {}   # DTC ya enriquecidos de otros protocolos
        self.protocols: set[str] = set()
        self.notes: list[str] = []
        self.extra_evidence: list[dict] = []
        self.trend: dict[str, dict] = {}
        self._last_trend = 0.0
        self.frames = 0
        self.unknown_pgns: dict[int, int] = {}
        self.lock = threading.Lock()
        self.tp = j1939.TransportReassembler()
        self.dbc = dbc                  # DBC opcional (cantools) para mensajes del fabricante

    def _ecu(self, sa) -> dict:
        return self.ecus.setdefault(sa, {"address": sa, "name": j1939.source_name(sa) if isinstance(sa, int) else str(sa),
                                         "protocol": "J1939"})

    # ---------------------------------------------------------------- J1939
    def process(self, can_id: int, data: bytes) -> None:
        jid = j1939.J1939Id.parse(can_id)
        with self.lock:
            self.frames += 1
            if jid.pgn in (0xDA00, 0xDB00):   # ISO-TP de UDS sobre 29 bits: lo gestiona uds.py
                return
            self.protocols.add("J1939")
            self._ecu(jid.source)["last_seen"] = time.time()
            if jid.pgn in (j1939.PGN_TP_CM, j1939.PGN_TP_DT):
                done = self.tp.feed(jid, data)
                if done:
                    self._handle(*done)
                return
            self._handle(jid.pgn, jid.source, bytes(data), can_id)

    def _handle(self, pgn: int, sa: int, data: bytes, can_id: int | None = None) -> None:
        ecu = self._ecu(sa)
        if pgn == j1939.PGN_DM1:
            self.dm1[sa] = j1939.decode_dm(data, sa, active=True)
        elif pgn == j1939.PGN_DM2:
            self.dm2[sa] = j1939.decode_dm(data, sa, active=False)
        elif pgn == j1939.PGN_DM19:
            ecu["calibrations"] = j1939.decode_dm19(data)
        elif pgn == j1939.PGN_COMPONENT_ID:
            ecu["component"] = j1939.decode_component_id(data)
        elif pgn == j1939.PGN_SOFTWARE_ID:
            ecu["software"] = j1939.decode_software_id(data)
        elif pgn == j1939.PGN_ECU_ID:
            ecu["ecu_id"] = j1939.decode_ecu_id(data)
        elif pgn in j1939.PGN_DECODERS:
            self.set_values(sa, j1939.decode_params(pgn, data))
        elif pgn not in (j1939.PGN_REQUEST, j1939.PGN_ADDRESS_CLAIM):
            if not self._try_dbc(pgn, sa, data):
                self.unknown_pgns[pgn] = self.unknown_pgns.get(pgn, 0) + 1

    def _try_dbc(self, pgn: int, sa: int, data: bytes) -> bool:
        if not self.dbc:
            return False
        try:
            name, values = self.dbc.decode(pgn, data)
        except Exception:  # noqa: BLE001
            return False
        if name is None:
            return False
        now = time.time()
        for sig, (v, unit) in values.items():
            if isinstance(v, (int, float)):
                self.live[f"dbc.{sig}"] = {"value": round(float(v), 3), "unit": unit or "", "label": sig,
                                           "source": sa, "t": now}
        return True

    def set_values(self, source, values: dict[str, float]) -> None:
        """Contadores y datos en vivo (lo usan todos los protocolos)."""
        ecu = self._ecu(source)
        now = time.time()
        for k, v in values.items():
            if k in COUNTER_KEYS:
                ecu[k] = v
            if k in COUNTER_KEYS or k.startswith("trip_") or k not in j1939.PARAM_INFO:
                continue
            desc, unit = j1939.PARAM_INFO[k]
            prev = self.live.get(k)
            # El motor J1939 (0x00) manda sobre los demás para datos en vivo
            if prev is None or source == 0 or prev["source"] == source or (prev["source"] != 0 and now - prev["t"] > 3):
                self.live[k] = {"value": v, "unit": unit, "label": desc, "source": source, "t": now}

    # ---------------------------------------------------------- otros protocolos
    def add_ecu(self, key: str, name: str, protocol: str, **info) -> dict:
        with self.lock:
            self.protocols.add(protocol)
            e = self.ecus.setdefault(key, {"address": key, "name": name, "protocol": protocol})
            e.update({k: v for k, v in info.items() if v not in (None, [], {})})
            return e

    def set_dtcs(self, key: str, dtcs: list[dict]) -> None:
        with self.lock:
            self.extra_dtcs[key] = dtcs

    TREND_KEYS = ("rpm", "coolant_c", "hyd_oil_temp_c", "oil_temp_c", "oil_pressure_kpa", "boost_kpa",
                  "fuel_rate_lh", "battery_v", "trans_oil_temp_c")

    def record_trend(self, every: float = 5.0, keep: int = 180) -> None:
        """Guarda una muestra cada ``every`` s (15 min con los valores por defecto)."""
        now = time.time()
        if now - self._last_trend < every:
            return
        self._last_trend = now
        with self.lock:
            for k in self.TREND_KEYS:
                p = self.live.get(k)
                if not p:
                    continue
                tr = self.trend.setdefault(k, {"label": p["label"], "unit": p["unit"], "t": [], "v": []})
                tr["t"].append(round(now, 1))
                tr["v"].append(p["value"])
                del tr["t"][:-keep], tr["v"][:-keep]

    # -------------------------------------------------------------------
    def machine_info(self) -> dict:
        comp = next((e["component"] for _, e in sorted(self.ecus.items(), key=lambda x: str(x[0]))
                     if e.get("component") and e["component"].get("make")), {})
        vin = next((e.get("vin") for e in self.ecus.values() if e.get("vin")), "")
        brand = kb.detect_brand(comp.get("make"))
        b = kb.brands()[brand]
        info = {"make": "", "model": "", "serial": "", "unit": ""}
        info.update(comp)
        if not info.get("serial") and vin:
            info["serial"] = vin
        return {**info, "vin": vin,
                "brand_key": brand, "brand_name": b["nombre"], "connector": b["conector"],
                "official_software": b["software_oficial"], "brand_note": b["notas"],
                "machine_class": self.machine_class,
                "machine_class_label": analysis.MACHINE_CLASSES.get(self.machine_class, analysis.MACHINE_CLASSES["generica"])[0]}

    def snapshot(self) -> dict:
        with self.lock:
            info = self.machine_info()
            dtcs = []
            lamps_all = {"mil": False, "red_stop": False, "amber_warning": False, "protect": False}
            for table in (self.dm1, self.dm2):
                for sa, (lamps, codes) in table.items():
                    ld = lamps.as_dict()
                    if table is self.dm1:
                        lamps_all = {k: lamps_all[k] or ld[k] for k in lamps_all}
                    for d in codes:
                        e = kb.enrich_dtc(d, info["brand_key"], self.labour_rate, ld if d.active else None)
                        e["protocol"] = "J1939"
                        dtcs.append(e)
            for key, codes in self.extra_dtcs.items():
                for d in codes:
                    dtcs.append({**d, "source": str(key)})
                    if d.get("active") and d.get("mil"):
                        lamps_all["mil"] = True
            dtcs.sort(key=lambda d: (not d["active"], -d["severity"], str(d["code"])))
            ecus = {sa: dict(e) for sa, e in self.ecus.items() if sa not in (0xF9, 0xFA)}
            tamper = analysis.analyze_counters(ecus, self.machine_class, self.history, self.extra_evidence)
            mods = analysis.analyze_modifications(ecus, self.previous_software)
            active = [d for d in dtcs if d["active"]]
            ecu_list = []
            for sa, e in sorted(ecus.items(), key=lambda x: (not isinstance(x[0], int), str(x[0]) if not isinstance(x[0], int) else f"{x[0]:03d}")):
                ecu_list.append({
                    "address": sa if isinstance(sa, int) else str(sa),
                    "address_hex": f"0x{sa:02X}" if isinstance(sa, int) else str(sa),
                    "name": e["name"], "protocol": e.get("protocol", "J1939"),
                    "software": e.get("software", []), "ecu_id": e.get("ecu_id"),
                    "component": e.get("component"), "calibrations": e.get("calibrations", []),
                    "vin": e.get("vin"),
                    **{k: e.get(k) for k in COUNTER_KEYS},
                    "active_dtcs": sum(1 for d in active if str(d["source"]) == str(sa)),
                    "history_dtcs": sum(1 for d in dtcs if not d["active"] and str(d["source"]) == str(sa)),
                })
            health = analysis.health_index(active, tamper, mods)
            return {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "health": health,
                "trend": {k: {**v, "t": list(v["t"]), "v": list(v["v"])} for k, v in self.trend.items()},
                "machine": info,
                "lamps": lamps_all,
                "protocols": sorted(self.protocols),
                "notes": list(self.notes),
                "summary": {
                    "active_dtcs": len(active), "history_dtcs": len(dtcs) - len(active),
                    "max_severity": max([d["severity"] for d in active], default=0),
                    "ecus": len(ecu_list), "frames": self.frames,
                    "repair_cost_min_eur": sum(d["cost_min_eur"] for d in active),
                    "repair_cost_max_eur": sum(d["cost_max_eur"] for d in active),
                },
                "dtcs": dtcs, "ecus": ecu_list,
                "live": {k: {kk: vv for kk, vv in v.items() if kk != "t"} for k, v in self.live.items()},
                "tamper": tamper, "modifications": mods,
                "unknown_pgns": [{"pgn": p, "count": c} for p, c in sorted(self.unknown_pgns.items())][:50],
            }


class _Feed(can.Listener):
    def __init__(self, state: MachineState):
        self.state = state

    def on_message_received(self, msg: can.Message) -> None:
        if msg.is_extended_id and not msg.is_error_frame:
            self.state.process(msg.arbitration_id, bytes(msg.data))

    def on_error(self, exc: Exception) -> None:
        log.warning("Error en el bus: %s", exc)


class DiagnosticSession:
    """Escucha el bus, pide los datos que solo se envían bajo petición y publica.

    Usa un ``can.Notifier`` para que otros protocolos (UDS sobre ISO-TP) puedan
    compartir el mismo adaptador a la vez.
    """

    def __init__(self, bus: can.BusABC, state: MachineState, tool_address: int = 0xF9):
        self.bus, self.state, self.addr = bus, state, tool_address
        self.state.tp.send = self._send
        self.state.tp.our_address = tool_address
        self.notifier: can.Notifier | None = None

    def _send(self, can_id: int, data: bytes) -> None:
        try:
            self.bus.send(can.Message(arbitration_id=can_id, data=data, is_extended_id=True))
        except can.CanError as e:
            log.warning("Error enviando trama: %s", e)

    def start(self):
        self.notifier = can.Notifier(self.bus, [_Feed(self.state)], timeout=0.2)

    def request_all(self, pause: float = 0.05):
        """Pide a todas las centralitas los PGN que no emiten solas."""
        for pgn in j1939.ON_REQUEST_PGNS:
            self._send(*j1939.build_request(pgn, self.addr, 0xFF))
            time.sleep(pause)
        # Algunas centralitas solo responden a peticiones dirigidas
        for sa in [s for s in list(self.state.ecus) if isinstance(s, int) and s != self.addr]:
            for pgn in (j1939.PGN_HOURS, j1939.PGN_SOFTWARE_ID, j1939.PGN_COMPONENT_ID, j1939.PGN_DM19):
                self._send(*j1939.build_request(pgn, self.addr, sa))
                time.sleep(pause)

    def clear_active_codes(self):
        """DM11: borra averías activas (solo si el usuario lo pide desde la app)."""
        self._send(*j1939.build_request(j1939.PGN_DM11, self.addr, 0xFF))

    def stop(self):
        if self.notifier:
            self.notifier.stop()
