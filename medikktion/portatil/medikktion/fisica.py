"""Modelo físico sencillo de un motor diésel con hidráulica, para que las
máquinas simuladas se comporten como las reales:

  * Ciclos de trabajo (cavar/girar/descargar) con pausas a ralentí.
  * Inercia térmica: el refrigerante tarda minutos en estabilizarse, el aceite
    hidráulico mucho más (decenas de minutos), así que sube de centésima en
    centésima, como un termómetro de verdad.
  * Presión de aceite que depende del régimen y de la temperatura del aceite
    (aceite frío = más viscoso = más presión).
  * Consumo, sobrealimentación y par ligados a la carga.

No pretende ser un modelo de ingeniería exacto; sirve para pruebas y demostraciones.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class Perfil:
    rated_rpm: float = 1800          # régimen de trabajo
    idle_rpm: float = 850
    coolant_set: float = 88          # °C con termostato abierto, a carga media
    hyd_set: float = 72              # °C de equilibrio del aceite hidráulico
    oil_p_rated: float = 400         # kPa a régimen nominal y aceite caliente
    boost_max: float = 170           # kPa de sobrealimentación a plena carga
    fuel_idle: float = 3.0           # L/h a ralentí
    fuel_max: float = 26.0           # L/h a plena carga
    ambient: float = 12.0
    start_coolant: float = 60.0
    start_hyd: float = 50.0
    start_oil: float = 55.0
    tank_l: float = 400.0
    fuel_level: float = 70.0         # %
    def_level: float = 55.0          # %
    has_trans: bool = False
    cycle_s: float = 26.0            # duración de un ciclo de trabajo
    work_share: float = 0.82         # fracción del tiempo trabajando (resto, pausas)
    load_mean: float = 0.55
    seed: int = 7
    # Hidráulica (solo si la máquina tiene sensores de presión de bomba)
    relief_p1: float = 0.0           # bar de alivio que alcanza la bomba 1 (0 = sin sensores)
    relief_p2: float = 0.0
    standby_bar: float = 32.0
    pilot_bar: float = 40.0


@dataclass
class Motor:
    p: Perfil
    t: float = 0.0
    s: dict = field(default_factory=dict)

    def __post_init__(self):
        self.rnd = random.Random(self.p.seed)
        p = self.p
        self.s = {"rpm": p.idle_rpm, "load": 0.1, "coolant": p.start_coolant, "oil": p.start_oil,
                  "hyd": p.start_hyd, "trans": p.start_hyd + 5, "fuel_level": p.fuel_level,
                  "def_level": p.def_level, "battery": 27.6, "boost": 10.0}
        self._pause_until = 0.0
        self._next_pause = self.rnd.uniform(120, 260)
        self.operator: str | None = None   # lo que hace el operador en una prueba guiada
        self.s.update({"p1": p.standby_bar, "p2": p.standby_bar, "pilot": p.pilot_bar})

    # --- consigna de trabajo ------------------------------------------------
    def _targets(self):
        p = self.p
        if self.operator:                       # prueba guiada: motor alto, sin ciclos de trabajo
            return p.rated_rpm, 0.9 if self.operator.startswith("alivio") else 0.12
        if self.t >= self._next_pause:
            self._pause_until = self.t + self.rnd.uniform(25, 60) * (1 - p.work_share) / 0.18
            self._next_pause = self._pause_until + self.rnd.uniform(140, 300)
        if self.t < self._pause_until:
            return p.idle_rpm, 0.06
        phase = (self.t % p.cycle_s) / p.cycle_s
        # cavar (carga alta) → girar (media) → descargar (baja) → volver (media)
        shape = 0.95 if phase < 0.35 else 0.6 if phase < 0.6 else 0.3 if phase < 0.75 else 0.5
        load = min(1.0, max(0.05, p.load_mean * shape / 0.6 + self.rnd.gauss(0, 0.04)))
        return p.rated_rpm, load

    # --- un paso de simulación ---------------------------------------------
    def step(self, dt: float) -> dict:
        p, s, g = self.p, self.s, self.rnd.gauss
        self.t += dt
        rpm_t, load_t = self._targets()
        a = 1 - math.exp(-dt / 1.1)
        s["rpm"] += (rpm_t - load_t * 60 - s["rpm"]) * a + g(0, 3.0) * math.sqrt(dt)
        s["load"] += (load_t - s["load"]) * (1 - math.exp(-dt / 0.8))
        load, rpm = s["load"], s["rpm"]

        def toward(key, target, tau, noise):
            s[key] += (target - s[key]) * (1 - math.exp(-dt / tau)) + g(0, noise) * math.sqrt(dt)

        # Refrigerante: calienta con la carga hasta el termostato y allí se estabiliza
        thermo = p.coolant_set + (load - 0.5) * 5
        warm = s["coolant"] < p.coolant_set - 6
        toward("coolant", thermo + (25 if warm else 0) * load, 210 if warm else 140, 0.012)
        toward("oil", s["coolant"] + 3 + load * 7, 380, 0.010)
        toward("hyd", p.hyd_set + (load - 0.5) * 8, 1100, 0.006)
        if p.has_trans:
            toward("trans", p.hyd_set + 6 + load * 12, 700, 0.008)
        s["boost"] = max(0.0, 8 + load * p.boost_max * (rpm / p.rated_rpm) ** 1.2 + g(0, 1.2))
        visc = 1 + max(-0.15, (92 - s["oil"]) / 92 * 0.45)
        oil_p = p.oil_p_rated * (max(rpm, 300) / p.rated_rpm) ** 0.65 * visc + g(0, 2.5)
        fuel_rate = max(0.5, p.fuel_idle + load * p.fuel_max * (rpm / p.rated_rpm) + g(0, 0.15))
        s["fuel_level"] -= fuel_rate * dt / 3600 / p.tank_l * 100
        s["def_level"] -= fuel_rate * 0.045 * dt / 3600 / 60 * 100
        s["battery"] += (27.65 - s["battery"]) * (1 - math.exp(-dt / 30)) + g(0, 0.004) * math.sqrt(dt)
        out = {
            "rpm": round(rpm, 2), "torque_pct": round(load * 92 + 4, 1),
            "coolant_c": round(s["coolant"], 3), "oil_temp_c": round(s["oil"], 3),
            "hyd_oil_temp_c": round(s["hyd"], 3), "oil_pressure_kpa": round(oil_p, 2),
            "boost_kpa": round(s["boost"], 2), "fuel_rate_lh": round(fuel_rate, 2),
            "battery_v": round(s["battery"], 3), "fuel_level_pct": round(s["fuel_level"], 2),
            "def_level_pct": round(s["def_level"], 2), "ambient_c": round(p.ambient + g(0, 0.05), 2),
            "intake_temp_c": round(p.ambient + 28 + load * 14 + g(0, 0.2), 2),
        }
        if p.has_trans:
            out["trans_oil_temp_c"] = round(s["trans"], 3)
        if p.relief_p1:
            out.update(self._hydraulics(dt, load))
        return out

    def _hydraulics(self, dt: float, load: float) -> dict:
        """Presiones de bomba: reposo, trabajo y picos contra tope (válvula de alivio)."""
        p, s, g = self.p, self.s, self.rnd.gauss
        op = self.operator
        sb = p.standby_bar
        if op in ("reposo", "pilotaje"):
            t1 = t2 = sb
        elif op == "alivio_p1":
            t1, t2 = p.relief_p1, sb
        elif op == "alivio_p2":
            t1, t2 = sb, p.relief_p2
        elif self.t < self._pause_until:
            t1 = t2 = sb
        else:
            phase = (self.t % p.cycle_s) / p.cycle_s
            t1 = sb + load * 0.72 * p.relief_p1
            t2 = sb + load * 0.55 * p.relief_p2
            if 0.29 < phase < 0.34:              # cazo contra tope al final de cada pasada
                t1 = p.relief_p1
        a = 1 - math.exp(-dt / 0.25)
        for k, tgt, ok in (("p1", t1, p.relief_p1), ("p2", t2, p.relief_p2)):
            s[k] += (tgt - s[k]) * a + g(0, 1.4)
            s[k] = min(s[k], ok + 2.5)            # la válvula de alivio no deja pasar de ahí
        s["pilot"] += (p.pilot_bar - s["pilot"]) * a + g(0, 0.25)
        return {"pump1_bar": round(max(0.0, s["p1"]), 1), "pump2_bar": round(max(0.0, s["p2"]), 1),
                "pilot_bar": round(s["pilot"], 2)}
