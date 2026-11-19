"""Programa del portátil.

  python -m medikktion demo --escenario cat320          # sin adaptador (simulador)
  python -m medikktion leer --interfaz pcan --canal PCAN_USBBUS1
  python -m medikktion leer --interfaz slcan --canal /dev/tty.usbmodem1101
  python -m medikktion adaptadores                       # Windows: lectores RP1210 instalados
  python -m medikktion leer --interfaz rp1210 --canal NULN2R32 --dispositivo 1
  python -m medikktion coche --puerto COM5 --km-cuadro 145000   # coche/furgoneta con ELM327
  python -m medikktion interfaces
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import can

from . import collector, report, simulator
from .sinks import FirestoreSink, LocalSink, ResilientSink, prune_local

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

log = logging.getLogger("medikktion")
logging.getLogger("pint").setLevel(logging.ERROR)  # aviso inofensivo de una dependencia de python-OBD


def load_config(path: str | None) -> dict:
    p = Path(path or "config.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def apply_demo_plate(args, sc: dict) -> None:
    """En las pruebas, si no se escribe placa, se usa la de la máquina simulada."""
    p = sc.get("placa") or {}
    for attr, key in (("marca", "make"), ("modelo", "model"), ("serie_placa", "serial"), ("anio", "year"),
                      ("horas_cuadro", "hours")):
        if getattr(args, attr, None) in (None, "") and key in p:
            setattr(args, attr, p[key])


def plate_from_args(args) -> dict:
    """Datos de la placa escritos por el usuario (solo los que tienen valor)."""
    pl = {"make": getattr(args, "marca", None), "model": getattr(args, "modelo", None),
          "serial": getattr(args, "serie_placa", None), "year": getattr(args, "anio", None),
          "hours": getattr(args, "horas_cuadro", None), "km": getattr(args, "km_cuadro", None)}
    return {k: v for k, v in pl.items() if v not in (None, "")}


def is_network_error(e: Exception) -> bool:
    """Fallo de red (reintentar luego) frente a fallo de configuración (avisar ya)."""
    import smtplib
    import socket
    if isinstance(e, (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused)):
        return False
    return isinstance(e, (ConnectionError, TimeoutError, socket.gaierror, socket.timeout,
                          smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError))


def make_sink(cfg: dict, args):
    """Con Firebase configurado: subida a prueba de cortes. Sin él: solo archivos locales."""
    if cfg.get("firebase_credentials") and not getattr(args, "local", False):
        try:
            return ResilientSink(FirestoreSink(cfg["firebase_credentials"]), args.carpeta)
        except Exception as e:  # noqa: BLE001
            print(f"No se pudo iniciar Firebase ({e}); se guarda solo en el portátil.")
    return LocalSink(args.carpeta)


def run(bus: can.BusABC | None, cfg: dict, args, sim=None, car=None, j1587_api=None,
        stop: threading.Event | None = None, hooks: dict | None = None) -> dict:
    """Lectura completa. ``stop`` la termina desde fuera (estación) y ``hooks``
    recibe las funciones para grabar, enviar informe y consultar el estado."""
    sink = make_sink(cfg, args)
    dbc = None
    if getattr(args, "dbc", None):
        from .dbc import DbcDecoder
        dbc = DbcDecoder(*args.dbc)
        print(f"DBC cargado: {len(dbc)} mensajes del fabricante")
    from .pricing import Pricing
    pricing = Pricing.from_config(cfg, args.clase, getattr(args, "km_viaje", 0) or 0)
    state = collector.MachineState(machine_class=args.clase, labour_rate=pricing, dbc=dbc)
    state.plate = plate_from_args(args)
    state.asking_price = getattr(args, "precio", None)
    sess = collector.DiagnosticSession(bus, state) if bus is not None else None
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    meta = {"session_id": session_id, "operator": cfg.get("operator", args.operador),
            "location": args.ubicacion, "recipients": cfg.get("default_recipients", []),
            "simulated": sim is not None, "started_at": datetime.now(timezone.utc).isoformat(),
            "plate": state.plate, "asking_price": state.asking_price}
    resilient = isinstance(sink, ResilientSink)
    n_del, mb = prune_local(args.carpeta, int(cfg.get("retencion_dias", 365)), float(cfg.get("max_mb_local", 1000)))
    n2, mb2 = prune_local(Path(args.carpeta) / "grabaciones", int(cfg.get("retencion_grabaciones_dias", 90)),
                          float(cfg.get("max_mb_grabaciones", 2000)), suffixes=(".blf",))
    n_del, mb = n_del + n2, round(mb + mb2, 1)
    if n_del:
        print(f"Limpieza: {n_del} archivo(s) antiguo(s) borrado(s) del portátil ({mb} MB). En la app siguen disponibles.")
    if resilient:
        n = sink.flush_pending()
        if n:
            print(f"{n} sesión(es) guardada(s) sin conexión se han subido ahora a la app.")
    sink.open_session(session_id, meta)
    print(f"Sesión {session_id} abierta → "
          f"{'Firebase (los móviles lo ven ya)' if resilient and sink.online else 'SIN CONEXIÓN: se guarda en el portátil y se subirá al volver' if resilient else sink.folder}")
    pending_reports: list[list[str]] = []

    def send_report(recipients, lang: str = "es") -> bool:
        snap = {**meta, **state.snapshot()}
        if hasattr(sink, "journal"):
            snap["journal"] = sink.journal()
        lang = lang or cfg.get("idioma_informe", "es")
        pdf = report.build_pdf(snap, Path(args.carpeta) / f"{session_id}{'-en' if lang == 'en' else ''}.pdf", lang=lang)
        try:
            from .mailer import send_report as mail
            mail(cfg["smtp"], recipients or meta["recipients"], snap, pdf)
            sink.report_done(recipients, True)
            print(f"\nInforme enviado a {recipients}")
            return True
        except Exception as e:  # noqa: BLE001
            if is_network_error(e) or (resilient and not sink.online):
                pending_reports.append((recipients, lang))  # sin red: se reintenta al volver la conexión
                print(f"\nInforme en espera (sin conexión): se enviará en cuanto vuelva internet")
            else:
                sink.report_done(recipients, False, str(e))
                print(f"\nNo se pudo enviar el informe: {e}")
            return False

    uds_thread = None
    j1587 = None
    from .recorder import Recorder
    rec = Recorder(args.carpeta, session_id)

    def set_recording(active: bool):
        if sess is None:
            print("\nGrabación no disponible en este modo (OBD con ELM327).")
            return
        if active and not rec.active:
            path = rec.start(sess.notifier)
            print(f"\nGRABANDO tramas en {path}")
            threading.Thread(target=sess.request_all, daemon=True).start()  # que la grabación incluya horas, DM2, software...
        elif not active and rec.active:
            path = rec.stop()
            print(f"\nGrabación guardada: {path} ({rec.frames} tramas)")
        sink.publish({**state.snapshot(), "recording": rec.status()})

    pump_rec = {"auto": False}

    def pump(action: str, payload: dict | None = None) -> dict:
        """Prueba de bombas desde la estación: iniciar, capturar, manual, siguiente, anterior, terminar, cancelar."""
        payload = payload or {}
        if action == "iniciar":
            on_step = sim.set_operator if hasattr(sim, "set_operator") else None
            out = state.start_pump_test(payload.get("alivio") or None, payload.get("pilotaje") or None, on_step)
            if sess is not None and not rec.active:     # se graba para poder aprender las presiones de la centralita
                rec.start(sess.notifier)
                pump_rec["auto"] = True
                print(f"\nPrueba de bombas: grabando tramas en {rec.path}")
        else:
            out = state.pump_action(action, payload.get("valores"))
        if action == "terminar":
            threading.Thread(target=learn_pressures, daemon=True).start()
        sink.publish({**state.snapshot(), "recording": rec.status()})
        return out

    def learn_pressures():
        """Tras una prueba con manómetro: busca en la grabación qué mensaje lleva esas presiones."""
        from . import hidraulica
        pt = state.pump_test
        if pt is None or rec.path is None:
            return
        manual = [m for m in pt.marks if m["source"] == "manometro"]
        path = rec.stop() if pump_rec["auto"] and rec.active else rec.path
        pump_rec["auto"] = False
        if not manual or state.pressure_profile:
            return
        time.sleep(0.5)
        info = state.machine_info()
        alivio = next((s_["nominal"] for s_ in pt.steps if s_["kind"] == "alivio"), 300)
        pil = next((s_["nominal"] for s_ in pt.steps if s_["kind"] == "pilotaje"), None)
        try:
            prof = hidraulica.profile_from_recording(path, alivio, pil, {"pump_test": {"marks": pt.marks}},
                                                     info["brand_key"], info.get("model", ""))
        except Exception as e:  # noqa: BLE001
            print(f"\nNo se pudo analizar la grabación de la prueba: {e}")
            return
        if prof["verificado"] == "manometro" and info.get("serial"):
            prof["solo_serie_prefijo"] = info["serial"]      # solo para ESTA máquina
            name = f"auto_{info['brand_key']}_{(info.get('model') or 'x').replace(' ', '')}_{info['serial']}"
            out = hidraulica.PRESION_DIR / f"{name}.json"
            out.write_text(json.dumps({k: v for k, v in prof.items() if k != "candidatos"}, ensure_ascii=False,
                                      indent=2), encoding="utf-8")
            state.pressure_profiles = hidraulica.load_profiles()
            state._pressure_map_at = 0
            print(f"\nPresiones de bomba encontradas en la centralita y confirmadas con el manómetro "
                  f"({', '.join(prof['senales'])}). Esta máquina las mostrará en vivo a partir de ahora.")
        else:
            print("\nLa centralita de esta máquina no parece emitir las presiones de bomba (o no coinciden con el "
                  "manómetro). La prueba queda hecha con las lecturas del manómetro.")

    def uds_scan():
        from .uds import UdsScanner
        n = UdsScanner(bus, sess.notifier).scan(state)
        print(f"\nUDS: {n} centralita(s) encontradas")

    if sess:
        sess.start()
        if getattr(args, "grabar", False):
            rec.start(sess.notifier)   # antes de pedir nada: la grabación queda completa
            print(f"GRABANDO tramas en {rec.path}")
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
        read_car(car, state)
    time.sleep(2.0)
    hist, sw = sink.machine_history(state.machine_info().get("serial"))
    state.history, state.previous_software = hist, sw
    if hist:
        print(f"Esta máquina ya se leyó {len(hist)} vez/veces: se compara con esas lecturas.")
    try:
        costs = sink.real_costs()
    except Exception:  # noqa: BLE001
        costs = {}
    if costs:
        state.pricing.real_costs = costs
        print(f"Precios aprendidos de {sum(len(v) for v in costs.values())} reparación(es) real(es).")
    sink.watch_report_requests(send_report, set_recording)
    if hooks is not None:
        hooks.update({
            "record": set_recording, "report": send_report, "session_id": session_id, "meta": meta, "pump": pump,
            "snapshot": lambda: {**meta, **state.snapshot(), "recording": rec.status()},
            "connection": lambda: (sink.connection_info() | {"pending": sink.pending_count()}) if resilient else None,
        })
    t_end = time.time() + args.segundos if args.segundos else None
    last_req = time.time()
    last_retry = time.time()
    try:
        while (t_end is None or time.time() < t_end) and not (stop is not None and stop.is_set()):
            if car is not None:
                from .obd_car import read_car
                read_car(car, state, samples=1)
            state.record_trend()
            snap = {**state.snapshot(), "recording": rec.status()}
            sink.publish(snap)
            s = snap["summary"]
            live = snap["live"]
            net = ""
            if resilient:
                net = (" · en línea" if sink.online else
                       f" · SIN CONEXIÓN {time.time() - (sink.offline_since or time.time()):.0f} s (guardando en el portátil)")
            recs = f" · REC {rec.status()['mb']:.1f} MB" if rec.active else ""
            print(f"\r{s['frames']:>7} tramas · {s['ecus']} centralitas · {s['active_dtcs']} activas · "
                  f"{live.get('rpm', {}).get('value', 0):>6.0f} rpm{recs}{net}      ", end="", flush=True)
            if pending_reports and time.time() - last_retry > 15 and (not resilient or sink.online):
                last_retry = time.time()
                for r in list(pending_reports):
                    pending_reports.remove(r)
                    send_report(*r)
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
    if rec.active:
        path = rec.stop()
        print(f"Grabación guardada: {path} ({rec.frames} tramas, {rec.status()['mb']} MB)")
    snap = {**meta, **state.snapshot(), "recording": rec.status()}
    uploaded = sink.close(snap)
    if resilient and not uploaded:
        print("Sin conexión al terminar: la sesión queda guardada en el portátil y se subirá sola la próxima vez "
              "que abras el programa (o ahora con: python -m medikktion subir-pendientes).")
    pdf = report.build_pdf(snap, Path(args.carpeta) / f"{session_id}.pdf")
    Path(args.carpeta, f"{session_id}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Informe PDF: {pdf}")
    for r, _lang in pending_reports:
        print(f"Informe para {', '.join(r)} sin enviar (sin conexión). El PDF está en {pdf}")
    if args.email:
        send_report(args.email)
    if j1587:
        j1587.stop()
    if sess:
        sess.stop()
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(prog="medikktion", description="Diagnóstico J1939 de maquinaria pesada")
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
    common.add_argument("--grabar", action="store_true", help="grabar todas las tramas CAN (archivo .blf)")
    common.add_argument("--km-viaje", type=float, default=0, help="km de ida hasta la máquina (desplazamiento)")
    pl = common.add_argument_group("datos de la placa (opcionales, para identificar y comprobar)")
    pl.add_argument("--marca")
    pl.add_argument("--modelo")
    pl.add_argument("--serie-placa", help="nº de serie de la placa de la máquina")
    pl.add_argument("--anio", type=int, help="año de fabricación")
    pl.add_argument("--horas-cuadro", type=float, help="horas que marca el cuadro")
    pl.add_argument("--km-cuadro", type=float, help="km que marca el cuadro")
    pl.add_argument("--precio", type=float, help="precio que piden por la máquina (informe de compra)")
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
    rp = sub.add_parser("reproducir", parents=[common], help="reproduce una grabación .blf como si fuera la máquina")
    rp.add_argument("archivo")
    rp.add_argument("--velocidad", type=float, default=1.0, help="1 = tiempo real, 5 = cinco veces más rápido")
    sub.add_parser("interfaces", help="adaptadores compatibles")
    da = sub.add_parser("importar-j1939da", help="importa el diccionario oficial SAE J1939DA (Excel)")
    da.add_argument("archivo")
    es = sub.add_parser("estacion", help="abre la ventana de la estación de lectura")
    es.add_argument("--puerto-web", type=int, default=8750)
    es.add_argument("--sin-ventana", action="store_true")
    gd = sub.add_parser("generar-demos", help="genera las 4 máquinas de demostración de la app")
    gd.add_argument("--salida", default="../app/assets/demo")
    sp = sub.add_parser("subir-pendientes", help="sube las sesiones guardadas sin conexión")
    sp.add_argument("--carpeta", default="sesiones")
    sp.add_argument("--config")
    sub.add_parser("configurar", help="asistente de puesta en marcha (Firebase, Gmail, cuentas)")
    sub.add_parser("comprobar", help="comprueba que todo funciona")
    ca = sub.add_parser("codigo-app", help="genera el código de la app desde google-services.json")
    ca.add_argument("archivo")
    sub.add_parser("adaptadores", help="Windows: lista los lectores RP1210 instalados")
    bp = sub.add_parser("buscar-presiones", help="busca en una grabación qué mensaje lleva las presiones de bomba")
    bp.add_argument("grabacion", help="archivo .blf (mejor grabado durante una prueba de bombas)")
    bp.add_argument("--alivio", type=float, required=True, help="presión de alivio del manual (bar)")
    bp.add_argument("--pilotaje", type=float, help="presión de pilotaje del manual (bar)")
    bp.add_argument("--sesion", help="JSON de la sesión con la prueba de bombas (lecturas de manómetro)")
    bp.add_argument("--marca", default="", help="caterpillar, fuchs, hamm, arjes... (clave de kb/marcas.json)")
    bp.add_argument("--modelo", default="")
    bp.add_argument("--guardar", help="nombre del perfil a guardar en kb/presiones (p. ej. cat_320_gc)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    for stream in (sys.stdout, sys.stderr):  # consolas Windows antiguas: nunca fallar por un acento o "→"
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    if args.cmd == "interfaces":
        print(INTERFACES)
        return 0
    if args.cmd == "importar-j1939da":
        from .j1939da import import_xlsx
        n = import_xlsx(args.archivo)
        print(f"{n} SPN oficiales importados. Ya se usan en todas las lecturas.")
        return 0
    if args.cmd == "estacion":
        from .estacion import serve
        serve(Path("."), args.puerto_web, open_ui=not args.sin_ventana, idle_exit=0 if args.sin_ventana else 45)
        return 0
    if args.cmd == "generar-demos":
        from .demos import generate
        generate(args.salida)
        return 0
    if args.cmd == "subir-pendientes":
        cfg = load_config(args.config)
        if not cfg.get("firebase_credentials"):
            print("Firebase no está configurado (python -m medikktion configurar).")
            return 1
        rs = ResilientSink(FirestoreSink(cfg["firebase_credentials"]), args.carpeta)
        n, left = rs.flush_pending(), rs.pending_count()
        print(f"{n} sesión(es) subida(s). Pendientes: {left}.")
        return 0 if left == 0 else 1
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
    if args.cmd == "buscar-presiones":
        from . import hidraulica
        ses = json.loads(Path(args.sesion).read_text(encoding="utf-8")) if args.sesion else None
        prof = hidraulica.profile_from_recording(args.grabacion, args.alivio, args.pilotaje, ses, args.marca, args.modelo)
        for ch, cands in prof["candidatos"].items():
            print(f"\n{hidraulica.CHANNELS[ch]}:")
            if not cands:
                print("  ningún candidato (¿se llevó la hidráulica contra su tope durante la grabación?)")
            for c in cands[:4]:
                man = f" · error frente al manómetro {c['manometer_error_pct']} %" if c["manometer_error_pct"] is not None else ""
                print(f"  PGN {c['pgn']} (0x{c['pgn']:04X}) de 0x{c['sa']:02X} · byte {c['byte']} · {c['len']} byte(s) "
                      f"{c['orden']} · escala {c['escala']:g} bar → pico {c['peak_bar']} bar, reposo {c['base_bar']} bar"
                      f"{man} · puntuación {c['score']}")
        print(f"\nSeñales elegidas: {', '.join(prof['senales']) or 'ninguna'} · "
              f"{'CONFIRMADO con manómetro' if prof['verificado'] else 'SIN CONFIRMAR: comprobar con un manómetro antes de fiarse'}")
        if args.guardar and prof["senales"]:
            out = hidraulica.PRESION_DIR / f"{args.guardar}.json"
            out.write_text(json.dumps({k: v for k, v in prof.items() if k != "candidatos"}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            print(f"Perfil guardado en {out}: a partir de ahora esa máquina muestra sus presiones en vivo.")
        return
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
        apply_demo_plate(args, sc)
        print(f"SIMULADOR: {sc['descripcion']}")
        machine_bus = can.Bus(interface="virtual", channel="medikktion")
        tool_bus = can.Bus(interface="virtual", channel="medikktion")
        sim = simulator.SimulatedMachine(machine_bus, args.escenario)
        sim.start()
        uds_ecus = []
        for u in sc.get("uds", []):
            ub = can.Bus(interface="virtual", channel="medikktion")
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
    elif args.cmd == "reproducir":
        from .recorder import duration, replay
        dur = duration(args.archivo)
        print(f"REPRODUCIENDO {args.archivo}: {dur / 60:.1f} min grabados, velocidad x{args.velocidad:g}")
        if not args.segundos:
            args.segundos = dur / max(args.velocidad, 0.01) + 4
        if args.ubicacion == "":
            args.ubicacion = f"Reproducción de {Path(args.archivo).name}"
        mbus = can.Bus(interface="virtual", channel="replay", receive_own_messages=False)
        tbus = can.Bus(interface="virtual", channel="replay")
        stop = threading.Event()
        th = threading.Thread(target=lambda: replay(args.archivo, mbus, args.velocidad, stop), daemon=True)
        th.start()
        try:
            run(tbus, cfg, args, sim="replay")
        finally:
            stop.set()
            th.join(timeout=2)
            mbus.shutdown()
            tbus.shutdown()
    elif args.cmd == "coche":
        import obd
        if args.clase == "generica":
            args.clase = "coche"
        conn = obd.OBD(args.puerto) if args.puerto else obd.OBD()
        if not conn.is_connected():
            print("No hay conexión con el ELM327. Revisa el puerto (python -m medikktion coche --puerto COM5) y que el contacto esté dado.")
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
