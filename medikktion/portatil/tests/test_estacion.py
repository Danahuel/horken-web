"""La ventana del portátil: servidor local, empezar/parar una lectura, grabar y libro de lecturas."""
import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

from medikktion.estacion import Controller, make_handler


def _call(base, path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_station_demo_reading_end_to_end(tmp_path):
    ctl = Controller(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ctl))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            assert b"MEDIKKTION" in r.read()
        st = _call(base, "/api/estado")
        assert not st["running"] and "cat320" in st["scenarios"]

        assert _call(base, "/api/iniciar", {"modo": "demo", "escenario": "cat320", "ubicacion": "Prueba", "grabar": True})["ok"]
        deadline = time.time() + 20
        snap = None
        while time.time() < deadline:
            st = _call(base, "/api/estado")
            snap = st["snapshot"]
            if snap and snap["summary"]["active_dtcs"] == 6 and snap["tamper"]["verdict"] == "manipulado":
                break
            time.sleep(0.5)
        assert st["running"] and snap["summary"]["active_dtcs"] == 6
        assert snap["recording"]["active"]

        assert _call(base, "/api/parar", {})["ok"]
        deadline = time.time() + 15
        while time.time() < deadline and _call(base, "/api/estado")["running"]:
            time.sleep(0.5)
        st = _call(base, "/api/estado")
        assert not st["running"] and st["error"] is None
        assert st["last"]["summary"]["active_dtcs"] == 6
        assert len(st["logbook"]) == 1 and st["logbook"][0]["pdf"]
        assert len(st["recordings"]) == 1
    finally:
        srv.shutdown()
