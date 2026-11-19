"""Prueba de bombas hidráulicas, guiada paso a paso.

Las presiones llegan por dos caminos:

* **Centralita** (automático): cuando la máquina emite las presiones de bomba en
  sus mensajes propios y tenemos el perfil de esa máquina (``kb/presiones``).
  Los perfiles se sacan de grabaciones con ``python -m medikktion buscar-presiones``.
* **Manómetro** (manual): el mecánico pincha un manómetro de taller (0-600 bar)
  en la toma de prueba de cada bomba y escribe lo que marca la aguja.

La prueba compara cada lectura con el valor del manual (o, si no se indica, con
un valor orientativo de la clase de máquina) y da un veredicto por bomba con su
causa probable, pasos y coste.

Honestidad: la presión dice si la bomba y las válvulas de alivio AGUANTAN.
Una bomba puede llegar a presión y aun así dar poco caudal (máquina lenta);
eso se ve con los tiempos de ciclo o con un caudalímetro.
"""
from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

PRESION_DIR = Path(__file__).parent / "kb" / "presiones"

CHANNELS = {
    "pump1_bar": "Bomba 1",
    "pump2_bar": "Bomba 2",
    "pilot_bar": "Pilotaje",
}

SEGURIDAD = [
    "Zona despejada, nadie cerca del equipo ni de los latiguillos.",
    "Implemento apoyado en el suelo antes de pinchar o quitar el manómetro.",
    "Manómetro de 0-600 bar con su latiguillo de prueba en la toma rápida (tipo Minimess).",
    "Aceite hidráulico caliente (más de 45 °C): en frío las presiones salen falseadas.",
    "Mantener cada mando a tope solo 3-5 s: más tiempo calienta el aceite y castiga la bomba.",
]

# Valores ORIENTATIVOS por clase. Cada máquina tiene los suyos en el manual de servicio:
# conviene escribir el valor exacto al empezar la prueba.
SPECS = {
    "excavadora_20t": {"alivio": 343, "reposo": (20, 45), "pilotaje": 40,
                       "nota": "Excavadora 20 t típica: alivio principal ≈ 34,3 MPa, pilotaje ≈ 4 MPa"},
    "excavadora_grande": {"alivio": 343, "reposo": (20, 45), "pilotaje": 40,
                          "nota": "Excavadora grande típica: alivio principal ≈ 34-35 MPa"},
    "manipuladora": {"alivio": 350, "reposo": (15, 40), "pilotaje": 35,
                     "nota": "Manipuladora de material: alivio de trabajo ≈ 350 bar"},
    "retro_mixta": {"alivio": 230, "reposo": (10, 30), "pilotaje": 30,
                    "nota": "Retrocargadora: alivio principal ≈ 200-250 bar"},
    "cargadora_ruedas": {"alivio": 250, "reposo": (10, 35), "pilotaje": 35,
                         "nota": "Cargadora de ruedas: alivio de trabajo ≈ 220-280 bar"},
    "minicargadora": {"alivio": 210, "reposo": (10, 30), "pilotaje": 30, "nota": "Minicargadora: ≈ 200-230 bar"},
    "trituradora": {"alivio": 350, "reposo": (15, 45), "pilotaje": 35,
                    "nota": "Trituradora con accionamiento hidráulico: alivio ≈ 300-380 bar"},
    "rodillo": {"alivio": 420, "reposo": (20, 30), "pilotaje": 25,
                "nota": "Rodillo (traslación hidrostática): alta presión ≈ 400-450 bar; 'pilotaje' = presión de carga"},
}
GENERIC_SPEC = {"alivio": 300, "reposo": (10, 45), "pilotaje": 35,
                "nota": "Sin clase de máquina: valores genéricos, escriba los del manual"}


