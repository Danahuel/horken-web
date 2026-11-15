"""Base de conocimiento: convierte un SPN/FMI en un diagnóstico útil para el taller."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..j1939 import Dtc, source_name

_DIR = Path(__file__).parent
LABOUR_RATE_EUR_H = 55.0  # tarifa de mano de obra por defecto (editable en config)

ELECTRICAL_STEPS = {
    "2": ["Prueba de meneo (wiggle test) del mazo y conector con la herramienta mostrando el valor en vivo",
          "Revisar pines doblados, corrosión o humedad en el conector",
          "Comprobar que el mazo no roza con piezas metálicas o calientes"],
    "3": ["Desconectar el sensor y medir la señal con llave en ON: si sigue alta, cortocircuito a positivo en el mazo",
          "Comprobar la masa del sensor (posible masa abierta)",
          "Medir la tensión de referencia (normalmente 5 V)"],
    "4": ["Desconectar el sensor: si el código cambia a FMI 3, el sensor está defectuoso",
          "Buscar cortocircuito a masa del cable de señal (aislamiento dañado)",
          "Medir la tensión de referencia (normalmente 5 V)"],
    "5": ["Comprobar continuidad de cada cable entre la ECU y el componente (circuito abierto)",
          "Medir la resistencia del componente (bobina/solenoide) y comparar con la especificación",
          "Revisar conectores sueltos o terminales abiertos"],
    "6": ["Medir la resistencia del componente: un valor muy bajo indica bobina en cortocircuito",
          "Buscar cable de salida en contacto con masa",
          "Desconectar el componente: si el código desaparece, el componente está defectuoso"],
    "8": ["Comprobar el entrehierro y la limpieza del sensor (limaduras)",
          "Revisar el blindaje del cable y su recorrido lejos de cables de potencia",
          "Comprobar la rueda dentada o el elemento de medida"],
    "12": ["Comprobar alimentación y masa del dispositivo",
           "Comprobar comunicación con la herramienta de diagnóstico",
           "Sustituir el componente si la alimentación es correcta"],
    "13": ["Realizar la calibración con el software del fabricante",
           "Si no calibra, sustituir el componente"],
}

GENERIC_ELECTRICAL_STEPS = ["Inspección visual de mazo y conector", "Medir alimentación, masa y señal con polímetro",
                            "Sustituir el componente si el circuito es correcto"]

INJECTOR = {
    "electrico": {"piezas": [{"nombre": "Revisión mazo de inyectores (bajo tapa de balancines)", "min": 0, "max": 150}],
                  "dificultad": 3, "horas_mo": 3},
    "condicion": {"causas": ["Inyector desgastado o con caudal incorrecto", "Combustible contaminado (agua/suciedad)",
                             "Compresión baja en ese cilindro"],
                  "pasos": ["Prueba de corte de cilindro con la herramienta del fabricante",
                            "Prueba de retorno (fuga) del inyector",
                            "Medir resistencia del solenoide del inyector",
                            "Sustituir inyector y cargar su código de compensación (trim/IMA) en la ECU"],
                  "piezas": [{"nombre": "Inyector (reconstruido → nuevo)", "min": 300, "max": 1300}],
                  "dificultad": 4, "horas_mo": 4},
}


@lru_cache
def _load(name: str) -> dict:
    return json.loads((_DIR / name).read_text(encoding="utf-8"))


def fmi_table() -> dict:
    return {k: v for k, v in _load("fmi.json").items() if not k.startswith("_")}


def spn_table() -> dict:
    return {k: v for k, v in _load("spn.json").items() if not k.startswith("_")}


def brands() -> dict:
    return {k: v for k, v in _load("marcas.json").items() if not k.startswith("_")}


def detect_brand(make: str | None) -> str:
    m = (make or "").upper()
    for key, b in brands().items():
        if any(alias in m for alias in b["alias"]):
            return key
    return "generico"


def _spn_entry(spn: int) -> dict | None:
    e = spn_table().get(str(spn))
    if e and e.get("familia") == "inyector":
        e = {**e, **INJECTOR}
    return e


def enrich_dtc(dtc: Dtc, brand: str = "generico", labour_rate: float = LABOUR_RATE_EUR_H,
               lamps: dict | None = None) -> dict:
    fmi = fmi_table().get(str(dtc.fmi), {"texto": f"FMI {dtc.fmi} reservado/no estándar", "tipo": "condicion", "gravedad": 3})
    entry = _spn_entry(dtc.spn)
    electrical = fmi["tipo"] in ("electrico", "componente", "red")
    proprietary = 520192 <= dtc.spn <= 524287

    if entry:
        branch = entry["electrico" if electrical else "condicion"]
        name, system, known = entry["nombre"], entry["sistema"], True
        critical = entry.get("critico", False) and not electrical
    else:
        branch = {"piezas": [], "dificultad": 3, "horas_mo": 2}
        name = (f"SPN propietario del fabricante ({dtc.spn})" if proprietary
                else f"Parámetro SPN {dtc.spn} (no catalogado todavía)")
        system, known, critical = "Desconocido", False, False

    if electrical:
        steps = ELECTRICAL_STEPS.get(str(dtc.fmi), GENERIC_ELECTRICAL_STEPS)
        causes = ["Fallo de circuito: cableado, conector o el propio sensor/actuador"]
    else:
        steps = branch.get("pasos", ["Consultar el manual de servicio del fabricante para este código"])
        causes = branch.get("causas", [])
    if not known:
        steps = steps + ["Código no incluido en la base: consultar documentación oficial y añadirlo a la base tras la reparación"]

    parts = branch.get("piezas", [])
    labour_h = float(branch.get("horas_mo", 1))
    parts_min = sum(p["min"] for p in parts)
    parts_max = max([p["max"] for p in parts], default=0)  # normalmente se cambia la pieza más probable, no todas
    severity = fmi["gravedad"]
    if critical:
        severity = 5
    if lamps and lamps.get("red_stop"):
        severity = max(severity, 4)
    elif lamps and lamps.get("amber_warning"):
        severity = max(severity, 3)

    b = brands().get(brand, brands()["generico"])
    return {
        "code": dtc.code, "spn": dtc.spn, "fmi": dtc.fmi,
        "active": dtc.active, "occurrences": dtc.occurrences,
        "source": dtc.source, "source_name": source_name(dtc.source),
        "name": name, "system": system, "fmi_text": fmi["texto"], "fault_type": fmi["tipo"],
        "severity": int(min(5, max(1, severity))), "critical": critical,
        "warning": branch.get("aviso") if not electrical else None,
        "causes": causes, "steps": steps,
        "parts": parts,
        "difficulty": int(branch.get("dificultad", 3)),
        "labour_hours": labour_h,
        "cost_min_eur": round(min([p["min"] for p in parts], default=0) + labour_h * labour_rate * 0.7),
        "cost_max_eur": round(max(parts_max, parts_min) + labour_h * labour_rate * 1.3),
        "known": known, "proprietary": proprietary,
        "brand_note": b["notas"],
    }
