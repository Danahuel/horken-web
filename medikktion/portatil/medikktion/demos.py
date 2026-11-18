"""Genera las 4 sesiones de demostración de la app (python -m medikktion generar-demos).

Cada una pasa por el mismo camino que una máquina real (bus CAN simulado →
lectura J1939/UDS → análisis) y después se simulan varios minutos de trabajo
con el modelo físico para tener historial de mediciones.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import can

from . import collector, j1939, simulator
from .fisica import Motor
from .pricing import Pricing

DEMOS = {
    # escenario: (ubicación, minutos trabajados, en directo, motivo)
    "cat320": ("Múnich · Obra Messestadt Riem", 18, True, "Revisión de compra"),
    "fuchs": ("Hamburgo · Terminal de chatarra Waltershof", 22, True, "Mantenimiento preventivo"),
    "arjes": ("Valencia · Planta de reciclaje de madera", 14, False, "Avería en planta"),
    "hamm": ("Stuttgart · Autobahn A8, tramo 4", 25, False, "Control de flota"),
}
# País (tarifa), km de desplazamiento, precio que piden y lecturas anteriores de la misma máquina
EXTRA = {
    "cat320": {"pais": "DE", "km": 35, "precio": 68000,
               "historia": [{"date": "2025-04-11", "engine_hours": 9412.0, "active": 2, "health": 71, "location": "Augsburgo"}]},
    "fuchs": {"pais": "DE", "km": 20, "precio": None,
              "historia": [{"date": "2025-05-20", "engine_hours": 6410.2, "active": 1, "health": 88, "location": "Hamburgo"},
                           {"date": "2025-11-03", "engine_hours": 6893.7, "active": 0, "health": 96, "location": "Hamburgo"}],
              "ordenes": [{"code": "SPN 110 FMI 16", "name": "Temperatura del refrigerante motor", "cost_eur": 640,
                           "labour_hours": 3.5, "parts": "Termostato + refrigerante", "notes": "Radiador limpiado",
                           "by": "mecánico", "at": "2025-11-04T09:12:00Z"}]},
    "arjes": {"pais": "ES", "km": 15, "precio": 210000, "historia": []},
    "hamm": {"pais": "DE", "km": 60, "precio": None,
             "historia": [{"date": "2025-03-14", "engine_hours": 2604.5, "active": 0, "health": 98, "location": "Stuttgart"},
                          {"date": "2025-09-29", "engine_hours": 2880.0, "active": 1, "health": 92, "location": "Ulm"}]},
}
TREND_EVERY = 5.0


def _structure(scenario: str, seconds: float = 4.0) -> dict:
    ch = f"demo-{scenario}"
    mbus, tbus = can.Bus(interface="virtual", channel=ch), can.Bus(interface="virtual", channel=ch)
    sc = simulator.SCENARIOS[scenario]
    sim = simulator.SimulatedMachine(mbus, scenario)
    uds_ecus = []
    for u in sc.get("uds", []):
        ub = can.Bus(interface="virtual", channel=ch)
        e = simulator.SimulatedUdsEcu(ub, u["addr"], u["dtcs"], u["dids"])
        e.start()
        uds_ecus.append((e, ub))
    ex = EXTRA.get(scenario, {})
    st = collector.MachineState(sc["machine_class"],
                                labour_rate=Pricing.from_config({"pais": ex.get("pais", "ES")}, sc["machine_class"], ex.get("km", 0)))
    st.plate = dict(sc.get("placa") or {})
    st.asking_price = ex.get("precio")
    st.history = list(ex.get("historia", []))
    sess = collector.DiagnosticSession(tbus, st)
    sim.start()
    sess.start()
    try:
        time.sleep(1.3)
        sess.request_all()
        if uds_ecus:
            from .uds import UdsScanner, default_targets
            UdsScanner(tbus, sess.notifier, timeout=0.3).scan(
                st, [t for t in default_targets() if t.key.startswith("UDS 29b")])
        time.sleep(seconds)
        return st.snapshot()
    finally:
        sess.stop()
        sim.stop()
        for e, ub in uds_ecus:
            e.stop()
            ub.shutdown()
        mbus.shutdown()
        tbus.shutdown()


def build(scenario: str) -> dict:
    location, minutes, live, purpose = DEMOS[scenario]
    snap = _structure(scenario)
    motor = Motor(simulator.SCENARIOS[scenario]["perfil"])
    now = datetime.now(timezone.utc)
    t0 = now.timestamp() - minutes * 60
    trend: dict[str, dict] = {}
    values = {}
    steps = int(minutes * 60 / 0.5)
    for i in range(steps):
        values = motor.step(0.5)
        if i % int(TREND_EVERY / 0.5) == 0:
            for k in collector.MachineState.TREND_KEYS:
                if k in values:
                    desc, unit = j1939.PARAM_INFO[k]
                    tr = trend.setdefault(k, {"label": desc, "unit": unit, "t": [], "v": []})
                    tr["t"].append(round(t0 + i * 0.5, 1))
                    tr["v"].append(values[k])
    for tr in trend.values():
        tr["t"], tr["v"] = tr["t"][-180:], tr["v"][-180:]
    snap["live"] = {k: {"value": v, "unit": j1939.PARAM_INFO[k][1], "label": j1939.PARAM_INFO[k][0], "source": 0}
                    for k, v in values.items() if k in j1939.PARAM_INFO}
    snap["trend"] = trend
    started = now - timedelta(minutes=minutes)
    snap.update({
        "session_id": started.strftime("%Y%m%d-%H%M%S-") + scenario[:4],
        "status": "live" if live else "finished", "simulated": True,
        "operator": "Demostración", "location": location, "purpose": purpose,
        "started_at": started.isoformat(), "duration_min": minutes,
        "recipients": [], "updated_at": now.isoformat(),
        "asking_price": EXTRA.get(scenario, {}).get("precio"),
    })
    if EXTRA.get(scenario, {}).get("ordenes"):
        snap["work_orders"] = EXTRA[scenario]["ordenes"]
        snap["has_work_orders"] = True
    return snap


def generate(out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in DEMOS:
        snap = build(name)
        p = out / f"{name}.json"
        p.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        paths.append(p)
        h = snap["health"]
        print(f"{name:8s} {snap['machine']['brand_name']} {snap['machine']['model']}: "
              f"{snap['summary']['active_dtcs']} activas, salud {h['score']} ({h['label']}), "
              f"{snap['tamper']['label']}, {len(snap['trend'].get('rpm', {}).get('v', []))} muestras")
    return paths
