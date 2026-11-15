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
    "generica": ("Máquina (clase no indicada)", 2, 80),
}

AVG_RPM_MIN, AVG_RPM_MAX = 600, 2100   # régimen medio de vida plausible (diésel industrial)
MAX_AVG_SPEED_KMH = {"camion": 90, "dumper_articulado": 40, "cargadora_ruedas": 30, "retro_mixta": 30}


def _n(v, d=1):
    """Número en formato español: 9.876,2"""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ev(title, detail, weight, level):
    return {"title": title, "detail": detail, "weight": weight, "level": level}


def analyze_counters(ecus: dict, machine_class: str = "generica", history: list[dict] | None = None) -> dict:
    """``ecus``: {sa: {"name", "engine_hours", "total_revolutions", "total_fuel_l", "total_km", "total_km_hr"}}."""
    evidence, checks = [], 0
    hours = {sa: e["engine_hours"] for sa, e in ecus.items() if e.get("engine_hours") is not None}
    names = {sa: e.get("name", f"0x{sa:02X}") for sa, e in ecus.items()}
    ref_sa = 0 if 0 in hours else (min(hours) if hours else None)
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


def analyze_modifications(ecus: dict, previous_software: dict | None = None) -> dict:
    """Busca centralitas cambiadas o software modificado."""
    findings = []
    serials = {sa: e["component"]["serial"] for sa, e in ecus.items()
               if e.get("component") and e["component"].get("serial")}
    if len(set(serials.values())) > 1:
        listing = ", ".join(f"{ecus[sa].get('name')}: {s}" for sa, s in serials.items())
        findings.append({"title": "Nº de serie distinto entre centralitas", "level": "alta",
                         "detail": f"{listing}. Una centralita procede de otra máquina (sustitución o "
                                   "'trasplante', método habitual para reiniciar horas)."})
    for sa, e in ecus.items():
        sw = e.get("software") or []
        if previous_software and str(sa) in previous_software and previous_software[str(sa)] != sw:
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
