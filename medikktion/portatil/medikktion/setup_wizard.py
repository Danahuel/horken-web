"""Asistente de puesta en marcha: python -m medikktion configurar

Tú solo creas el proyecto en Firebase y descargas la clave de servicio.
El asistente hace el resto con esa clave:
  1. Guarda config.json (Gmail, correos, tarifa).
  2. Activa el inicio de sesión por email, crea la base de datos (si puede) y
     las cuentas tuya y de tu mecánico con contraseña aleatoria.
  3. Publica las reglas de seguridad con vuestros dos correos.
  4. Registra la app Android y genera el CÓDIGO DE LA APP (se pega en el móvil).
  5. Prueba Firestore y Gmail, y os manda a los dos un email con el código y la contraseña.
Cada paso que no se pueda hacer automáticamente explica qué pulsar en la consola.
"""
from __future__ import annotations

import base64
import getpass
import json
import secrets
import shutil
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

PACKAGE = "com.medikktion.app"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/firebase"]
RULES_TEMPLATE = Path(__file__).resolve().parents[2] / "firebase" / "firestore.rules"

OK, FAIL, WARN = "[ OK ]", "[FALLO]", "[ !! ]"


def _ask(text: str, default: str = "") -> str:
    v = input(f"{text}{f' [{default}]' if default else ''}: ").strip()
    return v or default


def find_service_key(folder: Path) -> Path | None:
    for p in sorted(folder.glob("*.json")) + sorted((Path.home() / "Downloads").glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if d.get("type") == "service_account" and "firebase" in d.get("client_email", ""):
            return p
    return None


def app_code_from_google_services(gs: dict) -> str:
    """google-services.json → código corto que se pega en la app."""
    c = gs["client"][0]
    data = {"k": c["api_key"][0]["current_key"], "a": c["client_info"]["mobilesdk_app_id"],
            "p": gs["project_info"]["project_id"], "s": gs["project_info"]["project_number"],
            "b": gs["project_info"].get("storage_bucket", "")}
    return "MDK1:" + base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def build_rules(emails: list[str]) -> str:
    text = RULES_TEMPLATE.read_text(encoding="utf-8") if RULES_TEMPLATE.exists() else ""
    listing = ",\n          ".join(f"'{e}'" for e in emails)
    start, end = text.index("request.auth.token.email in ["), text.index("];")
    return text[:start] + "request.auth.token.email in [\n          " + listing + "\n        " + text[end:]


class FirebaseSetup:
    def __init__(self, key_path: Path):
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        self.key_path = key_path
        self.project = json.loads(key_path.read_text(encoding="utf-8"))["project_id"]
        creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)
        self.http = AuthorizedSession(creds)

    def _ok(self, r) -> bool:
        return 200 <= r.status_code < 300

    def enable_email_login(self) -> tuple[bool, str]:
        r = self.http.patch(f"https://identitytoolkit.googleapis.com/admin/v2/projects/{self.project}/config"
                            "?updateMask=signIn.email.enabled,signIn.email.passwordRequired",
                            json={"signIn": {"email": {"enabled": True, "passwordRequired": True}}})
        return self._ok(r), r.text[:200]

    def create_database(self, location: str = "europe-west3") -> tuple[bool, str]:
        r = self.http.get(f"https://firestore.googleapis.com/v1/projects/{self.project}/databases/(default)")
        if self._ok(r):
            return True, "ya existía"
        r = self.http.post(f"https://firestore.googleapis.com/v1/projects/{self.project}/databases?databaseId=(default)",
                           json={"locationId": location, "type": "FIRESTORE_NATIVE"})
        return self._ok(r), r.text[:200]

    def deploy_rules(self, rules: str) -> tuple[bool, str]:
        base = f"https://firebaserules.googleapis.com/v1/projects/{self.project}"
        r = self.http.post(f"{base}/rulesets", json={"source": {"files": [{"name": "firestore.rules", "content": rules}]}})
        if not self._ok(r):
            return False, r.text[:200]
        ruleset = r.json()["name"]
        name = f"projects/{self.project}/releases/cloud.firestore"
        r = self.http.patch(f"{base}/releases/cloud.firestore", json={"release": {"name": name, "rulesetName": ruleset}})
        if r.status_code == 404:
            r = self.http.post(f"{base}/releases", json={"name": name, "rulesetName": ruleset})
        return self._ok(r), r.text[:200]

    def android_config(self) -> tuple[dict | None, str]:
        base = f"https://firebase.googleapis.com/v1beta1/projects/{self.project}/androidApps"
        r = self.http.get(base)
        if not self._ok(r):
            return None, r.text[:200]
        app = next((a for a in r.json().get("apps", []) if a.get("packageName") == PACKAGE), None)
        if app is None:
            r = self.http.post(base, json={"packageName": PACKAGE, "displayName": "Medikktion"})
            if not self._ok(r):
                return None, r.text[:200]
            op = r.json()["name"]
            for _ in range(30):
                time.sleep(2)
                o = self.http.get(f"https://firebase.googleapis.com/v1beta1/{op}").json()
                if o.get("done"):
                    app = o.get("response")
                    break
            if not app:
                return None, "la creación de la app Android no terminó a tiempo"
        r = self.http.get(f"https://firebase.googleapis.com/v1beta1/projects/-/androidApps/{app['appId']}/config")
        if not self._ok(r):
            return None, r.text[:200]
        return json.loads(base64.b64decode(r.json()["configFileContents"])), "ok"


