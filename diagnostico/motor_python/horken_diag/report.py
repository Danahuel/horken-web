"""Informe PDF del diagnóstico (se adjunta al email)."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SEV_COLORS = {1: "#2e7d32", 2: "#689f38", 3: "#f9a825", 4: "#ef6c00", 5: "#c62828"}
VERDICT_COLORS = {"ok": "#2e7d32", "sospechoso": "#ef6c00", "manipulado": "#c62828", "sin_datos": "#616161"}


def _fmt(v, unit=""):
    if v is None:
        return "—"
    return f"{v:,.1f}{(' ' + unit) if unit else ''}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_pdf(snapshot: dict, path: str | Path) -> Path:
    path = Path(path)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=colors.HexColor("#1a1a1a"), fontSize=18)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor("#b26a00"), fontSize=13, spaceBefore=8)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#555555"))
    m, s, t = snapshot["machine"], snapshot["summary"], snapshot["tamper"]

    el = [Paragraph("HORKEN · Informe de diagnóstico", h1),
          Paragraph(f"{m.get('brand_name')} {m.get('model')} · Nº serie {m.get('serial') or '—'} · "
                    f"{m.get('machine_class_label')}<br/>Fecha: {snapshot.get('updated_at', '')[:19].replace('T', ' ')} UTC · "
                    f"Operador: {snapshot.get('operator', '—')} · Ubicación: {snapshot.get('location', '—')}", body),
          Spacer(1, 4 * mm)]

    summary = [["Averías activas", "Históricas", "Centralitas", "Gravedad máx.", "Coste estimado"],
               [s["active_dtcs"], s["history_dtcs"], s["ecus"], f"{s['max_severity']}/5",
                f"{s['repair_cost_min_eur']:,} – {s['repair_cost_max_eur']:,} €".replace(",", ".")]]
    tb = Table(summary, colWidths=[34 * mm] * 5)
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]))
    el += [tb, Spacer(1, 3 * mm)]

    # Horas / manipulación
    el.append(Paragraph("Horas, kilómetros y manipulación", h2))
    vc = VERDICT_COLORS.get(t["verdict"], "#616161")
    el.append(Paragraph(f"<font color='{vc}'><b>{t['label']}</b></font> · puntuación {t['score']}/100 · "
                        f"{t['checks']} comprobaciones · horas marcadas {_fmt(t.get('reported_hours'), 'h')}"
                        + (f" · <b>horas reales estimadas ≈ {_fmt(t['estimated_real_hours'], 'h')}</b>"
                           if t.get("estimated_real_hours") else ""), body))
    for e in t["evidence"]:
        mark = "<font color='#2e7d32'>[OK]</font>" if e["level"] == "ok" else "<font color='#c62828'>[!]</font>"
        el.append(Paragraph(f"{mark} <b>{e['title']}</b>: {e['detail']}", body))
    mods = snapshot.get("modifications", {})
    if mods.get("findings"):
        el.append(Paragraph("Modificaciones de centralitas", h2))
        for f in mods["findings"]:
            el.append(Paragraph(f"<font color='#c62828'>[!]</font> <b>{f['title']}</b>: {f['detail']}", body))

    # Averías
    el.append(Paragraph("Averías", h2))
    for d in snapshot["dtcs"]:
        sev = SEV_COLORS[d["severity"]]
        parts = "; ".join(f"{p['nombre']} ({p['min']}–{p['max']} €)" for p in d["parts"]) or "—"
        rows = [
            [Paragraph(f"<font color='{sev}'><b>Gravedad {d['severity']}/5</b></font> <b>{d['code']}</b> · "
                       f"{'ACTIVA' if d['active'] else 'Histórica'} · {d['occurrences']} veces · {d['source_name']}", body)],
            [Paragraph(f"<b>{d['name']}</b> — {d['fmi_text']} <font color='#777777'>({d['system']})</font>", body)],
        ]
        if d.get("warning"):
            rows.append([Paragraph(f"<font color='#c62828'><b>ATENCIÓN: {d['warning']}</b></font>", body)])
        if d["causes"]:
            rows.append([Paragraph("<b>Causas probables:</b> " + "; ".join(d["causes"]), body)])
        rows.append([Paragraph("<b>Pasos:</b> " + " - ".join(f"{i + 1}. {x}" for i, x in enumerate(d["steps"])), body)])
        rows.append([Paragraph(f"<b>Piezas:</b> {parts}<br/><b>Dificultad:</b> {d['difficulty']}/5 "
                               f" · <b>Mano de obra:</b> {d['labour_hours']} h · "
                               f"<b>Coste total estimado:</b> {d['cost_min_eur']}–{d['cost_max_eur']} €", body)])
        tbl = Table(rows, colWidths=[176 * mm])
        tbl.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(sev)),
                                 ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor(sev)),
                                 ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        el += [KeepTogether(tbl), Spacer(1, 2 * mm)]

    # Centralitas
    el.append(Paragraph("Centralitas detectadas", h2))
    rows = [["Dir.", "Centralita", "Software", "Horas", "Activas", "Hist."]]
    for e in snapshot["ecus"]:
        rows.append([e["address_hex"], Paragraph(e["name"], small), Paragraph(", ".join(e["software"]) or "—", small),
                     _fmt(e.get("engine_hours")), e["active_dtcs"], e["history_dtcs"]])
    tb = Table(rows, colWidths=[14 * mm, 52 * mm, 60 * mm, 22 * mm, 14 * mm, 14 * mm])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el.append(tb)

    # Datos en vivo
    el.append(Paragraph("Últimos valores en vivo", h2))
    rows = [[v["label"], _fmt(v["value"], v["unit"])] for v in snapshot["live"].values()]
    if rows:
        tb = Table(rows, colWidths=[90 * mm, 40 * mm])
        tb.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey)]))
        el.append(tb)

    el += [Spacer(1, 4 * mm), Paragraph(
        "Costes orientativos (recambio alternativo - original + mano de obra). Verificar referencias por nº de serie. "
        f"Marca: {m.get('brand_note')}", small)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
                      topMargin=14 * mm, bottomMargin=14 * mm, title="Informe Horken").build(el)
    return path
