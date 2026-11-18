"""Coches, furgonetas y camiones ligeros: OBD-II con un ELM327 (USB o Bluetooth)
usando la biblioteca python-OBD (2.000+ códigos SAE genéricos).

Además de averías y datos en vivo, busca señales de venta "maquillada":
  * Averías borradas hace poco (pocos km / pocos arranques desde el borrado).
  * Km de la centralita de motor (PID A6, coches desde ~2019) frente a los
    km del cuadro que introduce el usuario.
"""
from __future__ import annotations

import logging
import time

from . import kb
from .uds import enrich_uds

log = logging.getLogger("medikktion.obd")

LIVE = {  # comando python-OBD → (clave, etiqueta, unidad)
    "RPM": ("rpm", "Régimen motor", "rpm"),
    "SPEED": ("speed_kmh", "Velocidad", "km/h"),
    "COOLANT_TEMP": ("coolant_c", "Temperatura refrigerante", "°C"),
    "ENGINE_LOAD": ("load_pct", "Carga del motor", "%"),
    "CONTROL_MODULE_VOLTAGE": ("battery_v", "Tensión centralita", "V"),
    "FUEL_LEVEL": ("fuel_level_pct", "Nivel combustible", "%"),
    "INTAKE_PRESSURE": ("boost_kpa", "Presión colector admisión", "kPa"),
    "INTAKE_TEMP": ("intake_temp_c", "Temperatura admisión", "°C"),
    "OIL_TEMP": ("oil_temp_c", "Temperatura aceite motor", "°C"),
    "FUEL_RATE": ("fuel_rate_lh", "Consumo instantáneo", "L/h"),
    "THROTTLE_POS": ("throttle_pct", "Posición acelerador", "%"),
}


def _odometer_command():
    import obd
    from obd.protocols import ECU

    def dec(messages):
        d = messages[0].data[2:]
        return int.from_bytes(d[:4], "big") / 10 if len(d) >= 4 else None
    return obd.OBDCommand("ODOMETER", "Odómetro", b"01A6", 6, dec, ECU.ENGINE, True)


def _custom(name: str, cmd: bytes, decoder):
    import obd
    from obd.protocols import ECU
    return obd.OBDCommand(name, name, cmd, 0, decoder, ECU.ALL, False)


def _ff(fn):
    """Decodificador de modo 02 (imagen congelada): datos = [0x42, PID, nº de imagen, A, B...]."""
    def dec(messages):
        d = messages[0].data
        return fn(d[3:]) if len(d) > 3 else None
    return dec


FREEZE = {  # PID de imagen congelada → (clave, decodificador)
    "rpm": (b"020C00", _ff(lambda d: (d[0] * 256 + d[1]) / 4 if len(d) > 1 else None)),
    "coolant_c": (b"020500", _ff(lambda d: d[0] - 40)),
    "load_pct": (b"020400", _ff(lambda d: round(d[0] * 100 / 255))),
    "speed_kmh": (b"020D00", _ff(lambda d: d[0])),
}


def _val(r):
    if r is None or r.is_null():
        return None
    v = r.value
    return float(v.magnitude) if hasattr(v, "magnitude") else v


def _code_to_id(code: str) -> int:
    """'P0118' → 0x011800 (sin byte de tipo de fallo)."""
    letter = "PCBU".index(code[0])
    b1 = (letter << 6) | (int(code[1]) << 4) | int(code[2], 16)
    return (b1 << 16) | (int(code[3:5], 16) << 8)