def steps_for(machine_class: str, alivio: float | None = None, pilotaje: float | None = None) -> list[dict]:
    sp = SPECS.get(machine_class, GENERIC_SPEC)
    a = float(alivio or sp["alivio"])
    pi = float(pilotaje or sp["pilotaje"])
    lo, hi = sp["reposo"]
    excav = machine_class in ("excavadora_20t", "excavadora_grande", "manipuladora", "retro_mixta")
    if machine_class == "rodillo":
        return [
            {"id": "reposo", "title": "Presión de carga en reposo", "action": "reposo", "kind": "reposo",
             "instruction": "Motor a régimen de trabajo, palanca de avance en punto muerto. Esperar 10 s.",
             "channels": ["pump1_bar", "pump2_bar"], "range": [lo, hi]},
            {"id": "alivio_p1", "title": "Traslación bloqueada (adelante)", "action": "alivio_p1", "kind": "alivio",
             "instruction": "Freno de estacionamiento PUESTO y rodillo calzado. Accionar avance suavemente hasta "
                            "que la presión deje de subir. Máximo 3 s.",
             "channels": ["pump1_bar"], "nominal": a},
            {"id": "alivio_p2", "title": "Vibración: presión de arranque", "action": "alivio_p2", "kind": "alivio",
             "instruction": "Tambor apoyado sobre goma o terreno blando. Activar vibración en amplitud alta y "
                            "leer el pico al arrancar.",
             "channels": ["pump2_bar"], "nominal": a * 0.75},
            {"id": "pilotaje", "title": "Presión de carga con motor alto", "action": "pilotaje", "kind": "pilotaje",
             "instruction": "Motor a régimen alto, sin avanzar. Leer la toma de presión de carga.",
             "channels": ["pilot_bar"], "nominal": pi},
        ]
    f1 = "cazo: cerrar del todo" if excav else "función principal 1 contra su tope"
    f2 = "brazo: recoger del todo" if excav else "función principal 2 contra su tope"
    return [
        {"id": "reposo", "title": "Presión de reposo", "action": "reposo", "kind": "reposo",
         "instruction": "Motor a régimen alto, SIN tocar ningún mando. Esperar 10 s y leer las dos bombas.",
         "channels": ["pump1_bar", "pump2_bar"], "range": [lo, hi]},
        {"id": "alivio_p1", "title": "Alivio principal · bomba 1", "action": "alivio_p1", "kind": "alivio",
         "instruction": f"Motor a régimen alto. {f1.capitalize()} y mantener el mando a tope 3 s "
                        "(sin la función de potencia extra). Leer el pico de la bomba 1.",
         "channels": ["pump1_bar"], "nominal": a},
        {"id": "alivio_p2", "title": "Alivio principal · bomba 2", "action": "alivio_p2", "kind": "alivio",
         "instruction": f"Motor a régimen alto. {f2.capitalize()} y mantener el mando a tope 3 s. "
                        "Leer el pico de la bomba 2.",
         "channels": ["pump2_bar"], "nominal": a},
        {"id": "pilotaje", "title": "Presión de pilotaje", "action": "pilotaje", "kind": "pilotaje",
         "instruction": "Motor a régimen alto, palanca de seguridad bajada (mandos activos), sin mover nada. "
                        "Leer la toma de pilotaje.",
         "channels": ["pilot_bar"], "nominal": pi},
    ]


# ----------------------------------------------------------------- evaluación
def _verdict(step: dict, v: float) -> tuple[str, str, float | None]:
    """(estado, texto, desviación %) de una lectura."""
    if step["kind"] == "reposo":
        lo, hi = step["range"]
        if v > hi * 1.35:
            return "alta", f"{v:.0f} bar en reposo (normal {lo}-{hi})", None
        if v > hi:
            return "justa", f"{v:.0f} bar en reposo, algo alta (normal {lo}-{hi})", None
        return "ok", f"{v:.0f} bar en reposo (normal {lo}-{hi})", None
    nom = step["nominal"]
    dev = (v - nom) / nom * 100
    tol_low_ok, tol_low_bad = (-4, -9) if step["kind"] == "alivio" else (-8, -15)
    if dev > (6 if step["kind"] == "alivio" else 12):
        return "alta", f"{v:.0f} bar de {nom:.0f} ({dev:+.0f} %)", dev
    if dev >= tol_low_ok:
        return "ok", f"{v:.0f} bar de {nom:.0f} ({dev:+.0f} %)", dev
    if dev >= tol_low_bad:
        return "justa", f"{v:.0f} bar de {nom:.0f} ({dev:+.0f} %)", dev
    return "baja", f"{v:.0f} bar de {nom:.0f} ({dev:+.0f} %)", dev


