"""Mantenimiento por horas e informe de compra.

El informe de compra responde a lo que pregunta quien compra una máquina usada:
  * ¿Cuánto cuesta dejarla a punto? (averías activas, permanentes, pendientes y
    el servicio de entrada que hay que hacer siempre al comprar).
  * ¿Cuántas horas tiene de verdad? y ¿cuánto valen las horas ocultas?
  * ¿Cuánto hay que rebajar del precio que piden?
Siempre redondeando al alza.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from .pricing import PARTS_MARGIN, Pricing, _round_up

_KB = Path(__file__).parent / "kb" / "mantenimiento.json"


@lru_cache
def _data() -> dict:
    return json.loads(_KB.read_text(encoding="utf-8"))


def _applies(item: dict, machine_class: str, has_scr: bool) -> bool:
    c = item["clases"]
    if c == "todas_menos_coche":
        return machine_class != "coche"
    if c == "con_scr":
        return has_scr and machine_class != "coche"
    return machine_class in _data()["grupos"].get(c, [])


def maintenance(hours: float | None, machine_class: str, pricing: Pricing, has_scr: bool = False) -> dict:
    """Plan de mantenimiento según las horas (reales estimadas si el horómetro está alterado)."""
    if not hours:
        return {"hours_basis": None, "items": [], "entry": {"items": [], "cost_min_eur": 0, "cost_max_eur": 0}}
    items, entry = [], []
    for it in _data()["items"]:
        if not _applies(it, machine_class, has_scr):
            continue
        n_done = math.floor(hours / it["cada"])
        next_due = (n_done + 1) * it["cada"]
        remaining = next_due - hours
        c = pricing.fault([{"min": it["min"], "max": it["max"]}], it["horas"])
        row = {"id": it["id"], "name": it["nombre"], "every_h": it["cada"], "times_due": n_done,
               "next_due_h": next_due, "remaining_h": round(remaining), "cost_min_eur": c["cost_min_eur"],
               "cost_max_eur": c["cost_max_eur"], "soon": remaining <= max(100, it["cada"] * 0.2)}
        items.append(row)
        # Servicio de entrada al comprar: lo básico siempre + lo que vence pronto
        if it["compra"] or row["soon"]:
            entry.append(row)
    items.sort(key=lambda r: r["remaining_h"])
    return {"hours_basis": round(hours), "items": items,
            "entry": {"items": [r["name"] for r in entry],
                      "cost_min_eur": sum(r["cost_min_eur"] for r in entry),
                      "cost_max_eur": sum(r["cost_max_eur"] for r in entry)}}


def purchase_report(dtcs: list[dict], tamper: dict, health: dict, usage: dict, maint: dict, pricing: Pricing,
                    machine_class: str, asking_price: float | None = None) -> dict:
    """Coste para dejarla a punto, valor de las horas ocultas y rebaja recomendada."""
    active = [d for d in dtcs if d.get("active")]
    permanent = [d for d in dtcs if d.get("kind") == "permanent"]   # volverán a salir: cuentan como activas
    pending = [d for d in dtcs if d.get("kind") == "pending"]
    visit = pricing.visit()["eur"] if (active or permanent or pending) else 0

    def s(lst, k):
        return sum(d[k] for d in lst)

    rep_min = s(active, "cost_min_eur") + s(permanent, "cost_min_eur")
    rep_max = s(active, "cost_max_eur") + s(permanent, "cost_max_eur")
    pend_max = s(pending, "cost_max_eur")         # riesgo: aún no han dado la cara
    entry = maint.get("entry", {})
    ready_min = rep_min + entry.get("cost_min_eur", 0) + visit
    ready_max = rep_max + pend_max + entry.get("cost_max_eur", 0) + visit

    dep = _data()["depreciacion_eur_h"].get(machine_class, 10)
    reported, real = tamper.get("reported_hours"), tamper.get("estimated_real_hours")
    hidden = max(0.0, (real or 0) - (reported or 0)) if tamper.get("verdict") == "manipulado" else 0.0
    hidden_value = _round_up(hidden * dep, 100)
    suspicion_value = _round_up((reported or 0) * 0.15 * dep, 100) if tamper.get("verdict") == "sospechoso" else 0

    discount = _round_up(ready_max + hidden_value + suspicion_value, 100)
    h = health.get("score", 0)
    if tamper.get("verdict") == "manipulado" or h < 40:
        verdict, label = "no_comprar", "No comprar sin una inspección a fondo en taller"
    elif h < 70 or tamper.get("verdict") == "sospechoso" or rep_max > 5000:
        verdict, label = "negociar", "Negociar el precio con este informe"
    else:
        verdict, label = "comprar", "Compra razonable"
    out = {
        "verdict": verdict, "label": label,
        "repairs_min_eur": rep_min, "repairs_max_eur": rep_max, "pending_risk_eur": pend_max,
        "entry_service_min_eur": entry.get("cost_min_eur", 0), "entry_service_max_eur": entry.get("cost_max_eur", 0),
        "visit_eur": visit, "ready_min_eur": _round_up(ready_min, 100), "ready_max_eur": _round_up(ready_max, 100),
        "hidden_hours": round(hidden), "eur_per_hour": dep, "hidden_hours_value_eur": hidden_value,
        "suspicion_value_eur": suspicion_value, "recommended_discount_eur": discount,
        "counts": {"active": len(active), "permanent": len(permanent), "pending": len(pending)},
        "parts_margin": PARTS_MARGIN,
    }
    if asking_price:
        offer = asking_price - discount
        out.update({"asking_price_eur": asking_price, "max_offer_eur": _round_up(max(0, offer), 100),
                    "discount_pct": round(min(discount / asking_price, 1) * 100, 1),
                    "overpriced": offer <= 0})
        if offer <= 0:
            out["label"] = "No compensa: reparaciones y horas ocultas superan el precio que piden"
    return out
