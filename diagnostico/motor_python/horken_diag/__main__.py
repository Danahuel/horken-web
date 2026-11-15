"""Programa del portátil.

  python -m horken_diag demo --escenario cat320          # sin adaptador (simulador)
  python -m horken_diag leer --interfaz pcan --canal PCAN_USBBUS1
  python -m horken_diag leer --interfaz slcan --canal /dev/tty.usbmodem1101
  python -m horken_diag adaptadores                       # Windows: lectores RP1210 instalados
  python -m horken_diag leer --interfaz rp1210 --canal NULN2R32 --dispositivo 1
  python -m horken_diag coche --puerto COM5 --km-cuadro 145000   # coche/furgoneta con ELM327
  python -m horken_diag interfaces
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import can

from . import collector, report, simulator
from .sinks import FirestoreSink, LocalSink

INTERFACES = """Adaptadores compatibles:
  rp1210    Nexiq USB-Link, DG DPA5, Noregon, Cat Comm Adapter, clones...   Windows   canal: nombre API (ver 'adaptadores')
  pcan      PEAK PCAN-USB            macOS (driver PCBUSB de mac-can.com), Windows, Linux
  slcan     CANable / USBtin (serie) macOS, Windows, Linux     canal: /dev/tty.usbmodemXXXX o COM3
  gs_usb    candleLight / CANable 2  macOS, Windows, Linux
  kvaser    Kvaser                   Windows, Linux
  vector    Vector VN16xx            Windows
  socketcan Cualquiera con SocketCAN Linux                     canal: can0
  virtual   Bus simulado (demo)      todos