# Piezas y horas de cada diagnóstico (EUR, recambio alternativo → original)
_FIX = {
    "bomba_baja": {
        "name": "{pump} no llega a la presión de alivio",
        "causes": ["Válvula de alivio de ese circuito tarada baja, sucia o con el asiento marcado",
                   "Desgaste interno de la bomba (pistones, placa de distribución): fuga interna",
                   "Regulador de la bomba mal ajustado",
                   "Fuga interna en un cilindro o en el distribuidor de esa función"],
        "steps": ["Repetir la medida con aceite caliente y motor a régimen alto",
                  "Probar con otra función de la misma bomba: si todas se quedan bajas, es bomba o alivio principal",
                  "Desmontar, limpiar y tarar la válvula de alivio principal al valor del manual",
                  "Si sigue baja con la válvula bien: prueba de caudal de la bomba (caudalímetro) o desmontaje"],
        "parts": [{"nombre": "Válvula de alivio principal / kit de juntas y tarado", "min": 250, "max": 1200},
                  {"nombre": "Peor caso: bomba hidráulica reconstruida (alt.) / nueva original", "min": 3500, "max": 18000}],
        "hours": 14, "difficulty": 4, "severity": 4,
    },
    "ambas_bajas": {
        "name": "Las dos bombas se quedan bajas por igual",
        "causes": ["Válvula de alivio principal tarada baja (es común a las dos)",
                   "Regulación de potencia / limitación de par de las bombas",
                   "Motor que cae de vueltas al cargar (revisar régimen durante la prueba)"],
        "steps": ["Comprobar régimen del motor durante la prueba: si cae mucho, revisar motor y combustible",
                  "Tarar la válvula de alivio principal al valor del manual",
                  "Revisar ajuste del regulador de potencia de las bombas"],
        "parts": [{"nombre": "Válvula de alivio principal / tarado", "min": 250, "max": 1200}],
        "hours": 4, "difficulty": 3, "severity": 3,
    },
    "alta": {
        "name": "{what} por encima de lo normal",
        "causes": ["Válvula de alivio tarada por encima del valor del manual (manipulada para 'dar más fuerza')",
                   "Válvula de alivio agarrotada"],
        "steps": ["No trabajar así: revientan latiguillos y se castigan bomba y cilindros",
                  "Tarar la válvula al valor del manual y precintar",
                  "Revisar latiguillos y juntas del circuito por si ya han sufrido"],
        "parts": [{"nombre": "Kit de válvula de alivio / tarado", "min": 120, "max": 900}],
        "hours": 2.5, "difficulty": 2, "severity": 3,
    },
    "reposo_alto": {
        "name": "Presión de reposo alta",
        "causes": ["Regulador de bomba o control negativo/de caudal mal ajustado o sucio",
                   "Un distribuidor que no vuelve a neutro (corredera pegada)",
                   "Filtro de retorno obstruido"],
        "steps": ["Comprobar que ningún mando está accionado y que el filtro de retorno no está colmatado",
                  "Revisar el regulador de cada bomba y las señales de control negativo",
                  "Comprobar retorno a neutro de las correderas del distribuidor"],
        "parts": [{"nombre": "Filtro de retorno", "min": 90, "max": 260},
                  {"nombre": "Regulador de bomba (reparación / nuevo)", "min": 600, "max": 2600}],
        "hours": 5, "difficulty": 3, "severity": 2,
    },
    "pilotaje_bajo": {
        "name": "Presión de pilotaje baja",
        "causes": ["Válvula de alivio de pilotaje tarada baja o sucia",
                   "Bomba de pilotaje (engranajes) desgastada", "Filtro de pilotaje obstruido"],
        "steps": ["Cambiar el filtro de pilotaje", "Limpiar y tarar la válvula de alivio de pilotaje",
                  "Si no sube: bomba de pilotaje"],
        "parts": [{"nombre": "Filtro de pilotaje", "min": 40, "max": 160},
                  {"nombre": "Bomba de pilotaje", "min": 450, "max": 1900}],
        "hours": 4, "difficulty": 3, "severity": 3,
    },
}


