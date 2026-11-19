"""Candado de solo lectura.

Todo lo que el programa envía a la máquina pasa por aquí. Solo deja salir
PREGUNTAS (peticiones de lectura); cualquier otra trama se bloquea y no llega
al bus, aunque un fallo de programación intentara mandarla.

Permitido:
- J1939: petición de PGN (59904) solo de la lista de lecturas; confirmaciones
  del protocolo de transporte (CTS, fin de mensaje, cancelar) para recibir
  mensajes largos.
- UDS: TesterPresent (0x3E), leer averías (0x19) y leer datos (0x22), en una sola
  trama; y las tramas de control de flujo para recibir respuestas largas.

Bloqueado, entre otros: borrar averías (DM3, DM11, UDS 0x14), escribir datos
(0x2E), rutinas (0x31), cambio de sesión (0x10), acceso de seguridad (0x27),
reinicio (0x11), programación (0x34-0x37) y cualquier PGN no previsto.
"""
from __future__ import annotations

import logging

import can

from . import j1939

log = logging.getLogger(__name__)

READ_PGNS = frozenset(j1939.ON_REQUEST_PGNS) | {j1939.PGN_DM1}
UDS_READ_SERVICES = frozenset({0x3E, 0x19, 0x22})
TP_RECEIVE_CONTROL = frozenset({17, 19, 255})   # CTS, EndOfMsgAck, Abort
PGN_TP_CM = 0xEC00


class BlockedFrame(Exception):
    pass


def _uds_payload_ok(data: bytes) -> bool:
    if not data:
        return False
    kind = data[0] >> 4
    if kind == 3:                       # control de flujo: pedir el resto de una respuesta
        return True
    if kind == 0:                       # trama única: [longitud, servicio, ...]
        return len(data) >= 2 and data[1] in UDS_READ_SERVICES
    return False                        # el programa nunca envía peticiones largas


def check(msg: can.Message) -> None:
    """Lanza BlockedFrame si la trama no es una lectura permitida."""
    arb, data = msg.arbitration_id, bytes(msg.data)
    if not msg.is_extended_id:
        if arb == 0x7DF or 0x7E0 <= arb <= 0x7E7:
            if _uds_payload_ok(data):
                return
        raise BlockedFrame(f"trama 11 bits 0x{arb:03X} {data.hex()}")
    pf = (arb >> 16) & 0xFF
    if pf in (0xDA, 0xDB):              # UDS sobre 29 bits
        if _uds_payload_ok(data):
            return
        raise BlockedFrame(f"UDS 0x{arb:08X} {data.hex()}")
    if pf == 0xEA:                      # petición J1939
        pgn = int.from_bytes(data[:3].ljust(3, b"\0"), "little")
        if len(data) == 3 and pgn in READ_PGNS:
            return
        raise BlockedFrame(f"petición del PGN {pgn}")
    if pf == 0xEC and data and data[0] in TP_RECEIVE_CONTROL:
        return
    raise BlockedFrame(f"trama 0x{arb:08X} {data.hex()}")


def guard(bus: can.BusABC) -> can.BusABC:
    """Pone el candado al bus: a partir de aquí solo salen lecturas."""
    if getattr(bus, "_medikktion_guarded", False):
        return bus
    raw_send = bus.send

    def safe_send(msg: can.Message, timeout: float | None = None) -> None:
        try:
            check(msg)
        except BlockedFrame as e:
            log.error("BLOQUEADO (solo lectura): %s", e)
            raise can.CanError(f"Bloqueado por el modo solo lectura: {e}") from None
        raw_send(msg, timeout)

    bus.send = safe_send            # type: ignore[method-assign]
    bus._medikktion_guarded = True  # type: ignore[attr-defined]
    return bus
