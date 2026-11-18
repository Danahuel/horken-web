"""Detección de manipulación de horas/km y de modificaciones de centralitas.

Ningún método da certeza absoluta: se cruzan contadores que un manipulador
rara vez cambia todos a la vez y se da un nivel de sospecha con las pruebas.

Contadores usados (cada centralita puede guardar los suyos):
  * Horas de motor (SPN 247) en motor, transmisión, cuadro, cabina...
  * Revoluciones totales del motor (SPN 249): rev / (horas·60) = régimen medio.
    Si las horas se rebajan y las revoluciones no, sale un régimen imposible.
  * Combustible total consumido (SPN 250): litros / horas = consumo medio.
  * Distancia total (SPN 245) vs distancia alta resolución (SPN 917).
  * Lecturas anteriores guardadas de la misma máquina (por nº de serie).
"""
from __future__ import annotations

# Consumo medio de vida razonable (L/h), incluye ralentí. Orientativo.
MACHINE_CLASSES = {
    "excavadora_20t": ("Excavadora 14-25 t", 8, 24),
    "excavadora_grande": ("Excavadora 30-50 t", 15, 40),
    "cargadora_ruedas": ("Cargadora de ruedas", 8, 30),
    "dumper_articulado": ("Dúmper articulado", 12, 35),
    "bulldozer": ("Bulldozer", 12, 45),
    "rodillo": ("Rodillo compactador", 4, 16),
    "trituradora": ("Trituradora / biotrituradora", 15, 70),
    "retro_mixta": ("Retrocargadora mixta", 4, 12),
    "minicargadora": ("Minicargadora / minipala", 3, 10),
    "camion": ("Camión", 10, 45),
    "coche": ("Coche / furgoneta", 0.5, 15),
    "manipuladora": ("Manipuladora de material", 10, 35),
    "generica": ("Máquina (clase no indicada)", 2, 80),
}

AVG_RPM_MIN, AVG_RPM_MAX = 600, 2100   # régimen medio de vida plausible (diésel industrial)
MAX_AVG_SPEED_KMH = {"camion": 90, "dumper_articulado": 40, "cargadora_ruedas": 30, "retro_mixta": 30}


def _n(v, d=1):
    """Número en formato español: 9.876,2"""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ev(title, detail, weight, level):
    return {"title": title, "detail": detail, "weight": weight, "level": level}