def evaluate(steps: list[dict], readings: dict, pricing=None, mode_note: str = "") -> dict:
    """Veredicto por canal y averías que salen de la prueba (con coste)."""
    from .kb import as_pricing
    pr = as_pricing(pricing) if pricing is not None else None
    checks, faults = [], []
    by_id = {s["id"]: s for s in steps}
    for s in steps:
        for ch in s["channels"]:
            r = (readings.get(s["id"]) or {}).get(ch)
            if not r or r.get("value") is None:
                continue
            st, txt, dev = _verdict(s, float(r["value"]))
            checks.append({"step": s["id"], "title": s["title"], "channel": ch, "label": CHANNELS[ch],
                           "value": round(float(r["value"]), 1), "source": r.get("source", "manometro"),
                           "status": st, "text": txt, "deviation_pct": None if dev is None else round(dev, 1),
                           "nominal": s.get("nominal"), "range": s.get("range")})

    def add(key, code, value_txt, **fmt):
        f = _FIX[key]
        cost = pr.fault(f["parts"], f["hours"], code) if pr else {"cost_min_eur": 0, "cost_max_eur": 0,
                                                                  "labour_hours": f["hours"], "labour_eur": 0}
        faults.append({
            "code": code, "spn": None, "fmi": None, "active": True, "occurrences": 1,
            "source": "Prueba de bombas", "source_name": "Prueba de bombas", "protocol": "Prueba",
            "kind": "prueba", "kinds": ["prueba"],
            "name": f["name"].format(**fmt), "system": "Hidráulica · bombas", "fmi_text": value_txt,
            "fault_type": "condicion", "severity": f["severity"], "critical": False, "warning": None,
            "causes": f["causes"], "steps": f["steps"], "parts": f["parts"], "difficulty": f["difficulty"],
            **cost, "known": True, "proprietary": False, "name_language": "es", "brand_note": "",
        })

    relief = {c["channel"]: c for c in checks if by_id[c["step"]]["kind"] == "alivio"}
    lows = [c for c in relief.values() if c["status"] in ("baja", "justa")]
    both_low = len(relief) >= 2 and len(lows) == len(relief) and \
        max(c["deviation_pct"] for c in lows) - min(c["deviation_pct"] for c in lows) < 4
    if both_low:
        add("ambas_bajas", "BOMBAS 1+2", " · ".join(f"{c['label']}: {c['text']}" for c in lows))
    else:
        for c in lows:
            if c["status"] == "baja" or (c["status"] == "justa" and len(relief) >= 2):
                add("bomba_baja", f"{c['label'].upper()} · ALIVIO", f"Prueba de presión: {c['text']}", pump=c["label"])
    for c in checks:
        kind = by_id[c["step"]]["kind"]
        if c["status"] == "alta" and kind in ("alivio", "pilotaje"):
            add("alta", f"{c['label'].upper()} · ALTA", f"Prueba de presión: {c['text']}",
                what=f"Presión de {c['label'].lower()}")
        if kind == "reposo" and c["status"] in ("alta",):
            add("reposo_alto", f"{c['label'].upper()} · REPOSO", f"Prueba de presión: {c['text']}")
        if kind == "pilotaje" and c["status"] == "baja":
            add("pilotaje_bajo", "PILOTAJE", f"Prueba de presión: {c['text']}")

    comp = None
    if len(relief) >= 2:
        vals = [c["value"] for c in relief.values()]
        diff = (max(vals) - min(vals)) / max(vals) * 100
        comp = {"diff_pct": round(diff, 1), "text": f"Diferencia entre bombas al alivio: {diff:.1f} %".replace(".", ",")
                + (" (más de un 5 %: la más baja rinde menos)" if diff > 5 else " (iguales)")}
    if not checks:
        verdict, label = "sin_datos", "Prueba sin lecturas"
    elif any(c["status"] in ("baja", "alta") for c in checks):
        verdict, label = "mal", "Bombas: hay que actuar"
    elif any(c["status"] == "justa" for c in checks):
        verdict, label = "justa", "Bombas: justas, vigilar"
    else:
        verdict, label = "ok", "Bombas en buen estado (presión)"
    return {"verdict": verdict, "label": label, "checks": checks, "comparison": comp, "faults": faults,
            "cost_min_eur": sum(f["cost_min_eur"] for f in faults), "cost_max_eur": sum(f["cost_max_eur"] for f in faults),
            "note": "La presión indica si bombas y válvulas aguantan; el caudal (rapidez) se comprueba con tiempos de "
                    "ciclo o caudalímetro." + (f" {mode_note}" if mode_note else "")}