def ensure_user(auth, email: str) -> tuple[str | None, bool]:
    """Crea la cuenta si no existe. Devuelve (contraseña nueva o None, creada)."""
    password = secrets.token_urlsafe(9)
    try:
        u = auth.get_user_by_email(email)
        auth.update_user(u.uid, password=password, email_verified=True)
        return password, False
    except auth.UserNotFoundError:
        auth.create_user(email=email, password=password, email_verified=True)
        return password, True


def test_smtp(smtp: dict) -> tuple[bool, str]:
    try:
        with smtplib.SMTP(smtp.get("host", "smtp.gmail.com"), int(smtp.get("port", 587)), timeout=20) as s:
            s.starttls()
            s.login(smtp["user"], smtp["password"])
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def send_welcome(smtp: dict, to: str, name: str, password: str, code: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = "Medikktion · tu acceso a la app de diagnóstico"
    msg["From"] = smtp.get("from") or smtp["user"]
    msg["To"] = to
    msg.set_content(f"""Hola {name},

Ya tienes acceso a Medikktion.

1. Instala la app (archivo Medikktion.apk que te pasarán).
2. Al abrirla te pedirá el código de configuración. Copia y pega esta línea entera:

{code}

3. Entra con:
   Email: {to}
   Contraseña: {password}

Cuando se lea una máquina, aparecerá en la app en el momento.
""")
    with smtplib.SMTP(smtp.get("host", "smtp.gmail.com"), int(smtp.get("port", 587)), timeout=30) as s:
        s.starttls()
        s.login(smtp["user"], smtp["password"])
        s.send_message(msg)


def run_wizard(folder: Path = Path(".")) -> int:
    print("\n=== MEDIKKTION · Puesta en marcha ===\n")
    cfg_path = folder / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    cfg.pop("_instrucciones", None)

    # 1. Clave de servicio
    key = folder / "clave-servicio-firebase.json"
    if not key.exists():
        found = find_service_key(folder)
        hint = str(found) if found else ""
        src = _ask("Ruta del archivo de clave de Firebase que descargaste (arrástralo aquí)", hint).strip('"')
        if not src or not Path(src).exists():
            print(f"{FAIL} No encuentro la clave. Firebase → ⚙ Configuración del proyecto → Cuentas de servicio → "
                  "Generar nueva clave privada.")
            return 1
        shutil.copy(src, key)
    cfg["firebase_credentials"] = key.name
    print(f"{OK} Clave de Firebase: {key.name}")

    # 2. Datos
    cfg["operator"] = _ask("Tu nombre (aparece en los informes)", cfg.get("operator", ""))
    me = _ask("Tu email (Gmail desde el que se envían los informes)", cfg.get("smtp", {}).get("user", ""))
    mech = _ask("Email de tu mecánico", cfg.get("mechanic_email", ""))
    mech_name = _ask("Nombre de tu mecánico", cfg.get("mechanic_name", "mecánico"))
    print("Contraseña de aplicación de Gmail (16 letras; Cuenta de Google → Seguridad → Contraseñas de aplicación).")
    app_pw = getpass.getpass("Pega la contraseña de aplicación (no se ve al escribir): ").replace(" ", "") \
        or cfg.get("smtp", {}).get("password", "")
    cfg.update({"mechanic_email": mech, "mechanic_name": mech_name,
                "default_recipients": sorted({me, mech} - {""}),
                "pais": (_ask("País donde trabajas normalmente (ES = España, DE = Alemania)", cfg.get("pais", "ES")) or "ES").upper(),
                "labour_rate": float(_ask("Tarifa de mano de obra €/h (mínimo 75 en España, 120 en Alemania)",
                                          str(cfg.get("labour_rate", 75)))),
                "smtp": {"host": "smtp.gmail.com", "port": 587, "user": me, "password": app_pw,
                         "from": f"Medikktion Diagnóstico <{me}>"}})
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{OK} config.json guardado")

    # 3. Firebase
    import firebase_admin
    from firebase_admin import auth, credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(key)))
    fs = FirebaseSetup(key)
    print(f"\nProyecto Firebase: {fs.project}")
    pending = []

    ok, info = fs.create_database()
    print(f"{OK if ok else WARN} Base de datos Firestore {'lista' if ok else 'no creada automáticamente'}")
    if not ok:
        pending.append("Firestore Database → Crear base de datos → modo producción → ubicación europe-west3 (Fráncfort)")
    ok, info = fs.enable_email_login()
    print(f"{OK if ok else WARN} Inicio de sesión por email {'activado' if ok else 'no activado automáticamente'}")
    if not ok:
        pending.append("Authentication → Comenzar → Correo electrónico/contraseña → Habilitar")

    users = {}
    for email, name in ((me, cfg["operator"] or "jefe"), (mech, mech_name)):
        if not email:
            continue
        try:
            pw, created = ensure_user(auth, email)
            users[email] = (name, pw)
            print(f"{OK} Cuenta {'creada' if created else 'actualizada'}: {email}")
        except Exception as e:  # noqa: BLE001
            print(f"{FAIL} No se pudo crear la cuenta {email}: {e}")

    rules = build_rules(sorted(users) or [me, mech])
    (folder.parent / "firebase" / "firestore.rules.generadas").write_text(rules, encoding="utf-8")
    ok, info = fs.deploy_rules(rules)
    print(f"{OK if ok else WARN} Reglas de seguridad {'publicadas' if ok else 'NO publicadas'}")
    if not ok:
        pending.append("Firestore Database → Reglas → pegar el contenido de firebase/firestore.rules.generadas → Publicar")

    gs, info = fs.android_config()
    code = app_code_from_google_services(gs) if gs else None
    if code:
        (folder / "codigo_app.txt").write_text(code + "\n", encoding="utf-8")
        print(f"{OK} App Android registrada. Código de la app guardado en codigo_app.txt")
    else:
        print(f"{WARN} No pude registrar la app Android automáticamente ({info[:80]})")
        pending.append("Configuración del proyecto → Tus apps → Android → paquete com.medikktion.app → descargar "
                       "google-services.json → ejecutar: python -m medikktion codigo-app google-services.json")

    # 4. Pruebas
    try:
        db = firestore.client()
        ref = db.collection("_comprobacion").document("portatil")
        ref.set({"t": firestore.SERVER_TIMESTAMP})
        ref.delete()
        print(f"{OK} Firestore: escritura y lectura correctas")
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} Firestore: {e}")
    ok, info = test_smtp(cfg["smtp"])
    print(f"{OK if ok else FAIL} Gmail: {'acceso correcto' if ok else info}")
    if ok and code:
        for email, (name, pw) in users.items():
            try:
                send_welcome(cfg["smtp"], email, name, pw, code)
                print(f"{OK} Email de bienvenida enviado a {email}")
            except Exception as e:  # noqa: BLE001
                print(f"{FAIL} Email a {email}: {e}")
    elif users:
        print("\nContraseñas (apúntalas, no se vuelven a mostrar):")
        for email, (_, pw) in users.items():
            print(f"   {email}: {pw}")

    if pending:
        print("\nQueda por hacer a mano en https://console.firebase.google.com (proyecto " + fs.project + "):")
        for i, p in enumerate(pending, 1):
            print(f"   {i}. {p}")
        print("Después vuelve a ejecutar: python -m medikktion configurar")
    else:
        print("\nTodo listo. Prueba: python -m medikktion demo --escenario fuchs --segundos 60")
    return 0


