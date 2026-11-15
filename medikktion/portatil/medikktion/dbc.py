"""Archivos DBC (cantools): si consigues el DBC de una marca o modelo (de un
concesionario, de un proyecto abierto o creado a mano), sus mensajes
propietarios se decodifican y aparecen en "En vivo" sin tocar código.

  python -m medikktion leer ... --dbc fuchs_mhl.dbc
"""
from __future__ import annotations

from pathlib import Path

import cantools

from .j1939 import J1939Id


class DbcDecoder:
    def __init__(self, *paths: str | Path):
        self.by_pgn: dict[int, object] = {}
        for p in paths:
            db = cantools.database.load_file(str(p), strict=False)
            for m in db.messages:
                if m.is_extended_frame:
                    self.by_pgn[J1939Id.parse(m.frame_id).pgn] = m

    def __len__(self):
        return len(self.by_pgn)

    def decode(self, pgn: int, data: bytes):
        m = self.by_pgn.get(pgn)
        if m is None:
            return None, {}
        values = m.decode(bytes(data[:m.length]).ljust(m.length, b"\xff"), decode_choices=False)
        units = {s.name: s.unit for s in m.signals}
        return m.name, {k: (v, units.get(k)) for k, v in values.items()}