# ---------------------------------------------------------------- la prueba
class PumpTest:
    """Estado de la prueba guiada. La estación la maneja; el estado viaja en la instantánea."""

    def __init__(self, machine_class: str, alivio: float | None = None, pilotaje: float | None = None,
                 on_step=None):
        sp = SPECS.get(machine_class, GENERIC_SPEC)
        self.machine_class = machine_class
        self.spec_source = "manual" if alivio else "orientativo"
        self.spec_note = sp["nota"]
        self.steps = steps_for(machine_class, alivio, pilotaje)
        self.readings: dict[str, dict] = {}
        self.index = 0
        self.active = True
        self.finished = False
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.marks: list[dict] = []      # cuándo se tomó cada lectura (para buscar presiones en la grabación)
        self.on_step = on_step
        self._notify()

    def _notify(self):
        self.step_started = time.time()
        if self.on_step:
            try:
                self.on_step(None if self.finished else self.steps[self.index]["action"])
            except Exception:  # noqa: BLE001
                pass

    @property
    def step(self) -> dict:
        return self.steps[self.index]

    def capture(self, log: dict) -> dict:
        """Toma la lectura automática de la centralita: pico en alivio, mediana en reposo/pilotaje."""
        got = {}
        now = time.time()
        # solo lo medido en este paso, tras 1 s para que la presión se asiente
        since = max(now - (8 if self.step["kind"] == "alivio" else 4), self.step_started + 1.0)
        for ch in self.step["channels"]:
            samples = [v for t, v in log.get(ch, []) if t >= since]
            if len(samples) < 3:
                continue
            if self.step["kind"] == "alivio":
                sm = [statistics.median(samples[i:i + 3]) for i in range(len(samples) - 2)]
                val = max(sm)
            else:
                val = statistics.median(samples)
            got[ch] = self._store(ch, val, "centralita")
        return got

    def manual(self, ch: str, value: float) -> dict:
        return self._store(ch, float(value), "manometro")

    def _store(self, ch, value, source):
        r = {"value": round(value, 1), "source": source, "at": datetime.now(timezone.utc).isoformat(), "t": time.time()}
        self.readings.setdefault(self.step["id"], {})[ch] = r
        self.marks.append({"step": self.step["id"], "kind": self.step["kind"], "channel": ch, **r})
        return r

    def go(self, delta: int):
        if self.finished:
            return
        self.index = max(0, min(len(self.steps) - 1, self.index + delta))
        self._notify()

    def finish(self):
        self.finished, self.active = True, False
        self._notify()

    def to_dict(self, pricing=None) -> dict:
        src = {r["source"] for rr in self.readings.values() for r in rr.values()}
        mode = ("Lecturas de la centralita." if src == {"centralita"} else
                "Lecturas de manómetro de taller." if src == {"manometro"} else
                "Lecturas de centralita y de manómetro." if src else "")
        return {
            "active": self.active, "finished": self.finished, "index": self.index,
            "spec_source": self.spec_source, "spec_note": self.spec_note, "safety": SEGURIDAD,
            "started_at": self.started_at, "marks": self.marks,
            "steps": [{**s, "readings": {k: {kk: vv for kk, vv in v.items() if kk != "t"}
                                         for k, v in (self.readings.get(s["id"]) or {}).items()}} for s in self.steps],
            "result": evaluate(self.steps, self.readings, pricing, mode),
        }


