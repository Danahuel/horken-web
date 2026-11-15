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

log = logging.getLogger("horken.obd")

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

    dtcs = []
    for cmd, status in ((obd.commands.GET_DTC, 0x09), (obd.commands.GET_CURRENT_DTC, 0x04)):
        for code, _desc in (_val(conn.query(cmd)) or []):
            try:
                d = enrich_uds(_code_to_id(code), status | (0x80 if status == 0x09 else 0), "Motor / OBD-II",
                               state.labour_rate)
            except (ValueError, IndexError):
                continue
            d["code"] = code
            d["fmi_text"] = "Confirmada (modo 03)" if status == 0x09 else "Pendiente (modo 07)"
            d["protocol"] = "OBD-II"
            dtcs.append(d)
    state.set_dtcs(key, dtcs)

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
