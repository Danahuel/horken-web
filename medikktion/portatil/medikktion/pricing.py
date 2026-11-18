"""Precios de reparación. Criterio: mejor pasarse que quedarse corto.

* Mano de obra por país (servicio móvil de maquinaria): España 75 €/h como
  mínimo, Alemania 120 €/h. En config.json se puede subir, nunca bajar del mínimo.
* Margen sobre piezas (+15 %) y sobre horas (+25 %) para imprevistos: tornillería,
  juntas, fluidos, una pieza que se rompe al desmontar...
* Máquinas grandes: más horas (accesos, pesos, grúa).
* Cada visita suma desplazamiento (km ida y vuelta + tiempo de viaje) y 1 h de diagnóstico.
* Si hay reparaciones reales registradas para esa avería, mandan los costes reales.
"""
from __future__ import annotations

from dataclasses import dataclass, field

COUNTRIES = {
    "ES": {"name": "España", "rate": 75.0, "eur_km": 1.0},
    "DE": {"name": "Alemania", "rate": 120.0, "eur_km": 1.5},
}
PARTS_MARGIN = 1.15
HOURS_MARGIN = 1.25
DIAGNOSIS_H = 1.0
TRAVEL_KMH = 70.0
SIZE_FACTOR = {  # horas de mano de obra según el tamaño de la máquina
    "excavadora_grande": 1.25, "bulldozer": 1.3, "manipuladora": 1.2, "trituradora": 1.2,
    "dumper_articulado": 1.2, "cargadora_ruedas": 1.15, "excavadora_20t": 1.0, "rodillo": 1.0,
    "camion": 1.0, "retro_mixta": 0.9, "minicargadora": 0.85, "coche": 0.8, "generica": 1.1,
}


@dataclass
class Pricing:
    country: str = "ES"
    rate: float = COUNTRIES["ES"]["rate"]
    eur_km: float = COUNTRIES["ES"]["eur_km"]
    travel_km: float = 0.0           # km de ida hasta la máquina
    machine_class: str = "generica"
    real_costs: dict = field(default_factory=dict)  # código → [costes reales de reparaciones registradas]

    @classmethod
    def from_config(cls, cfg: dict, machine_class: str = "generica", travel_km: float = 0.0,
                    real_costs: dict | None = None) -> "Pricing":
        c = (cfg.get("pais") or "ES").upper()
        base = COUNTRIES.get(c, COUNTRIES["ES"])
        rate = max(float(cfg.get("labour_rate") or 0), base["rate"])  # nunca por debajo del mínimo del país
        return cls(country=c if c in COUNTRIES else "ES", rate=rate,
                   eur_km=max(float(cfg.get("eur_km") or 0), base["eur_km"]),
                   travel_km=float(travel_km or 0), machine_class=machine_class, real_costs=real_costs or {})

    @property
    def size(self) -> float:
        return SIZE_FACTOR.get(self.machine_class, 1.1)

    def labour_hours(self, base_h: float) -> float:
        return round(base_h * HOURS_MARGIN * self.size, 1)

    def fault(self, parts: list[dict], base_h: float, code: str | None = None) -> dict:
        """Coste de una avería: con recambio alternativo y con original."""
        h = self.labour_hours(base_h)
        labour = h * self.rate
        if parts:
            alt = min(p["min"] for p in parts) * PARTS_MARGIN
            oem = max(p["max"] for p in parts) * PARTS_MARGIN
        else:
            alt = oem = 0.0
        out = {"labour_hours": h, "labour_eur": round(labour), "rate": self.rate,
               "cost_min_eur": _round_up(alt + labour), "cost_max_eur": _round_up(oem + labour),
               "price_source": "estimación"}
        real = self.real_costs.get(code or "") or []
        if real:
            lo, hi = min(real), max(real)
            out.update({"cost_min_eur": _round_up(max(out["cost_min_eur"], lo)),
                        "cost_max_eur": _round_up(max(out["cost_max_eur"], hi * 1.1)),
                        "price_source": f"{len(real)} reparación(es) real(es)"})
        return out

    def visit(self) -> dict:
        """Lo que cuesta ir a la máquina: desplazamiento y diagnóstico."""
        km = self.travel_km * 2
        travel_h = km / TRAVEL_KMH
        eur = km * self.eur_km + (travel_h + DIAGNOSIS_H) * self.rate
        return {"km_round_trip": round(km), "travel_hours": round(travel_h, 1), "diagnosis_hours": DIAGNOSIS_H,
                "eur": _round_up(eur), "rate": self.rate, "eur_km": self.eur_km}

    def describe(self) -> dict:
        return {"country": self.country, "country_name": COUNTRIES[self.country]["name"], "rate": self.rate,
                "eur_km": self.eur_km, "travel_km": self.travel_km, "parts_margin": PARTS_MARGIN,
                "hours_margin": HOURS_MARGIN, "size_factor": self.size, "visit": self.visit()}


def _round_up(v: float, step: int = 10) -> int:
    """Redondea hacia arriba a la decena: un presupuesto nunca se queda corto por céntimos."""
    import math
    return int(math.ceil(v / step) * step)