def analyze_counters(ecus: dict, machine_class: str = "generica", history: list[dict] | None = None,
                     extra_evidence: list[dict] | None = None) -> dict:
    """``ecus``: {sa: {"name", "engine_hours", "total_revolutions", "total_fuel_l", "total_km", "total_km_hr"}}."""
    evidence, checks = [], 0
    hours = {sa: e["engine_hours"] for sa, e in ecus.items() if e.get("engine_hours") is not None}
    names = {sa: e.get("name") or str(sa) for sa, e in ecus.items()}
    ref_sa = 0 if 0 in hours else (sorted(hours, key=str)[0] if hours else None)
    ref_hours = hours.get(ref_sa) if ref_sa is not None else None

    # 1. Horas entre centralitas
    if len(hours) >= 2:
        checks += 1
        hi, lo = max(hours.values()), min(hours.values())
        diff = hi - lo
        if diff > max(20.0, 0.02 * hi):
            listing = ", ".join(f"{names[sa]}: {_n(h, 1)} h" for sa, h in sorted(hours.items()))
            evidence.append(_ev("Horas distintas entre centralitas",
                                f"{listing}. Diferencia de {_n(diff, 1)} h. Las centralitas cuentan las horas a la vez; "
                                "una diferencia grande indica que una se ha rebajado o se ha cambiado una centralita.",
                                55, "alta"))
        else:
            evidence.append(_ev("Horas coherentes entre centralitas",
                                f"{len(hours)} centralitas coinciden (diferencia {_n(diff, 1)} h).", 0, "ok"))

    eng = ecus.get(ref_sa, {}) if ref_sa is not None else {}
    # 2. Régimen medio de vida
    revs = eng.get("total_revolutions")
    if ref_hours and revs:
        checks += 1
        avg = revs / (ref_hours * 60)
        if avg > AVG_RPM_MAX:
            real_h = revs / (60 * 1400)
            evidence.append(_ev("Régimen medio imposible",
                                f"Revoluciones totales {_n(revs, 0)} / {_n(ref_hours, 1)} h = {_n(avg, 0)} rpm de media "
                                f"durante toda su vida (normal {AVG_RPM_MIN}-{AVG_RPM_MAX}). Con un régimen medio "
                                f"típico de 1.400 rpm corresponderían unas {_n(real_h, 0)} h.", 45, "alta"))
        elif avg < AVG_RPM_MIN * 0.7:
            evidence.append(_ev("Revoluciones totales anormalmente bajas",
                                f"Régimen medio de {_n(avg, 0)} rpm: el contador de revoluciones pudo reiniciarse "
                                "(cambio de ECU) o manipularse.", 15, "media"))
        else:
            evidence.append(_ev("Régimen medio plausible", f"{_n(avg, 0)} rpm de media de vida.", 0, "ok"))

    # 3. Consumo medio de vida
    fuel = eng.get("total_fuel_l")
    label, fmin, fmax = MACHINE_CLASSES.get(machine_class, MACHINE_CLASSES["generica"])
    if ref_hours and fuel:
        checks += 1
        lh = fuel / ref_hours
        if lh > fmax:
            evidence.append(_ev("Consumo medio demasiado alto para las horas",
                                f"{_n(fuel, 0)} L / {_n(ref_hours, 1)} h = {_n(lh, 1)} L/h. Para {label} lo normal es "
                                f"{fmin}-{fmax} L/h. Indica que la máquina tiene más horas de las que marca "
                                f"(≈{_n(fuel / ((fmin + fmax) / 2), 0)} h según el gasoil consumido).", 30, "alta"))
        elif lh < fmin * 0.6:
            evidence.append(_ev("Consumo medio demasiado bajo",
                                f"{_n(lh, 1)} L/h (normal {fmin}-{fmax}). El contador de combustible pudo reiniciarse.",
                                10, "media"))
        else:
            evidence.append(_ev("Consumo medio coherente", f"{_n(lh, 1)} L/h ({label}: {fmin}-{fmax} L/h).", 0, "ok"))

    # 4. Kilómetros
    km_sources = {sa: e["total_km"] for sa, e in ecus.items() if e.get("total_km") is not None}
    km_hr = {sa: e["total_km_hr"] for sa, e in ecus.items() if e.get("total_km_hr") is not None}
    all_km = {**{(sa, "VD"): v for sa, v in km_sources.items()}, **{(sa, "VDHR"): v for sa, v in km_hr.items()}}
    if len(all_km) >= 2:
        checks += 1
        hi, lo = max(all_km.values()), min(all_km.values())
        if hi - lo > max(50, 0.01 * hi):
            listing = ", ".join(f"{names.get(sa, sa)} ({kind}): {_n(v, 0)} km" for (sa, kind), v in all_km.items())
            evidence.append(_ev("Kilómetros distintos entre contadores", listing, 50, "alta"))
        else:
            evidence.append(_ev("Kilómetros coherentes", f"{len(all_km)} contadores coinciden.", 0, "ok"))
    km = max(all_km.values()) if all_km else None
    if km and ref_hours and machine_class in MAX_AVG_SPEED_KMH:
        checks += 1
        speed = km / ref_hours
        if speed > MAX_AVG_SPEED_KMH[machine_class]:
            evidence.append(_ev("Velocidad media imposible",
                                f"{_n(km, 0)} km / {_n(ref_hours, 1)} h = {_n(speed, 0)} km/h de media.", 35, "alta"))

    # 5. Historial de lecturas anteriores
    if history and ref_hours is not None:
        checks += 1
        prev = max(history, key=lambda h: h.get("engine_hours") or 0)
        if prev.get("engine_hours") and prev["engine_hours"] > ref_hours + 1:
            evidence.append(_ev("Horas MENORES que en una revisión anterior",
                                f"El {prev.get('date', '?')} marcaba {_n(prev['engine_hours'], 1)} h y ahora "
                                f"{_n(ref_hours, 1)} h. Prueba directa de manipulación o cambio de centralita.",
                                100, "alta"))

    if extra_evidence:
        evidence.extend(extra_evidence)
        checks += len(extra_evidence)
    score = min(100, sum(e["weight"] for e in evidence))
    if checks == 0:
        verdict, label_v = "sin_datos", "Datos insuficientes"
    elif score >= 50:
        verdict, label_v = "manipulado", "Manipulación MUY PROBABLE"
    elif score >= 20:
        verdict, label_v = "sospechoso", "Sospechoso: revisar"
    else:
        verdict, label_v = "ok", "Sin indicios de manipulación"
    est = None
    if verdict == "manipulado":
        cands = [max(hours.values())] if hours else []
        if revs:
            cands.append(revs / (60 * 1400))
        est = round(max(cands)) if cands else None
    return {"verdict": verdict, "label": label_v, "score": score, "checks": checks,
            "reported_hours": ref_hours, "estimated_real_hours": est,
            "machine_class": machine_class, "evidence": evidence}