def read_car(conn, state, cluster_km: float | None = None, samples: int = 3) -> None:
    """Lee un vehículo OBD-II y vuelca en el MachineState. ``conn`` es un obd.OBD."""
    import obd
    key = "OBD-II"
    info = {}
    vin = _val(conn.query(obd.commands.VIN)) if conn.supports(obd.commands.VIN) else None
    if isinstance(vin, (bytes, bytearray)):
        vin = vin.decode(errors="replace")
    cal = _val(conn.query(obd.commands.CALIBRATION_ID)) if conn.supports(obd.commands.CALIBRATION_ID) else None
    cvn = _val(conn.query(obd.commands.CVN)) if conn.supports(obd.commands.CVN) else None
    if cal:
        info["calibrations"] = [{"cal_id": str(cal).strip(), "cvn": str(cvn or "").strip()}]
    state.add_ecu(key, "Motor / OBD-II", "OBD-II", vin=(vin or "").strip() or None,
                  component={"make": "", "model": "", "serial": (vin or "").strip(), "unit": ""}, **info)

    dtcs, seen = [], {}
    try:
        permanent_cmd = _custom("PERMANENT_DTC", b"0A", obd.decoders.dtc)
    except Exception:  # noqa: BLE001
        permanent_cmd = None
    sources = [(obd.commands.GET_DTC, 0x09, "active", "Confirmada (modo 03)"),
               (obd.commands.GET_CURRENT_DTC, 0x04, "pending", "Pendiente (modo 07)")]
    if permanent_cmd is not None:
        sources.append((permanent_cmd, 0x08, "permanent", "Permanente (modo 0A): no se borra hasta repararla"))
    for cmd, status, kind, txt in sources:
        try:
            r = conn.query(cmd, force=True) if cmd is permanent_cmd else conn.query(cmd)
        except Exception:  # noqa: BLE001
            continue
        for code, _desc in (_val(r) or []):
            if code in seen:
                seen[code]["kinds"].append(kind)
                continue
            try:
                d = enrich_uds(_code_to_id(code), status | (0x80 if kind == "active" else 0), "Motor / OBD-II",
                               state.labour_rate)
            except (ValueError, IndexError):
                continue
            d.update({"code": code, "fmi_text": txt, "protocol": "OBD-II", "kind": kind, "kinds": [kind],
                      "active": kind == "active"})
            seen[code] = d
            dtcs.append(d)
    # Imagen congelada: condiciones cuando saltó la avería que la provocó
    ff_code = _val(conn.query(obd.commands.FREEZE_DTC)) if conn.supports(obd.commands.FREEZE_DTC) else None
    if isinstance(ff_code, (list, tuple)) and ff_code and isinstance(ff_code[0], str):
        ff_code = ff_code[0]
    if isinstance(ff_code, str) and ff_code in seen:
        fr = {}
        for k, (raw, dec) in FREEZE.items():
            try:
                v = _val(conn.query(_custom(f"FF_{k}", raw, dec), force=True))
            except Exception:  # noqa: BLE001
                v = None
            if isinstance(v, (int, float)):
                fr[k] = v
        if fr:
            seen[ff_code]["freeze"] = fr
    state.set_dtcs(key, dtcs)
    perm_only = [c for c, d in seen.items() if d["kinds"] == ["permanent"]]

    # Señales de borrado reciente / km
    evidence = []
    dist_clear = _val(conn.query(obd.commands.DISTANCE_SINCE_DTC_CLEAR))
    warm_clear = _val(conn.query(obd.commands.WARMUPS_SINCE_DTC_CLEAR))
    if dist_clear is not None and warm_clear is not None:
        if dist_clear < 100 or warm_clear < 10:
            evidence.append({"title": "Averías borradas recientemente",
                             "detail": f"Solo {dist_clear:.0f} km y {warm_clear:.0f} arranques en caliente desde el último "
                                       "borrado de códigos. Típico para ocultar averías antes de vender: "
                                       "conducir 50-100 km y volver a leer.", "weight": 30, "level": "alta"})
        else:
            evidence.append({"title": "Sin borrado reciente de averías",
                             "detail": f"{dist_clear:.0f} km desde el último borrado.", "weight": 0, "level": "ok"})
    try:
        odo = _val(conn.query(_odometer_command(), force=True))
    except Exception:  # noqa: BLE001
        odo = None
    if odo:
        state.add_ecu(key, "Motor / OBD-II", "OBD-II", total_km=odo)
        if cluster_km:
            diff = abs(odo - cluster_km)
            if diff > max(50, odo * 0.01):
                evidence.append({"title": "Km del cuadro distintos a los de la centralita de motor",
                                 "detail": f"Cuadro: {cluster_km:,.0f} km · centralita de motor: {odo:,.0f} km.",
                                 "weight": 60, "level": "alta"})
            else:
                evidence.append({"title": "Km coherentes cuadro / motor", "detail": f"{odo:,.0f} km.", "weight": 0, "level": "ok"})
    if perm_only:
        evidence.append({"title": "Averías permanentes que alguien borró",
                         "detail": f"{', '.join(perm_only)}: la centralita las guarda como permanentes aunque ya no estén "
                                   "activas. Se borraron sin reparar.", "weight": 30, "level": "alta"})
    state.extra_evidence = evidence

    for _ in range(samples):
        vals = {}
        for cmd_name, (k, label, unit) in LIVE.items():
            cmd = obd.commands[cmd_name]
            if conn.supports(cmd):
                v = _val(conn.query(cmd))
                if isinstance(v, (int, float)):
                    vals[k] = (round(v, 2), label, unit)
        now = time.time()
        with state.lock:
            for k, (v, label, unit) in vals.items():
                state.live[k] = {"value": v, "unit": unit, "label": label, "source": key, "t": now}
        time.sleep(0.2)
