"""Lectura del bus: agrupa todo lo que emiten las centralitas en un estado único."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import can

from . import analysis, j1939, kb

log = logging.getLogger("horken.collector")

COUNTER_KEYS = ("engine_hours", "total_revolutions", "total_fuel_l", "total_km", "total_km_hr")


class MachineState:
    def __init__(self, machine_class: str = "generica", history: list | None = None,
                 previous_software: dict | None = None, labour_rate: float = kb.LABOUR_RATE_EUR_H):
        self.machine_class = machine_class
        self.history = history or []
        self.previous_software = previous_software
        self.labour_rate = labour_rate
        self.ecus: dict[int, dict] = {}
        self.live: dict[str, dict] = {}
        self.dm1: dict[int, tuple] = {}
        self.dm2: dict[int, tuple] = {}
        self.frames = 0
        self.unknown_pgns: dict[int, int] = {}
        self.lock = threading.Lock()
        self.tp = j1939.TransportReassembler()

    def _ecu(self, sa: int) -> dict:
        return self.ecus.setdefault(sa, {"address": sa, "name": j1939.source_name(sa)})

    def process(self, can_id: int, data: bytes) -> None:
        jid = j1939.J1939Id.parse(can_id)
        with self.lock:
            self.frames += 1
            self._ecu(jid.source)["last_seen"] = time.time()
            if jid.pgn in (j1939.PGN_TP_CM, j1939.PGN_TP_DT):
                done = self.tp.feed(jid, data)
                if done:
                    self._handle(*done)
                return
            self._handle(jid.pgn, jid.source, bytes(data))

    def _handle(self, pgn: int, sa: int, data: bytes) -> None:
        ecu = self._ecu(sa)
        if pgn == j1939.PGN_DM1:
            self.dm1[sa] = j1939.decode_dm(data, sa, active=True)
        elif pgn == j1939.PGN_DM2:
            self.dm2[sa] = j1939.decode_dm(data, sa, active=False)
        elif pgn == j1939.PGN_COMPONENT_ID:
            ecu["component"] = j1939.decode_component_id(data)
        elif pgn == j1939.PGN_SOFTWARE_ID:
            ecu["software"] = j1939.decode_software_id(data)
        elif pgn == j1939.PGN_ECU_ID:
            ecu["ecu_id"] = j1939.decode_ecu_id(data)
        elif pgn in j1939.PGN_DECODERS:
            values = j1939.decode_params(pgn, data)
            now = time.time()
            for k, v in values.items():
                if k in COUNTER_KEYS:
                    ecu[k] = v
                if k in COUNTER_KEYS or k.startswith("trip_"):
                    continue  # contadores: van a la pestaña de horas, no a datos en vivo
                desc, unit = j1939.PARAM_INFO[k]
                # El motor (0x00) manda sobre los demás para datos en vivo
                prev = self.live.get(k)
                if prev is None or sa == 0 or prev["source"] == sa:
                    self.live[k] = {"value": v, "unit": unit, "label": desc, "source": sa, "t": now}
        elif pgn not in (j1939.PGN_REQUEST, j1939.PGN_ADDRESS_CLAIM):
            self.unknown_pgns[pgn] = self.unknown_pgns.get(pgn, 0) + 1

    # -------------------------------------------------------------------
    def machine_info(self) -> dict:
        comp = next((e["component"] for sa, e in sorted(self.ecus.items()) if e.get("component")), {})
        brand = kb.detect_brand(comp.get("make"))
        b = kb.brands()[brand]
        return {**{"make": "", "model": "", "serial": "", "unit": ""}, **comp,
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
                        dtcs.append(kb.enrich_dtc(d, info["brand_key"], self.labour_rate,
                                                  ld if d.active else None))
            dtcs.sort(key=lambda d: (not d["active"], -d["severity"], d["spn"]))
            ecus = {sa: dict(e) for sa, e in self.ecus.items() if sa not in (0xF9, 0xFA)}
            tamper = analysis.analyze_counters(ecus, self.machine_class, self.history)
            mods = analysis.analyze_modifications(ecus, self.previous_software)
            active = [d for d in dtcs if d["active"]]
            ecu_list = []
            for sa, e in sorted(ecus.items()):
                ecu_list.append({
                    "address": sa, "address_hex": f"0x{sa:02X}", "name": e["name"],
                    "software": e.get("software", []), "ecu_id": e.get("ecu_id"),
                    "component": e.get("component"),
                    **{k: e.get(k) for k in COUNTER_KEYS},
                    "active_dtcs": sum(1 for d in active if d["source"] == sa),
                    "history_dtcs": sum(1 for d in dtcs if not d["active"] and d["source"] == sa),
                })
            return {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "machine": info,
                "lamps": lamps_all,
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


class DiagnosticSession:
    """Escucha el bus, pide los datos que solo se envían bajo petición y publica."""

    def __init__(self, bus: can.BusABC, state: MachineState, tool_address: int = 0xF9):
        self.bus, self.state, self.addr = bus, state, tool_address
        self._stop = threading.Event()
        self.state.tp.send = self._send
        self.state.tp.our_address = tool_address
        self._rx = threading.Thread(target=self._rx_loop, daemon=True)

    def _send(self, can_id: int, data: bytes) -> None:
        try:
            self.bus.send(can.Message(arbitration_id=can_id, data=data, is_extended_id=True))
        except can.CanError as e:
            log.warning("Error enviando trama: %s", e)

    def _rx_loop(self):
        while not self._stop.is_set():
            msg = self.bus.recv(0.2)
            if msg is not None and msg.is_extended_id:
                self.state.process(msg.arbitration_id, bytes(msg.data))

    def start(self):
        self._rx.start()

    def request_all(self, pause: float = 0.05):
        """Pide a todas las centralitas los PGN que no emiten solas."""
        for pgn in j1939.ON_REQUEST_PGNS:
            self._send(*j1939.build_request(pgn, self.addr, 0xFF))
            time.sleep(pause)
        # Algunas centralitas solo responden a peticiones dirigidas
        for sa in list(self.state.ecus):
            if sa in (self.addr,):
                continue
            for pgn in (j1939.PGN_HOURS, j1939.PGN_SOFTWARE_ID, j1939.PGN_COMPONENT_ID):
                self._send(*j1939.build_request(pgn, self.addr, sa))
                time.sleep(pause)

    def clear_active_codes(self):
        """DM11: borra averías activas (solo si el usuario lo pide desde la app)."""
        self._send(*j1939.build_request(j1939.PGN_DM11, self.addr, 0xFF))

    def stop(self):
        self._stop.set()
        self._rx.join(timeout=1)
