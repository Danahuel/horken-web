"""Grabación y reproducción de tramas CAN.

Graba TODO lo que circula por el bus en formato BLF (Vector Binary Logging
Format, comprimido): se abre con python-can, Vector CANalyzer/CANoe, BusMaster
y muchas otras herramientas. Sirve para:
  * Diagnosticar fallos del propio programa con una máquina real: la grabación
    se reproduce después como si la máquina estuviera conectada.
  * Guardar la "huella" de una máquina para compararla más adelante.

Unos 5-10 MB por hora de lectura. Se activa con --grabar o desde la app.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import can

log = logging.getLogger("medikktion.recorder")


class Recorder(can.Listener):
    """Se cuelga del Notifier de la sesión: no interfiere con la lectura."""

    def __init__(self, folder: str | Path, session_id: str):
        self.folder = Path(folder) / "grabaciones"
        self.session_id = session_id
        self._writer: can.BLFWriter | None = None
        self._lock = threading.Lock()
        self.path: Path | None = None
        self.frames = 0
        self.started: float | None = None
        self._notifier: can.Notifier | None = None

    @property
    def active(self) -> bool:
        return self._writer is not None

    def start(self, notifier: can.Notifier) -> Path:
        with self._lock:
            if self._writer:
                return self.path
            self.folder.mkdir(parents=True, exist_ok=True)
            n = len(list(self.folder.glob(f"{self.session_id}*.blf")))
            self.path = self.folder / f"{self.session_id}{f'-{n + 1}' if n else ''}.blf"
            self._writer = can.BLFWriter(str(self.path))
            self.frames, self.started = 0, time.time()
            self._notifier = notifier
        notifier.add_listener(self)
        log.info("Grabando en %s", self.path)
        return self.path

    def stop(self) -> Path | None:
        with self._lock:
            w, self._writer = self._writer, None
            if self._notifier:
                try:
                    self._notifier.remove_listener(self)
                except ValueError:
                    pass
        if w:
            w.stop()
        return self.path

    def on_message_received(self, msg: can.Message) -> None:
        with self._lock:
            if not self._writer:
                return
            if len(msg.data) > 8:  # modo J1939 del lector: mensajes ya reensamblados
                if len(msg.data) > 64:
                    return
                msg = can.Message(timestamp=msg.timestamp, arbitration_id=msg.arbitration_id, is_extended_id=True,
                                  data=msg.data, is_fd=True, channel=msg.channel)
            self._writer.on_message_received(msg)
            self.frames += 1

    def status(self) -> dict:
        size = self.path.stat().st_size if self.path and self.path.exists() else 0
        return {
            "active": self.active,
            "file": self.path.name if self.path else None,
            "frames": self.frames,
            "mb": round(size / 1024 / 1024, 2),
            "since": datetime.fromtimestamp(self.started, timezone.utc).isoformat() if self.started else None,
        }


def replay(path: str | Path, bus: can.BusABC, speed: float = 1.0, stop: threading.Event | None = None) -> int:
    """Envía al bus las tramas grabadas respetando sus tiempos (``speed`` 2 = el doble de rápido)."""
    sent, t_first, t0 = 0, None, time.time()
    for msg in can.LogReader(str(path)):
        if stop is not None and stop.is_set():
            break
        if t_first is None:
            t_first = msg.timestamp
        wait = (msg.timestamp - t_first) / max(speed, 0.01) - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)
        try:
            bus.send(can.Message(arbitration_id=msg.arbitration_id, data=msg.data, is_extended_id=msg.is_extended_id,
                                 is_fd=msg.is_fd, check=False))
            sent += 1
        except can.CanError:
            continue
    return sent


def duration(path: str | Path) -> float:
    first = last = None
    for msg in can.LogReader(str(path)):
        first = msg.timestamp if first is None else first
        last = msg.timestamp
    return (last - first) if first is not None else 0.0