# ------------------------------------------------- perfiles (presiones por CAN)
def load_profiles(folder: Path = PRESION_DIR) -> list[dict]:
    out = []
    for f in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            p["_file"] = f.name
            out.append(p)
        except Exception:  # noqa: BLE001
            continue
    return out


def profile_applies(p: dict, brand_key: str, model: str, serial: str) -> bool:
    if p.get("marca") and p["marca"] != brand_key:
        return False
    if p.get("modelos") and not any(m.lower() in (model or "").lower() for m in p["modelos"]):
        return False
    pref = p.get("solo_serie_prefijo")
    if pref and not (serial or "").upper().startswith(pref.upper()):
        return False
    return True


def decode_signal(sig: dict, data: bytes) -> float | None:
    b, n = sig["byte"], sig.get("len", 2)
    if len(data) < b + n:
        return None
    raw = int.from_bytes(data[b:b + n], sig.get("orden", "little"))
    if raw >= (0xFE << (8 * (n - 1))):
        return None   # J1939: 0xFE.. = error, 0xFF.. = no disponible
    return raw * sig.get("escala", 1.0) + sig.get("offset", 0.0)


# --------------------------------------- buscador de presiones en grabaciones
SCALES = [1.0, 0.5, 0.25, 0.2, 0.1, 0.08, 0.05, 0.04, 0.02, 0.01, 1 / 128, 1 / 256 * 10]