Cable necesario: Deutsch 9 pines (J1939) → DB9. Velocidad habitual 250000 (algunas máquinas nuevas 500000)."""

log = logging.getLogger("horken")


def load_config(path: str | None) -> dict:
    p = Path(path or "config.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def run(bus: can.BusABC | None, cfg: dict, args, sim=None, car=None, j1587_api=None) -> dict:
    sink = FirestoreSink(cfg["firebase_credentials"]) if cfg.get("firebase_credentials") and not args.local else LocalSink(args.carpeta)
    dbc = None
    if getattr(args, "dbc", None):
        from .dbc import DbcDecoder
        dbc = DbcDecoder(*args.dbc)
        print(f"DBC cargado: {len(dbc)} mensajes del fabricante")
    state = collector.MachineState(machine_class=args.clase, labour_rate=cfg.get("labour_rate", 55), dbc=dbc)
    sess = collector.DiagnosticSession(bus, state) if bus is not None else None
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    meta = {"session_id": session_id, "operator": cfg.get("operator", args.operador),
            "location": args.ubicacion, "recipients": cfg.get("default_recipients", []),
            "simulated": sim is not None}
    sink.open_session(session_id, meta)
    print(f"Sesión {session_id} abierta → {'Firestore (los móviles lo ven ya)' if isinstance(sink, FirestoreSink) else sink.folder}")

    def send_report(recipients):
        snap = {**meta, **state.snapshot()}
        pdf = report.build_pdf(snap, Path(args.carpeta) / f"{session_id}.pdf")
        try:
            from .mailer import send_report as mail
            mail(cfg["smtp"], recipients or meta["recipients"], snap, pdf)
            sink.report_done(recipients, True)
            print(f"\nInforme enviado a {recipients}")
        except Exception as e:  # noqa: BLE001
            sink.report_done(recipients, False, str(e))
            print(f"\nNo se pudo enviar el informe: {e}")

    uds_thread = None
    j1587 = None

    def uds_scan():
        from .uds import UdsScanner
        n = UdsScanner(bus, sess.notifier).scan(state)
        print(f"\nUDS: {n} centralita(s) encontradas")

    if sess:
        sess.start()
        time.sleep(1.5)            # descubrir centralitas
        sess.request_all()
        if not getattr(args, "sin_uds", True):
            uds_thread = threading.Thread(target=uds_scan, daemon=True)
            uds_thread.start()
    if j1587_api:
        from .j1587 import J1587Reader
        try:
            j1587 = J1587Reader(j1587_api, args.dispositivo, state)
            j1587.start()
            print("J1587 (máquinas antiguas) escuchando también")
        except OSError as e:
            print(f"J1587 no disponible en este lector: {e}")
    if car is not None:
        from .obd_car import read_car
        read_car(car, state, cluster_km=getattr(args, "km_cuadro", None))
    time.sleep(2.0)
    hist, sw = sink.machine_history(state.machine_info().get("serial"))
    state.history, state.previous_software = hist, sw
    sink.watch_report_requests(send_report)
    t_end = time.time() + args.segundos if args.segundos else None
    last_req = time.time()
    try:
        while t_end is None or time.time() < t_end:
            if car is not None:
                from .obd_car import read_car
                read_car(car, state, cluster_km=getattr(args, "km_cuadro", None), samples=1)
            snap = state.snapshot()
            sink.publish(snap)
            s = snap["summary"]
            live = snap["live"]
            print(f"\r{s['frames']:>7} tramas · {s['ecus']} centralitas · {s['active_dtcs']} activas · "
                  f"{live.get('rpm', {}).get('value', 0):>6.0f} rpm · {snap['tamper']['label']}   ", end="", flush=True)
            if time.time() - last_req > 30:  # refrescar contadores y DM2
                if sess:
                    sess.request_all()
                if j1587:
                    j1587.request_all()
                last_req = time.time()
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        pass
    print()
    if uds_thread:
        uds_thread.join(timeout=15)
    snap = {**meta, **state.snapshot()}
    sink.close(snap)
    pdf = report.build_pdf(snap, Path(args.carpeta) / f"{session_id}.pdf")
    Path(args.carpeta, f"{session_id}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Informe PDF: {pdf}")
    if args.email:
        send_report(args.email)
    if j1587:
        j1587.stop()
    if sess:
        sess.stop()
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(prog="horken_diag", description="Diagnóstico J1939 de maquinaria pesada")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="config.json (Firebase, Gmail, destinatarios)")
    common.add_argument("--clase", default="generica", help="clase de máquina: " + ", ".join(collector.analysis.MACHINE_CLASSES))
    common.add_argument("--segundos", type=float, default=0, help="duración (0 = hasta Ctrl+C)")
    common.add_argument("--intervalo", type=float, default=2.0, help="segundos entre envíos a la app")
    common.add_argument("--carpeta", default="sesiones")
    common.add_argument("--operador", default="")
    common.add_argument("--ubicacion", default="")
    common.add_argument("--email", nargs="*", help="enviar el informe al terminar a estos correos")
    common.add_argument("--local", action="store_true", help="no usar Firebase aunque esté configurado")
    common.add_argument("--dbc", nargs="*", help="archivos DBC del fabricante para decodificar mensajes propios")
    common.add_argument("--sin-uds", action="store_true", help="no buscar centralitas UDS")
    d = sub.add_parser("demo", parents=[common], help="probar sin adaptador con una máquina simulada")
    d.add_argument("--escenario", default="cat320", choices=list(simulator.SCENARIOS))
    r = sub.add_parser("leer", parents=[common], help="leer una máquina real")
    r.add_argument("--interfaz", required=True)
    r.add_argument("--canal", required=True)
    r.add_argument("--bitrate", type=int, default=250000, help="250000 (habitual), 500000, o 0 = automático (RP1210)")
    r.add_argument("--dispositivo", type=int, default=1, help="RP1210: DeviceID (ver 'adaptadores')")
    r.add_argument("--protocolo", default="CAN", choices=["CAN", "J1939"], help="RP1210: CAN en bruto o J1939")
    r.add_argument("--j1587", action="store_true", help="RP1210: leer también J1708/J1587 (máquinas antiguas)")
    c = sub.add_parser("coche", parents=[common], help="coche/furgoneta por OBD-II con un ELM327")
    c.add_argument("--puerto", help="COM5, /dev/ttyUSB0... (vacío = buscar)")
    c.add_argument("--km-cuadro", type=float, help="km que marca el cuadro, para compararlos con la centralita")
    sub.add_parser("interfaces", help="adaptadores compatibles")
    sub.add_parser("configurar", help="asistente de puesta en marcha (Firebase, Gmail, cuentas)")
    sub.add_parser("comprobar", help="comprueba que todo funciona")
    ca = sub.add_parser("codigo-app", help="genera el código de la app desde google-services.json")
    ca.add_argument("archivo")
    sub.add_parser("adaptadores", help="Windows: lista los lectores RP1210 instalados")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    if args.cmd == "interfaces":
        print(INTERFACES)
        return 0
    if args.cmd == "configurar":
        from .setup_wizard import run_wizard
        return run_wizard(Path("."))
    if args.cmd == "comprobar":
        from .setup_wizard import check
        return check(Path("."))
    if args.cmd == "codigo-app":
        from .setup_wizard import app_code_from_google_services
        code = app_code_from_google_services(json.loads(Path(args.archivo).read_text(encoding="utf-8")))
        Path("codigo_app.txt").write_text(code + "\n", encoding="utf-8")
        print(code)
        return 0
    if args.cmd == "adaptadores":
        from .rp1210 import list_adapters
        found = list_adapters()
        if not found:
            print("No hay adaptadores RP1210 instalados (falta C:\\Windows\\RP121032.ini). Instala el driver del lector.")
        for a in found:
            print(f"{a['vendor']}  →  --canal {a['api']}   protocolos: {', '.join(a['protocols']) or '?'}")
            for d in a["devices"]:
                print(f"      --dispositivo {d['id']}   {d['description']}")
        return 0
    cfg = load_config(args.config)
    Path(args.carpeta).mkdir(parents=True, exist_ok=True)
    if args.cmd == "demo":
        sc = simulator.SCENARIOS[args.escenario]
        if args.clase == "generica":
            args.clase = sc["machine_class"]
        print(f"SIMULADOR: {sc['descripcion']}")
        machine_bus = can.Bus(interface="virtual", channel="horken")
        tool_bus = can.Bus(interface="virtual", channel="horken")
        sim = simulator.SimulatedMachine(machine_bus, args.escenario)
        sim.start()
        uds_ecus = []
        for u in sc.get("uds", []):
            ub = can.Bus(interface="virtual", channel="horken")
            uds_ecus.append((simulator.SimulatedUdsEcu(ub, u["addr"], u["dtcs"], u["dids"]), ub))
            uds_ecus[-1][0].start()
        try:
            run(tool_bus, cfg, args, sim)
        finally:
            for e, ub in uds_ecus:
                e.stop()
                ub.shutdown()
            sim.stop()
            machine_bus.shutdown()
            tool_bus.shutdown()
    elif args.cmd == "coche":
        import obd
        if args.clase == "generica":
            args.clase = "coche"
        conn = obd.OBD(args.puerto) if args.puerto else obd.OBD()
        if not conn.is_connected():
            print("No hay conexión con el ELM327. Revisa el puerto (python -m horken_diag coche --puerto COM5) y que el contacto esté dado.")
            return 1
        run(None, cfg, args, car=conn)
    else:
        if args.interfaz == "rp1210":
            from .rp1210 import RP1210Bus
            bus = RP1210Bus(args.canal, device_id=args.dispositivo, protocol=args.protocolo, bitrate=args.bitrate)
        else:
            bus = can.Bus(interface=args.interfaz, channel=args.canal, bitrate=args.bitrate)
        with bus:
            run(bus, cfg, args, j1587_api=args.canal if args.interfaz == "rp1210" and args.j1587 else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