def check(folder: Path = Path(".")) -> int:
    """python -m medikktion comprobar: semáforo de todo el sistema."""
    import importlib
    import sys
    bad = 0
    print(f"Python {sys.version.split()[0]} ({64 if sys.maxsize > 2**32 else 32} bits)")
    for mod in ("can", "cantools", "isotp", "udsoncan", "obd", "reportlab", "firebase_admin"):
        try:
            importlib.import_module(mod)
            print(f"{OK} biblioteca {mod}")
        except ImportError:
            bad += 1
            print(f"{FAIL} falta {mod}: ejecuta instalar_windows.bat")
    cfg_path = folder / "config.json"
    if not cfg_path.exists():
        print(f"{FAIL} falta config.json: ejecuta python -m medikktion configurar")
        return 1
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(str(folder / cfg["firebase_credentials"])))
        list(firestore.client().collection("sessions").limit(1).stream())
        print(f"{OK} Firebase conectado")
    except Exception as e:  # noqa: BLE001
        bad += 1
        print(f"{FAIL} Firebase: {e}")
    ok, info = test_smtp(cfg.get("smtp", {}))
    print(f"{OK if ok else FAIL} Gmail: {'ok' if ok else info}")
    bad += not ok
    if sys.platform == "win32":
        from .rp1210 import list_adapters
        ad = list_adapters()
        print(f"{OK if ad else WARN} Lectores RP1210: {', '.join(a['vendor'] for a in ad) or 'ninguno instalado todavía'}")
    print("\nTodo correcto." if not bad else f"\n{bad} problema(s). Mándame esta pantalla.")
    return 1 if bad else 0