def fingerprint(ecu: dict) -> list[str]:
    """Software + calibraciones (DM19) de una centralita: si cambia entre revisiones, se ha reprogramado."""
    return list(ecu.get("software") or []) + [f"CAL {c['cal_id']} CVN {c['cvn']}" for c in ecu.get("calibrations") or []]


def analyze_modifications(ecus: dict, previous_software: dict | None = None, extra: list[dict] | None = None) -> dict:
    """Busca centralitas cambiadas o software modificado."""
    findings = list(extra or [])
    serials = {sa: e["component"]["serial"] for sa, e in ecus.items()
               if e.get("component") and e["component"].get("serial")}
    if len(set(serials.values())) > 1:
        listing = ", ".join(f"{ecus[sa].get('name')}: {s}" for sa, s in serials.items())
        findings.append({"title": "Nº de serie distinto entre centralitas", "level": "alta",
                         "detail": f"{listing}. Una centralita procede de otra máquina (sustitución o "
                                   "'trasplante', método habitual para reiniciar horas)."})
    for sa, e in ecus.items():
        sw = fingerprint(e)
        if previous_software and str(sa) in previous_software and previous_software[str(sa)] and sw \
                and previous_software[str(sa)] != sw:
            findings.append({"title": f"Software cambiado en {e.get('name')}", "level": "media",
                             "detail": f"Antes: {previous_software[str(sa)]} → ahora: {sw}. Puede ser una "
                                       "actualización oficial o una reprogramación (chip/tuning)."})
        if any(tag in " ".join(sw).upper() for tag in ("TUN", "STAGE", "MOD", "CHIP", "REMAP")):
            findings.append({"title": f"Identificador de software no original en {e.get('name')}", "level": "alta",
                             "detail": f"Versión: {sw}"})
    level = "alta" if any(f["level"] == "alta" for f in findings) else ("media" if findings else "ok")
    return {"level": level, "findings": findings,
            "note": "La reprogramación profesional puede no dejar rastro legible por J1939; "
                    "confirmar con el software oficial si hay dudas."}


SEVERITY_PENALTY = {5: 26, 4: 16, 3: 8, 2: 3, 1: 1}


def health_index(active_dtcs: list[dict], tamper: dict, mods: dict) -> dict:
    """Índice de estado 0-100 (100 = perfecta). Resume averías activas, integridad
    de horas/km y modificaciones en una sola cifra para comparar máquinas."""
    score = 100.0
    worst = {}
    for d in active_dtcs:  # una avería repetida en varias centralitas no penaliza doble
        key = (d.get("spn"), d.get("fmi"), d.get("code"))
        worst[key] = max(worst.get(key, 0), int(d.get("severity", 1)))
    for sev in sorted(worst.values(), reverse=True):
        score -= SEVERITY_PENALTY.get(sev, 1)
    score -= {"manipulado": 22, "sospechoso": 9}.get(tamper.get("verdict"), 0)
    score -= {"alta": 12, "media": 5}.get(mods.get("level"), 0)
    score = max(0, min(100, round(score)))
    label = ("Óptimo" if score >= 85 else "Aceptable" if score >= 65
             else "Requiere atención" if score >= 40 else "Crítico")
    return {"score": score, "label": label}


def _norm(s) -> str:
    return "".join(ch for ch in str(s or "").upper() if ch.isalnum())


def _ref_ecu(ecus: dict):
    hours = {sa: e["engine_hours"] for sa, e in ecus.items() if e.get("engine_hours") is not None}
    sa = 0 if 0 in hours else (sorted(hours, key=str)[0] if hours else None)
    return sa, (ecus.get(sa, {}) if sa is not None else {})