def find_pressure_signals(frames, expected_relief: float, marks: list[dict] | None = None, top: int = 6,
                          constant: bool = False) -> list[dict]:
    """Busca en las tramas propias del fabricante qué bytes son presiones de bomba.

    ``frames``: iterable de (t, can_id, data) de una grabación en la que se llevó la
    hidráulica contra su tope al menos una vez. ``marks``: lecturas de manómetro con su
    hora (de una prueba de bombas hecha a la vez); si hay, se usan como verdad.
    Devuelve candidatos ordenados (lo más probable primero).
    """
    from .j1939 import J1939Id
    series: dict[tuple, list] = {}
    for t, cid, data in frames:
        jid = J1939Id.parse(cid)
        if not (jid.pgn >= 0xFF00 or jid.pgn == 0xEF00):     # solo mensajes propietarios (PropA / PropB)
            continue
        series.setdefault((jid.pgn, jid.source), []).append((t, bytes(data)))
    out = []
    for (pgn, sa), rows in series.items():
        if len(rows) < 30:
            continue
        maxlen = max(len(d) for _, d in rows)
        for n in (2, 1):
            for b in range(0, maxlen - n + 1):
                for order in (("little", "big") if n == 2 else ("little",)):
                    sig = {"byte": b, "len": n, "orden": order, "escala": 1.0}
                    vals = [(t, decode_signal(sig, d)) for t, d in rows]
                    vals = [(t, v) for t, v in vals if v is not None]
                    if len(vals) < 30:
                        continue
                    raw = [v for _, v in vals]
                    lo, hi = min(raw), max(raw)
                    if hi - lo < 8 or len(set(raw)) < 6:
                        continue
                    steps = [raw[i + 1] - raw[i] for i in range(len(raw) - 1)]
                    if sum(1 for s in steps if s == 1 or s == -255) > 0.8 * len(steps):
                        continue                                    # contador de mensajes
                    # una presión real cambia de forma suave; un campo mal alineado (medio byte de otra
                    # señal) salta sin sentido de una trama a la siguiente
                    jitter_raw = statistics.median(abs(x) for x in steps) if steps else 0
                    for sc in SCALES:
                        peak = sorted(raw)[int(len(raw) * 0.995)] * sc
                        err_peak = abs(peak - expected_relief) / expected_relief
                        if constant:                                # pilotaje: valor casi fijo
                            peak = statistics.median(raw) * sc
                            err_peak = abs(peak - expected_relief) / expected_relief
                        if err_peak > 0.25:
                            continue
                        base = sorted(raw)[len(raw) // 10] * sc
                        if not constant and base > 0.4 * expected_relief:
                            continue                                # en reposo debe bajar mucho
                        hold = sum(1 for v in raw if v * sc > 0.85 * peak) / len(raw)
                        score = 1 - err_peak * 2 + min(hold, 0.2) * 2 - jitter_raw * sc / expected_relief * 30
                        # J1939 manda los datos en little-endian y alineados a byte par casi siempre
                        score -= (0.3 if order == "big" else 0) + (0.2 if n == 2 and b % 2 else 0)
                        err_marks = None
                        if marks:
                            errs = []
                            for m in marks:
                                # la lectura se apunta DESPUÉS de mirar la aguja: se busca en los segundos previos
                                win = 8 if m.get("kind") == "alivio" else 3
                                near = [v for t, v in vals if m["t"] - win <= t <= m["t"] + 0.3]
                                if near:
                                    got = max(near) * sc if m.get("kind") == "alivio" else statistics.median(near) * sc
                                    errs.append(abs(got - m["value"]) / max(m["value"], 1))
                            if errs:
                                err_marks = sum(errs) / len(errs)
                                score += 2 - err_marks * 10
                        out.append({"pgn": pgn, "sa": sa, **sig, "escala": sc, "peak_bar": round(peak, 1),
                                    "base_bar": round(base, 1), "hold_pct": round(hold * 100, 1),
                                    "manometer_error_pct": None if err_marks is None else round(err_marks * 100, 1),
                                    "score": round(score, 3)})
    out.sort(key=lambda c: -c["score"])
    # una sola escala por campo (la mejor)
    seen, best = set(), []
    for c in out:
        k = (c["pgn"], c["sa"], c["byte"], c["len"], c["orden"])
        if k in seen:
            continue
        seen.add(k)
        best.append(c)
    return best[:top]


def read_frames(path: str | Path):
    """Tramas de una grabación .blf como (t, can_id, data)."""
    import can
    for m in can.LogReader(str(path)):
        if m.is_extended_id and not m.is_error_frame:
            yield m.timestamp, m.arbitration_id, bytes(m.data)


def profile_from_recording(path: str | Path, alivio: float, pilotaje: float | None = None,
                           session: dict | None = None, marca: str = "", modelo: str = "") -> dict:
    """Saca el perfil de presiones de una máquina a partir de una grabación.

    Lo ideal: grabar mientras se hace la prueba de bombas con manómetro; entonces cada
    lectura del manómetro sirve para confirmar el byte y la escala (``session``).
    """
    frames = list(read_frames(path))
    marks = ((session or {}).get("pump_test") or {}).get("marks") or []
    manual = [m for m in marks if m.get("source") == "manometro" and m.get("t")]
    result = {"marca": marca, "modelos": [modelo] if modelo else [], "verificado": False,
              "origen": Path(path).name, "creado": datetime.now(timezone.utc).isoformat(), "senales": {},
              "candidatos": {}}
    taken = set()
    for ch in ("pump1_bar", "pump2_bar", "pilot_bar"):
        if ch == "pilot_bar" and not pilotaje:
            continue
        mk = [m for m in manual if m["channel"] == ch]
        cands = find_pressure_signals(frames, pilotaje if ch == "pilot_bar" else alivio, mk,
                                      constant=ch == "pilot_bar")
        cands = [c for c in cands if (c["pgn"], c["sa"], c["byte"]) not in taken]
        result["candidatos"][ch] = cands
        if not cands or (ch == "pilot_bar" and not mk):
            continue          # el pilotaje solo se acepta confirmado con manómetro
        best = cands[0]
        taken.add((best["pgn"], best["sa"], best["byte"]))
        result["senales"][ch] = {k: best[k] for k in ("pgn", "sa", "byte", "len", "orden", "escala")}
        if mk and best.get("manometer_error_pct") is not None and best["manometer_error_pct"] < 3:
            result["verificado"] = "manometro"
    return result
