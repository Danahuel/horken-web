"""Estación de lectura: la ventana del portátil.

    python -m medikktion estacion          (o doble clic en Medikktion.bat)

Levanta un servidor solo para este ordenador (127.0.0.1) y abre una ventana de
Edge en modo aplicación (sin barra de direcciones). Toda la lógica es la misma
que la del programa de consola: aquí solo se arranca, se para y se mira.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import can

from .. import __main__ as cli
from .. import analysis, simulator

log = logging.getLogger("medikktion.estacion")
STATIC = Path(__file__).parent / "static"
FONTS = Path(__file__).resolve().parents[1] / "fonts"
PORT = 8750


class _Tape(io.TextIOBase):
    """Recoge lo que el programa escribe en consola para mostrarlo en la ventana."""

    def __init__(self, lines: deque, status: dict):
        self.lines, self.status, self._buf = lines, status, ""

    def write(self, s: str) -> int:
        self._buf += s
        while True:
            i_n, i_r = self._buf.find("\n"), self._buf.find("\r")
            idx = min(x for x in (i_n, i_r) if x >= 0) if (i_n >= 0 or i_r >= 0) else -1
            if idx < 0:
                break
            chunk, sep, self._buf = self._buf[:idx], self._buf[idx], self._buf[idx + 1:]
            chunk = chunk.strip()
            if not chunk:
                continue
            if sep == "\r":
                self.status["line"] = chunk           # línea de estado que se sobrescribe
            else:
                self.lines.append({"t": datetime.now().strftime("%H:%M:%S"), "text": chunk})
        return len(s)


class Controller:
    def __init__(self, folder: Path):
        self.folder = folder
        self.lines: deque = deque(maxlen=300)
        self.status: dict = {}
        self.thread: threading.Thread | None = None
        self.stop_ev = threading.Event()
        self.hooks: dict = {}
        self.mode: str | None = None
        self.started: float | None = None
        self.error: str | None = None
        self.last_result: dict | None = None
        self.last_seen = time.time()  # última vez que la ventana preguntó

    # ------------------------------------------------------------------ info
    def config(self) -> dict:
        cfg = cli.load_config(str(self.folder / "config.json"))
        return cfg

    def adapters(self) -> list[dict]:
        if sys.platform != "win32":
            return []
        try:
            from ..rp1210 import list_adapters
            return list_adapters()
        except Exception:  # noqa: BLE001
            return []

    def logbook(self, limit: int = 30) -> list[dict]:
        out = []
        folder = self.folder / "sesiones"
        if not folder.exists():
            return out
        for f in sorted(folder.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            m = d.get("machine", {})
            out.append({
                "id": f.stem, "when": d.get("updated_at", "")[:16].replace("T", " "),
                "brand": (m.get("brand_name") or "").split(" (")[0], "model": m.get("model") or "",
                "serial": m.get("serial") or "", "location": d.get("location") or "",
                "active": d.get("summary", {}).get("active_dtcs", 0),
                "health": (d.get("health") or {}).get("score"),
                "tamper": d.get("tamper", {}).get("verdict"),
                "pdf": (folder / f"{f.stem}.pdf").exists(),
                "simulated": d.get("simulated", False),
            })
        return out

    def recordings(self) -> list[dict]:
        folder = self.folder / "sesiones" / "grabaciones"
        if not folder.exists():
            return []
        return [{"name": f.name, "mb": round(f.stat().st_size / 1048576, 2),
                 "when": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}
                for f in sorted(folder.glob("*.blf"), key=lambda x: x.stat().st_mtime, reverse=True)]

    def disk(self) -> dict:
        folder = self.folder / "sesiones"
        total = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) if folder.exists() else 0
        pend = len(list((folder / "pendientes").glob("*.json"))) if (folder / "pendientes").exists() else 0
        return {"mb": round(total / 1048576, 1), "pending": pend}

    def state(self) -> dict:
        cfg = self.config()
        running = bool(self.thread and self.thread.is_alive())
        snap = None
        if running and "snapshot" in self.hooks:
            try:
                snap = self.hooks["snapshot"]()
            except Exception:  # noqa: BLE001
                snap = None
        conn = None
        if running and self.hooks.get("connection"):
            try:
                conn = self.hooks["connection"]()
            except Exception:  # noqa: BLE001
                conn = None
        return {
            "now": datetime.now().isoformat(timespec="seconds"),
            "operator": cfg.get("operator", ""),
            "firebase": bool(cfg.get("firebase_credentials")),
            "gmail": bool(cfg.get("smtp", {}).get("password")),
            "recipients": cfg.get("default_recipients", []),
            "platform": sys.platform,
            "adapters": self.adapters(),
            "classes": {k: v[0] for k, v in analysis.MACHINE_CLASSES.items()},
            "scenarios": {k: v["descripcion"] for k, v in simulator.SCENARIOS.items()},
            "running": running, "mode": self.mode if running else None,
            "started": self.started if running else None,
            "status_line": self.status.get("line", "") if running else "",
            "snapshot": _slim(snap) if snap else None,
            "connection": conn,
            "error": self.error,
            "last": _slim(self.last_result) if (self.last_result and not running) else None,
            "log": list(self.lines)[-60:],
            "disk": self.disk(),
            "logbook": self.logbook(),
            "recordings": self.recordings(),
        }

    # ---------------------------------------------------------------- acciones
    def start(self, p: dict) -> dict:
        if self.thread and self.thread.is_alive():
            return {"ok": False, "error": "Ya hay una lectura en curso."}
        self.stop_ev = threading.Event()
        self.hooks, self.error, self.status, self.last_result = {}, None, {}, None
        mode = p.get("modo", "maquina")
        args = argparse.Namespace(
            config=None, clase=p.get("clase") or "generica", segundos=0, intervalo=2.0,
            carpeta=str(self.folder / "sesiones"), operador="", ubicacion=p.get("ubicacion", ""),
            email=None, local=False, dbc=None, sin_uds=bool(p.get("sin_uds")), grabar=bool(p.get("grabar")),
            dispositivo=int(p.get("dispositivo") or 1), protocolo=p.get("protocolo") or "CAN",
            bitrate=int(p.get("bitrate") or 0), j1587=True, km_cuadro=p.get("km") or None,
            escenario=p.get("escenario") or "cat320", velocidad=float(p.get("velocidad") or 1),
        )
        self.mode, self.started = mode, time.time()
        self.thread = threading.Thread(target=self._worker, args=(mode, p, args), daemon=True)
        self.thread.start()
        return {"ok": True}

    def _worker(self, mode: str, p: dict, args):
        tape = _Tape(self.lines, self.status)
        cfg = self.config()
        buses = []
        try:
            with contextlib.redirect_stdout(tape):
                if mode == "demo":
                    sc = simulator.SCENARIOS[args.escenario]
                    if args.clase == "generica":
                        args.clase = sc["machine_class"]
                    print(f"SIMULADOR: {sc['descripcion']}")
                    mb, tb = can.Bus(interface="virtual", channel="est"), can.Bus(interface="virtual", channel="est")
                    buses += [mb, tb]
                    sim = simulator.SimulatedMachine(mb, args.escenario)
                    sim.start()
                    uds = []
                    for u in sc.get("uds", []):
                        ub = can.Bus(interface="virtual", channel="est")
                        buses.append(ub)
                        e = simulator.SimulatedUdsEcu(ub, u["addr"], u["dtcs"], u["dids"])
                        e.start()
                        uds.append(e)
                    try:
                        self.last_result = cli.run(tb, cfg, args, sim=sim, stop=self.stop_ev, hooks=self.hooks)
                    finally:
                        for e in uds:
                            e.stop()
                        sim.stop()
                elif mode == "reproducir":
                    from ..recorder import replay
                    path = self.folder / "sesiones" / "grabaciones" / Path(p.get("archivo", "")).name
                    args.ubicacion = args.ubicacion or f"Reproducción de {path.name}"
                    print(f"REPRODUCIENDO {path.name}")
                    mb, tb = can.Bus(interface="virtual", channel="rep"), can.Bus(interface="virtual", channel="rep")
                    buses += [mb, tb]
                    stop_rep = threading.Event()
                    th = threading.Thread(target=lambda: (replay(path, mb, args.velocidad, stop_rep),
                                                          time.sleep(3), self.stop_ev.set()), daemon=True)
                    th.start()
                    try:
                        self.last_result = cli.run(tb, cfg, args, sim="replay", stop=self.stop_ev, hooks=self.hooks)
                    finally:
                        stop_rep.set()
                elif mode == "coche":
                    import obd
                    if args.clase == "generica":
                        args.clase = "coche"
                    conn = obd.OBD(p.get("puerto")) if p.get("puerto") else obd.OBD()
                    if not conn.is_connected():
                        raise RuntimeError("No hay conexión con el ELM327. Revise el puerto y que el contacto esté dado.")
                    self.last_result = cli.run(None, cfg, args, car=conn, stop=self.stop_ev, hooks=self.hooks)
                else:
                    from ..rp1210 import RP1210Bus
                    lector = p.get("lector")
                    if not lector:
                        raise RuntimeError("Elija el lector.")
                    bus = RP1210Bus(lector, device_id=args.dispositivo, protocol=args.protocolo, bitrate=args.bitrate)
                    buses.append(bus)
                    print(f"Lector {lector} conectado ({args.protocolo})")
                    self.last_result = cli.run(bus, cfg, args, j1587_api=lector, stop=self.stop_ev, hooks=self.hooks)
                print("Lectura terminada.")
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            self.lines.append({"t": datetime.now().strftime("%H:%M:%S"), "text": f"ERROR: {e}"})
            log.exception("Lectura fallida")
        finally:
            for b in buses:
                with contextlib.suppress(Exception):
                    b.shutdown()

    def stop(self) -> dict:
        self.stop_ev.set()
        return {"ok": True}

    def record(self, active: bool) -> dict:
        if "record" not in self.hooks:
            return {"ok": False, "error": "No hay lectura en curso."}
        threading.Thread(target=self.hooks["record"], args=(active,), daemon=True).start()
        return {"ok": True}

    def report(self, to: list[str]) -> dict:
        if "report" not in self.hooks:
            return {"ok": False, "error": "No hay lectura en curso."}
        threading.Thread(target=self.hooks["report"], args=(to,), daemon=True).start()
        return {"ok": True}

    def check(self) -> dict:
        from ..setup_wizard import check
        buf = io.StringIO()
        cwd = os.getcwd()
        try:
            os.chdir(self.folder)
            with contextlib.redirect_stdout(buf):
                code = check(Path("."))
        finally:
            os.chdir(cwd)
        return {"ok": code == 0, "lines": buf.getvalue().splitlines()}

    def open_path(self, what: str, name: str = "") -> dict:
        base = self.folder / "sesiones"
        target = base / "grabaciones" if what == "grabaciones" else base
        if name:
            target = base / Path(name).name
        if not target.exists():
            return {"ok": False, "error": "No existe todavía."}
        if sys.platform == "win32":
            os.startfile(str(target))  # noqa: S606  (abre carpeta o PDF con el programa de Windows)
        else:
            webbrowser.open(target.as_uri())
        return {"ok": True}


def _slim(snap: dict | None) -> dict | None:
    """Lo que la ventana necesita (sin tendencias completas ni textos largos)."""
    if not snap:
        return None
    return {
        "session_id": snap.get("session_id"), "machine": snap.get("machine", {}),
        "summary": snap.get("summary", {}), "health": snap.get("health", {}),
        "tamper": {k: snap.get("tamper", {}).get(k) for k in ("verdict", "label", "score", "reported_hours", "estimated_real_hours")},
        "lamps": snap.get("lamps", {}), "protocols": snap.get("protocols", []),
        "live": snap.get("live", {}), "recording": snap.get("recording"),
        "dtcs": [{k: d.get(k) for k in ("code", "name", "fmi_text", "severity", "active", "source_name", "cost_min_eur",
                                       "cost_max_eur", "difficulty")} for d in snap.get("dtcs", [])][:20],
        "ecus": [{k: e.get(k) for k in ("address_hex", "name", "protocol", "engine_hours", "active_dtcs")}
                 for e in snap.get("ecus", [])],
        "location": snap.get("location"),
    }


def make_handler(ctl: Controller):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencio en consola
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: Path, ctype: str):
            if not path.exists():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/api/estado":
                ctl.last_seen = time.time()
                return self._json(ctl.state())
            if path.startswith("/fonts/"):
                return self._file(FONTS / Path(path).name, "font/ttf")
            name = "index.html" if path in ("/", "") else Path(path).name
            ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                     ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
                     ".png": "image/png", ".ico": "image/x-icon"}.get(Path(name).suffix, "application/octet-stream")
            return self._file(STATIC / name, ctype)

        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length") or 0)
            try:
                p = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                p = {}
            path = self.path.split("?")[0]
            routes = {
                "/api/iniciar": lambda: ctl.start(p),
                "/api/parar": ctl.stop,
                "/api/grabar": lambda: ctl.record(bool(p.get("activo"))),
                "/api/informe": lambda: ctl.report(p.get("destinatarios") or []),
                "/api/comprobar": ctl.check,
                "/api/abrir": lambda: ctl.open_path(p.get("que", "sesiones"), p.get("nombre", "")),
            }
            if path not in routes:
                return self._json({"ok": False, "error": "ruta desconocida"}, 404)
            try:
                return self._json(routes[path]())
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": str(e)}, 500)
    return H


def open_window(url: str) -> None:
    """Ventana sin barra de direcciones (Edge/Chrome en modo app); si no, el navegador normal."""
    if sys.platform == "win32":
        for exe in (shutil.which("msedge"), r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", shutil.which("chrome")):
            if exe and Path(exe).exists():
                subprocess.Popen([exe, f"--app={url}", "--window-size=1360,860"])
                return
    webbrowser.open(url)


def serve(folder: str | Path = ".", port: int = PORT, open_ui: bool = True, idle_exit: float = 45) -> None:
    for name in ("stdout", "stderr"):  # con pythonw no hay consola
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    folder = Path(folder).resolve()
    url = f"http://127.0.0.1:{port}/"
    ctl = Controller(folder)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctl))
    except OSError:
        # ya está abierta: solo se muestra la ventana
        if open_ui:
            open_window(url)
        return
    print(f"Estación de lectura en {url}")
    if open_ui:
        threading.Timer(0.6, open_window, args=(url,)).start()

    def watchdog():
        # al cerrar la ventana, el programa se cierra solo (salvo con una lectura en marcha)
        while True:
            time.sleep(5)
            busy = ctl.thread is not None and ctl.thread.is_alive()
            if idle_exit and not busy and time.time() - ctl.last_seen > idle_exit:
                srv.shutdown()
                return
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ctl.stop()
        srv.server_close()
