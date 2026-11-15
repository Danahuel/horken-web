"""Envío del informe por email (Gmail SMTP, gratis, sin plan de pago de Firebase).

En Gmail: Cuenta de Google → Seguridad → Verificación en 2 pasos → Contraseñas
de aplicación → crear una para "Horken" y ponerla en config.json.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path


def send_report(smtp: dict, recipients: list[str], snapshot: dict, pdf_path: Path) -> None:
    recipients = sorted({r.strip() for r in recipients if r and "@" in r})
    if not recipients:
        raise ValueError("No hay destinatarios")
    m, s, t = snapshot["machine"], snapshot["summary"], snapshot["tamper"]
    msg = EmailMessage()
    msg["Subject"] = (f"[Horken] {m.get('brand_name')} {m.get('model')} {m.get('serial')} · "
                      f"{s['active_dtcs']} averías activas · {t['label']}")
    msg["From"] = smtp.get("from") or smtp["user"]
    msg["To"] = ", ".join(recipients)
    lines = [f"Máquina: {m.get('brand_name')} {m.get('model')} · Nº serie {m.get('serial')}",
             f"Horas marcadas: {t.get('reported_hours')} · {t['label']} ({t['score']}/100)",
             f"Averías activas: {s['active_dtcs']} · históricas: {s['history_dtcs']}",
             f"Coste estimado: {s['repair_cost_min_eur']} – {s['repair_cost_max_eur']} €", ""]
    for d in snapshot["dtcs"]:
        if d["active"]:
            lines.append(f"[{d['severity']}/5] {d['code']} {d['name']} — {d['fmi_text']} ({d['source_name']})")
    lines += ["", "Informe completo en el PDF adjunto."]
    msg.set_content("\n".join(lines))
    msg.add_attachment(Path(pdf_path).read_bytes(), maintype="application", subtype="pdf",
                       filename=Path(pdf_path).name)
    with smtplib.SMTP(smtp.get("host", "smtp.gmail.com"), int(smtp.get("port", 587)), timeout=30) as s_:
        s_.starttls()
        s_.login(smtp["user"], smtp["password"])
        s_.send_message(msg)