def cross_checks(ecus: dict, plate: dict | None, year_now: int | None = None) -> tuple[dict, list[dict], list[dict]]:
    """Cruza lo que dicen las centralitas con la placa y con contadores de uso.

    Devuelve (uso, pruebas para el horómetro, hallazgos de modificación)."""
    from datetime import date
    plate = plate or {}
    year_now = year_now or date.today().year
    ev, mods = [], []
    sa, eng = _ref_ecu(ecus)
    hours = eng.get("engine_hours")

    def first(key):
        if eng.get(key) is not None:
            return eng[key]
        return next((e[key] for e in ecus.values() if e.get(key) is not None), None)

    usage = {"engine_hours": hours, "idle_hours": first("idle_hours"), "idle_fuel_l": first("idle_fuel_l"),
             "total_fuel_l": first("total_fuel_l"), "cleared_min": first("cleared_min"), "mil_min": first("mil_min"),
             "cleared_km": first("cleared_km")}
    if hours and usage["total_fuel_l"]:
        usage["fuel_per_hour"] = round(usage["total_fuel_l"] / hours, 2)
    if hours and first("total_revolutions"):
        usage["avg_rpm"] = round(first("total_revolutions") / (hours * 60))

    # Ralentí
    idle = usage["idle_hours"]
    if hours and idle is not None:
        usage["idle_pct"] = round(idle / hours * 100, 1)
        if idle > hours + 1:
            ev.append(_ev("Horas al ralentí mayores que las horas totales",
                          f"La centralita registra {_n(idle, 1)} h al ralentí pero solo {_n(hours, 1)} h en total. "
                          "Es imposible: el horómetro total se ha rebajado y el contador de ralentí no.", 50, "alta"))
        else:
            ev.append(_ev("Horas al ralentí coherentes",
                          f"{_n(idle, 0)} h al ralentí ({_n(usage['idle_pct'], 0)} % de su vida).", 0, "ok"))

    # Borrado de averías (DM21)
    cm = usage["cleared_min"]
    if cm is not None:
        h = cm / 60
        if h < 10:
            ev.append(_ev("Averías borradas hace muy poco",
                          f"El último borrado de códigos fue hace {_n(h, 1)} h de motor. Antes de una compra es una señal "
                          "de alerta: trabaje la máquina un rato y vuelva a leer.", 20, "media"))
        else:
            ev.append(_ev("Sin borrado reciente de averías", f"Último borrado hace {_n(h, 0)} h de motor.", 0, "ok"))
    if usage["mil_min"]:
        ev.append(_ev("Testigo de avería encendido en su historial",
                      f"Ha trabajado {_n(usage['mil_min'] / 60, 1)} h con el testigo de avería encendido.", 0, "media"))

    # Placa: horas del cuadro
    ph = plate.get("hours")
    if ph is not None and hours:
        diff = abs(ph - hours)
        if diff > max(20, hours * 0.02):
            ev.append(_ev("Las horas del cuadro no coinciden con la centralita",
                          f"Cuadro: {_n(ph, 0)} h · centralita de motor: {_n(hours, 1)} h (diferencia {_n(diff, 0)} h).",
                          55, "alta"))
        else:
            ev.append(_ev("Horas del cuadro coherentes con la centralita",
                          f"Cuadro {_n(ph, 0)} h · centralita {_n(hours, 1)} h.", 0, "ok"))
    # Placa: km del cuadro
    pk = plate.get("km")
    km = next((e.get("total_km") for e in ecus.values() if e.get("total_km") is not None), None)
    if pk is not None and km:
        if abs(pk - km) > max(50, km * 0.01):
            ev.append(_ev("Los km del cuadro no coinciden con la centralita",
                          f"Cuadro: {_n(pk, 0)} km · centralita: {_n(km, 0)} km.", 55, "alta"))
        else:
            ev.append(_ev("Km del cuadro coherentes", f"{_n(km, 0)} km.", 0, "ok"))
    # Año de fabricación: horas por año
    yr = plate.get("year")
    if yr and hours:
        age = max(0.5, year_now - int(yr) + 0.5)
        hpy = hours / age
        usage["hours_per_year"] = round(hpy)
        if hpy > 6000:
            ev.append(_ev("Horas por año imposibles", f"{_n(hpy, 0)} h/año desde {yr}.", 30, "alta"))
        elif hpy < 150 and age >= 3:
            ev.append(_ev("Muy pocas horas para su antigüedad",
                          f"{_n(hours, 0)} h en unos {_n(age, 0)} años = {_n(hpy, 0)} h/año. Lo habitual en obra es "
                          "500-2.000 h/año. Puede haber estado parada… o tener el horómetro rebajado.", 15, "media"))
        else:
            ev.append(_ev("Uso anual normal", f"{_n(hpy, 0)} h/año desde {yr}.", 0, "ok"))

    # Placa: número de serie frente a centralitas
    ps = _norm(plate.get("serial"))
    if len(ps) >= 4:
        # El VIN (17 caracteres) y el nº de serie de máquina son números distintos: solo se compara
        # el VIN si lo que se escribió en la placa es un VIN.
        ids = [(e.get("name", str(k)), str(v)) for k, e in ecus.items()
               for v in ((e.get("component") or {}).get("serial"), e.get("vin") if len(ps) == 17 else None)
               if v and len(_norm(v)) >= 4]
        if ids:
            bad = [(n, v) for n, v in ids if ps not in _norm(v) and _norm(v) not in ps]
            if bad:
                mods.append({"title": "El nº de serie de la placa no coincide con la centralita", "level": "alta",
                             "detail": f"Placa: {plate.get('serial')} · " + ", ".join(f"{n}: {v}" for n, v in bad)
                             + ". La centralita puede proceder de otra máquina."})
    return usage, ev, mods
