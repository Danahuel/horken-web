"""Destino de los datos: Firebase Firestore (tiempo real a los móviles) o archivo local."""
from __future__ import annotations

import json
import logging
import threading
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

    def open_session(self, session_id: str, meta: dict) -> None:
        self.ref = self.db.collection("sessions").document(session_id)
        self.ref.set({**meta, "status": "live", "created_at": self.fs.SERVER_TIMESTAMP}, merge=True)

    def publish(self, snapshot: dict) -> None:
        self.ref.set({**snapshot, "server_updated_at": self.fs.SERVER_TIMESTAMP}, merge=True)

    def close(self, snapshot: dict) -> None:
        self.publish({**snapshot, "status": "finished"})
        if self._watch:
            self._watch.unsubscribe()

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
