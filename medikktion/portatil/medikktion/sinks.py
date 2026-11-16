"""Destino de los datos: Firebase Firestore (tiempo real a los móviles) o archivo local."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .analysis import fingerprint

log = logging.getLogger("medikktion.sink")


class LocalSink:
    def __init__(self, folder: str | Path = "sesiones"):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def open_session(self, session_id: str, meta: dict) -> None:
        self.path = self.folder / f"{session_id}.json"
        self.meta = meta

    def publish(self, snapshot: dict) -> None:
        self.path.write_text(json.dumps({**self.meta, **snapshot}, ensure_ascii=False, indent=2), encoding="utf-8")

    def close(self, snapshot: dict) -> None:
        self.publish({**snapshot, "status": "finished"})

    def watch_report_requests(self, cb: Callable[[list[str]], None]) -> None:
        pass  # sin app no hay peticiones remotas

    def report_done(self, to: list[str], ok: bool, error: str | None = None) -> None:
        log.info("Informe %s a %s", "enviado" if ok else f"fallido ({error})", to)

    def machine_history(self, serial: str) -> tuple[list[dict], dict | None]:
        hist, sw = [], None
        for f in sorted(self.folder.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("machine", {}).get("serial") == serial and d.get("tamper", {}).get("reported_hours"):
                hist.append({"date": d.get("updated_at", "")[:10], "engine_hours": d["tamper"]["reported_hours"]})
                sw = {str(e["address"]): fingerprint(e) for e in d.get("ecus", [])}
        return hist, sw


class FirestoreSink:
    """Colección ``sessions``: un documento por diagnóstico, actualizado en vivo.

    La app Flutter escucha el documento, así en Alemania y en España se ve lo
    mismo a la vez. Para pedir el informe por email la app escribe
    ``report_request`` y este programa lo envía y responde en ``report_status``.
    """

    def __init__(self, credentials_path: str):
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(credentials_path))
        self.fs = firestore
        self.db = firestore.client()
        self._watch = None

    TIMEOUT = 10  # s: sin conexión no se espera más; ResilientSink reintenta

    def _created(self, meta: dict):
        """created_at = inicio real de la sesión (aunque se suba horas después)."""
        try:
            return datetime.fromisoformat(meta["started_at"])
        except (KeyError, ValueError, TypeError):
            return self.fs.SERVER_TIMESTAMP

    def open_session(self, session_id: str, meta: dict) -> None:
        self.ref = self.db.collection("sessions").document(session_id)
        self.ref.set({**meta, "status": "live", "created_at": self._created(meta)}, merge=True, timeout=self.TIMEOUT)

    def publish(self, snapshot: dict) -> None:
        self.ref.set({**snapshot, "server_updated_at": self.fs.SERVER_TIMESTAMP}, merge=True, timeout=self.TIMEOUT)

    def close(self, snapshot: dict) -> None:
        self.publish({**snapshot, "status": "finished"})
        if self._watch:
            self._watch.unsubscribe()

    def upload_finished(self, session_id: str, data: dict) -> None:
        """Sube de una vez una sesión que terminó sin conexión."""
        ref = self.db.collection("sessions").document(session_id)
        ref.set({**data, "status": "finished", "created_at": self._created(data),
                 "server_updated_at": self.fs.SERVER_TIMESTAMP}, merge=True, timeout=self.TIMEOUT)

    def watch_report_requests(self, cb: Callable[[list[str]], None]) -> None:
        lock = threading.Lock()

        def on_snap(docs, _changes, _ts):
            for doc in docs:
                req = (doc.to_dict() or {}).get("report_request")
                if req and req.get("pending"):
                    with lock:
                        self.ref.update({"report_request.pending": False})
                        threading.Thread(target=cb, args=(req.get("recipients", []),), daemon=True).start()
        self._watch = self.ref.on_snapshot(on_snap)

    def report_done(self, to: list[str], ok: bool, error: str | None = None) -> None:
        self.ref.update({"report_status": {"ok": ok, "to": to, "error": error, "at": self.fs.SERVER_TIMESTAMP}})

    def machine_history(self, serial: str) -> tuple[list[dict], dict | None]:
        if not serial:
            return [], None
        q = self.db.collection("sessions").where("machine.serial", "==", serial).stream()
        hist, sw = [], None
        for d in q:
            x = d.to_dict()
            h = x.get("tamper", {}).get("reported_hours")
            if h:
                hist.append({"date": str(x.get("updated_at", ""))[:10], "engine_hours": h})
                sw = {str(e["address"]): fingerprint(e) for e in x.get("ecus", [])}
        return hist, sw


class ResilientSink:
    """Envuelve a FirestoreSink para que un corte de internet no pierda nada.

    * La lectura nunca espera a la red: el último estado se deja en una "bandeja"
      y un hilo aparte lo sube; si falla, reintenta con esperas crecientes.
    * Cada pocos segundos se guarda una copia en el disco del portátil.
    * El estado subido es completo (incluye 15 min de tendencias), así que al
      volver la conexión la app recupera también lo ocurrido durante el corte.
    * Si la sesión termina sin conexión, queda en ``pendientes/`` y se sube la
      próxima vez (``flush_pending``) o con ``python -m medikktion subir-pendientes``.
    """

    BACKOFF = (2, 5, 10, 20, 30, 60)

    def __init__(self, remote, folder: str | Path = "sesiones", local_every: float = 5.0):
        self.remote = remote
        self.local = LocalSink(folder)
        self.pending_dir = Path(folder) / "pendientes"
        self.local_every = local_every
        self._latest: dict | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._opened = False
        self._last_local = 0.0
        self.online = True
        self.offline_since: float | None = None
        self.last_upload: float | None = None
        self.last_outage_s: float | None = None
        self.failures = 0
        self._thread = threading.Thread(target=self._uploader, daemon=True)

    # --- estado de conexión (para la consola y para la app) -----------------
    def connection_info(self) -> dict:
        return {
            "online": self.online,
            "offline_since": datetime.fromtimestamp(self.offline_since, timezone.utc).isoformat() if self.offline_since else None,
            "last_outage_s": round(self.last_outage_s) if self.last_outage_s else None,
            "recovered_at": datetime.now(timezone.utc).isoformat() if self.online and self.last_outage_s else None,
        }

    def _mark_ok(self):
        if not self.online and self.offline_since:
            self.last_outage_s = time.time() - self.offline_since
            log.warning("Conexión recuperada tras %.0f s", self.last_outage_s)
        self.online, self.offline_since, self.failures = True, None, 0
        self.last_upload = time.time()

    def _mark_fail(self, e: Exception):
        if self.online:
            log.warning("Sin conexión con Firebase: %s", e)
            self.offline_since = time.time()
        self.online = False
        self.failures += 1

    # --- interfaz de sink ----------------------------------------------------
    def open_session(self, session_id: str, meta: dict) -> None:
        self.session_id, self.meta = session_id, meta
        self.local.open_session(session_id, meta)
        try:
            self.remote.open_session(session_id, meta)
            self._opened = True
            self._mark_ok()
        except Exception as e:  # noqa: BLE001
            self._mark_fail(e)
        self._thread.start()

    def publish(self, snapshot: dict) -> None:
        with self._lock:
            self._latest = snapshot
        self._wake.set()
        now = time.time()
        if now - self._last_local >= self.local_every:
            self._last_local = now
            try:
                self.local.publish({**snapshot, "status": "live"})
            except OSError as e:
                log.warning("No se pudo guardar la copia local: %s", e)

    def _push(self, snapshot: dict) -> None:
        if not self._opened:
            self.remote.open_session(self.session_id, self.meta)
            self._opened = True
        self.remote.publish({**snapshot, "connection": self.connection_info()})

    def _uploader(self):
        while not self._stop.is_set():
            wait = None if self.online else self.BACKOFF[min(self.failures - 1, len(self.BACKOFF) - 1)]
            self._wake.wait(timeout=wait)
            self._wake.clear()
            if self._stop.is_set():
                break
            with self._lock:
                snap = self._latest
            if snap is None:
                continue
            try:
                was_offline = not self.online
                self._push(snap)
                self._mark_ok()
                if was_offline:
                    self._push(snap)  # segunda subida: ya lleva "recuperado tras X s" para la app
            except Exception as e:  # noqa: BLE001
                self._mark_fail(e)

    def close(self, snapshot: dict) -> bool:
        """True si la sesión quedó subida; False si queda pendiente en el portátil."""
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=15)
        final = {**self.meta, **snapshot, "status": "finished"}
        self.local.publish(final)
        try:
            if not self._opened:
                self.remote.open_session(self.session_id, self.meta)
                self._opened = True
            self.remote.close({**snapshot, "connection": self.connection_info()})
            self._mark_ok()
            return True
        except Exception as e:  # noqa: BLE001
            self._mark_fail(e)
            self.pending_dir.mkdir(parents=True, exist_ok=True)
            (self.pending_dir / f"{self.session_id}.json").write_text(
                json.dumps(final, ensure_ascii=False), encoding="utf-8")
            return False

    def flush_pending(self) -> int:
        """Sube las sesiones que terminaron sin conexión. Devuelve cuántas se subieron."""
        if not self.pending_dir.exists():
            return 0
        done = 0
        for f in sorted(self.pending_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self.remote.upload_finished(f.stem, data)
                f.unlink()
                done += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Sesión pendiente %s no subida todavía: %s", f.stem, e)
                break
        return done

    def pending_count(self) -> int:
        return len(list(self.pending_dir.glob("*.json"))) if self.pending_dir.exists() else 0

    def watch_report_requests(self, cb) -> None:
        try:
            self.remote.watch_report_requests(cb)  # el listener de Firestore se reconecta solo
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo escuchar peticiones de informe: %s", e)

    def report_done(self, to: list[str], ok: bool, error: str | None = None) -> None:
        try:
            self.remote.report_done(to, ok, error)
        except Exception as e:  # noqa: BLE001
            log.warning("Estado del informe no subido: %s", e)

    def machine_history(self, serial: str):
        try:
            hist, sw = self.remote.machine_history(serial)
        except Exception:  # noqa: BLE001
            hist, sw = [], None
        if not hist:
            hist, sw = self.local.machine_history(serial)
        return hist, sw
