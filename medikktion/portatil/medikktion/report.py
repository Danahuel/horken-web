"""Informe técnico en PDF (se adjunta al correo). Misma línea visual que la app:
grafito, oro champán y tipografía Inter."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

_FONTS = Path(__file__).parent / "fonts"
for _name, _file in (("Inter-Light", "Inter-Light.ttf"), ("Inter", "Inter-Regular.ttf"),
                     ("Inter-Medium", "Inter-Medium.ttf"), ("Inter-SemiBold", "Inter-SemiBold.ttf")):
    try:
        pdfmetrics.registerFont(TTFont(_name, str(_FONTS / _file)))
    except Exception:  # noqa: BLE001  si faltan las fuentes se usa Helvetica
        pass
_HAS_INTER = "Inter" in pdfmetrics.getRegisteredFontNames()
F_LIGHT = "Inter-Light" if _HAS_INTER else "Helvetica"
F_REG = "Inter" if _HAS_INTER else "Helvetica"
F_MED = "Inter-Medium" if _HAS_INTER else "Helvetica-Bold"
F_SEMI = "Inter-SemiBold" if _HAS_INTER else "Helvetica-Bold"

GRAPHITE = colors.HexColor("#0A0B0D")
INK = colors.HexColor("#15171A")
INK2 = colors.HexColor("#4C5159")
INK3 = colors.HexColor("#8B9099")
LINE = colors.HexColor("#E3E1DB")
PAPER2 = colors.HexColor("#F6F5F2")
GOLD = colors.HexColor("#A88445")
GOLD_LIGHT = colors.HexColor("#C9A86A")
OK = colors.HexColor("#23855D")
WARN = colors.HexColor("#B3741A")
DANGER = colors.HexColor("#C63A31")
SEV = {1: INK3, 2: INK2, 3: WARN, 4: colors.HexColor("#D0682C"), 5: DANGER}
SEV_TXT = {1: "Informativa", 2: "Leve", 3: "Moderada", 4: "Grave", 5: "Crítica"}
VERDICT = {"ok": OK, "sospechoso": WARN, "manipulado": DANGER, "sin_datos": INK3}

S_BODY = ParagraphStyle("b", fontName=F_REG, fontSize=8.8, leading=12.6, textColor=INK)
S_SMALL = ParagraphStyle("s", parent=S_BODY, fontSize=7.6, leading=10.5, textColor=INK2)
S_LABEL = ParagraphStyle("l", fontName=F_SEMI, fontSize=6.6, leading=9, textColor=INK3)
S_H2 = ParagraphStyle("h2", fontName=F_SEMI, fontSize=7.4, leading=10, textColor=GOLD, spaceBefore=14, spaceAfter=7)
S_TITLE = ParagraphStyle("t", fontName=F_LIGHT, fontSize=12.5, leading=16, textColor=INK)


def _n(v, d=1):
    if v is None:
        return "—"
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _spaced(text: str, html: bool = True) -> str:
    """Versalitas espaciadas; entre palabras, un hueco mayor que no se colapse."""
    gap = "&nbsp;&nbsp;&nbsp;" if html else "   "
    return gap.join(" ".join(w) for w in text.upper().split())


def _section(title: str) -> Paragraph:
    return Paragraph(f"—&nbsp;&nbsp;&nbsp;{_spaced(title)}", S_H2)


def _health(snapshot: dict) -> dict:
    h = snapshot.get("health")
    if isinstance(h, dict):
        return h
    from .analysis import health_index
    return health_index([d for d in snapshot["dtcs"] if d["active"]], snapshot["tamper"], snapshot.get("modifications", {}))


def _trend_chart(tr: dict, label: str, unit: str, factor: float = 1.0, decimals: int = 1, limit: float | None = None):
    w, h = 82 * mm, 34 * mm
    d = Drawing(w, h)
    v = [x * factor for x in tr["v"]]
    t = tr["t"]
    if len(v) < 2:
        return d
    lo, hi = min(v), max(v)
    pad = max((hi - lo) * 0.15, 0.05 if decimals >= 2 else 0.5)
    lo, hi = lo - pad, hi + pad
    top, bottom, left, right = h - 13, 9, 0, w - 22

    def X(tt):
        return left + (tt - t[0]) / max(1e-6, t[-1] - t[0]) * (right - left)

    def Y(vv):
        return bottom + (vv - lo) / (hi - lo) * (top - bottom)
    d.add(String(0, h - 6, _spaced(label, html=False), fontName=F_SEMI, fontSize=5.6, fillColor=INK3))
    for i in range(4):
        yy = bottom + (top - bottom) * i / 3
        d.add(Line(left, yy, right, yy, strokeColor=LINE, strokeWidth=0.4))
        d.add(String(right + 3, yy - 2, _n(lo + (hi - lo) * i / 3, 1), fontName=F_REG, fontSize=5.4, fillColor=INK3))
    if limit is not None and lo < limit < hi:
        d.add(Line(left, Y(limit), right, Y(limit), strokeColor=DANGER, strokeWidth=0.5, strokeDashArray=[2, 2]))
    d.add(PolyLine([c for i in range(len(v)) for c in (X(t[i]), Y(v[i]))], strokeColor=GOLD, strokeWidth=1.0))
    mins = round((t[-1] - t[0]) / 60)
    d.add(String(left, 0, f"−{mins} min", fontName=F_REG, fontSize=5.4, fillColor=INK3))
    d.add(String(right - 14, 0, "ahora", fontName=F_REG, fontSize=5.4, fillColor=INK3))
    d.add(String(right - 60, h - 6, f"{_n(v[-1], decimals)} {unit}", fontName=F_MED, fontSize=7, fillColor=INK))
    return d


def _header(canvas, doc, snapshot):
    canvas.saveState()
    W, H = A4
    canvas.setFillColor(GRAPHITE)
    canvas.rect(0, H - 30 * mm, W, 30 * mm, stroke=0, fill=1)
    # monograma
    x, y, s = 17 * mm, H - 19.5 * mm, 9 * mm
    canvas.setStrokeColor(GOLD_LIGHT)
    canvas.setLineWidth(0.9)
    p = canvas.beginPath()
    p.moveTo(x + s / 2, y + s)
    p.lineTo(x + s, y + s / 2)
    p.lineTo(x + s / 2, y)
    p.lineTo(x, y + s / 2)
    p.close()
    canvas.drawPath(p, stroke=1, fill=0)
    p = canvas.beginPath()
    p.moveTo(x + s * 0.3, y + s * 0.36)
    p.lineTo(x + s * 0.3, y + s * 0.62)
    p.lineTo(x + s * 0.5, y + s * 0.44)
    p.lineTo(x + s * 0.7, y + s * 0.62)
    p.lineTo(x + s * 0.7, y + s * 0.36)
    canvas.drawPath(p, stroke=1, fill=0)
    canvas.setFillColor(colors.HexColor("#EDEEF0"))
    canvas.setFont(F_LIGHT, 13)
    canvas.drawString(x + s + 5 * mm, y + s / 2 - 4.5, "  ".join("MEDIKKTION"))
    canvas.setFont(F_SEMI, 6.4)
    canvas.setFillColor(GOLD_LIGHT)
    canvas.drawRightString(W - 17 * mm, y + s / 2 + 1, _spaced("Informe técnico", html=False))
    canvas.setFillColor(colors.HexColor("#A2A8B0"))
    canvas.setFont(F_REG, 7)
    canvas.drawRightString(W - 17 * mm, y + s / 2 - 8, f"Ref. {snapshot.get('session_id', '')}")
    # pie
    canvas.setFont(F_REG, 6.6)
    canvas.setFillColor(INK3)
    canvas.drawString(17 * mm, 10 * mm, "Medikktion · diagnóstico de maquinaria pesada · documento de uso interno")
    canvas.drawRightString(W - 17 * mm, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


def build_pdf(snapshot: dict, path: str | Path) -> Path:
    path = Path(path)
    m, s, t = snapshot["machine"], snapshot["summary"], snapshot["tamper"]
    h = _health(snapshot)
    brand = (m.get("brand_name") or "").split(" (")[0]
    el = []

    # Portada: máquina + índice de estado
    when = (snapshot.get("updated_at") or "")[:16].replace("T", " ")
    head = Table([[
        [Paragraph(_spaced(brand), ParagraphStyle("br", fontName=F_SEMI, fontSize=7.5, textColor=GOLD, leading=10)),
         Spacer(1, 3),
         Paragraph(m.get("model") or "", ParagraphStyle("md", fontName=F_LIGHT, fontSize=26, leading=30, textColor=INK)),
         Spacer(1, 4),
         Paragraph(f"{m.get('machine_class_label', '')} · nº de serie {m.get('serial') or '—'}", S_SMALL),
         Paragraph(f"{snapshot.get('location') or ''} · {when} UTC"
                   + (f" · {snapshot.get('operator')}" if snapshot.get("operator") else ""), S_SMALL)],
        [Paragraph(_spaced("Índice de estado"), S_LABEL), Spacer(1, 2),
         Paragraph(str(h["score"]), ParagraphStyle("hs", fontName=F_LIGHT, fontSize=34, leading=38,
                                                   textColor={True: OK}.get(h["score"] >= 85,
                                                   GOLD if h["score"] >= 65 else WARN if h["score"] >= 40 else DANGER))),
         Paragraph(_spaced(h["label"]), ParagraphStyle("hl", fontName=F_SEMI, fontSize=6.6, textColor=INK2))],
    ]], colWidths=[128 * mm, 48 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("LINEBEFORE", (1, 0), (1, 0), 0.6, LINE), ("LEFTPADDING", (1, 0), (1, 0), 12)]))
    el += [head, Spacer(1, 10)]

    kpis = [[Paragraph(_spaced(x), S_LABEL) for x in ("Averías activas", "Históricas", "Centralitas", "Coste estimado")],
            [Paragraph(str(s["active_dtcs"]), ParagraphStyle("k", fontName=F_LIGHT, fontSize=18, leading=22,
                                                             textColor=SEV.get(s["max_severity"], INK) if s["active_dtcs"] else OK)),
             Paragraph(str(s["history_dtcs"]), ParagraphStyle("k2", fontName=F_LIGHT, fontSize=18, leading=22)),
             Paragraph(str(s["ecus"]), ParagraphStyle("k3", fontName=F_LIGHT, fontSize=18, leading=22)),
             Paragraph(f"{_n(s['repair_cost_min_eur'], 0)} – {_n(s['repair_cost_max_eur'], 0)} €",
                       ParagraphStyle("k4", fontName=F_LIGHT, fontSize=14, leading=22))]]
    kt = Table(kpis, colWidths=[38 * mm, 34 * mm, 34 * mm, 70 * mm])
    kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER2), ("TOPPADDING", (0, 0), (-1, 0), 8),
                            ("BOTTOMPADDING", (0, 1), (-1, 1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                            ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white)]))
    el.append(kt)

    # Horómetro
    el.append(_section("Integridad del horómetro"))
    vc = VERDICT.get(t["verdict"], INK3)
    el.append(Paragraph(f"<font color='{vc.hexval()}'>{t['label']}</font>",
                        ParagraphStyle("v", fontName=F_MED, fontSize=12, leading=15)))
    el.append(Paragraph(f"{t['checks']} comprobaciones cruzadas · índice de sospecha {t['score']}/100 · "
                        f"horas registradas {_n(t.get('reported_hours'))} h"
                        + (f" · <b>horas reales estimadas ≈ {_n(t['estimated_real_hours'], 0)} h</b>"
                           if t.get("estimated_real_hours") else ""), S_SMALL))
    el.append(Spacer(1, 6))
    for e in t["evidence"]:
        mark = "<font color='#23855D'>✓</font>" if e["level"] == "ok" else "<font color='#C63A31'>!</font>"
        el.append(Paragraph(f"{mark}&nbsp;&nbsp;<font name='{F_MED}'>{e['title']}</font> — {e['detail']}", S_BODY))
        el.append(Spacer(1, 3))
    mods = snapshot.get("modifications", {})
    if mods.get("findings"):
        el.append(_section("Modificaciones detectadas"))
        for f in mods["findings"]:
            el.append(Paragraph(f"<font color='#C63A31'>!</font>&nbsp;&nbsp;<font name='{F_MED}'>{f['title']}</font> — "
                                f"{f['detail']}", S_BODY))

    # Mediciones
    trend = snapshot.get("trend") or {}
    charts = [("hyd_oil_temp_c", "Aceite hidráulico", "°C", 1, 2, 85), ("coolant_c", "Refrigerante", "°C", 1, 2, 100),
              ("oil_pressure_kpa", "Presión de aceite", "bar", 0.01, 2, 2.5), ("rpm", "Régimen motor", "rpm", 1, 0, None)]
    charts = [c for c in charts if c[0] in trend and len(trend[c[0]].get("v", [])) > 2]
    if charts:
        el.append(_section("Mediciones registradas"))
        cells = [_trend_chart(trend[k], lbl, u, f, d, lim) for k, lbl, u, f, d, lim in charts]
        rows = [cells[i:i + 2] + [""] * (2 - len(cells[i:i + 2])) for i in range(0, len(cells), 2)]
        ct = Table(rows, colWidths=[88 * mm, 88 * mm])
        ct.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        el.append(ct)
    live = snapshot.get("live") or {}
    if live:
        rows, row = [], []
        for v in live.values():
            val, unit = (v["value"] / 100, "bar") if v["unit"] == "kPa" else (v["value"], v["unit"])
            row.append(Paragraph(f"<font color='#8B9099'>{v['label']}</font><br/>"
                                 f"<font name='{F_MED}' size='9.5'>{_n(val, 2)} {unit}</font>", S_SMALL))
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row + [""] * (4 - len(row)))
        lt = Table(rows, colWidths=[44 * mm] * 4)
        lt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        el += [Spacer(1, 4), Paragraph(_spaced("Últimos valores"), S_LABEL), Spacer(1, 3), lt]

    # Averías
    el.append(_section("Averías"))
    for d in snapshot["dtcs"]:
        sc = SEV[d["severity"]]
        parts = "; ".join(f"{p['nombre']} ({_n(p['min'], 0)}–{_n(p['max'], 0)} €)" for p in d["parts"]) or "No requiere piezas"
        rows = [
            [Paragraph(f"<font name='{F_SEMI}' color='{sc.hexval()}' size='6.6'>{_spaced(SEV_TXT[d['severity']])}</font>"
                       f"&nbsp;&nbsp;&nbsp;<font color='#8B9099' size='7'>{d['code']} · "
                       f"{'ACTIVA' if d['active'] else 'HISTÓRICA'} · {d['source_name']}</font>", S_BODY)],
            [Paragraph(f"<font name='{F_MED}' size='10.5'>{d['name']}</font> — {d['fmi_text']}", S_BODY)],
        ]
        if d.get("warning"):
            rows.append([Paragraph(f"<font color='#C63A31' name='{F_MED}'>{d['warning']}</font>", S_BODY)])
        if d["causes"]:
            rows.append([Paragraph(f"<font color='#8B9099'>Causas probables:</font> " + "; ".join(d["causes"]), S_SMALL)])
        rows.append([Paragraph(f"<font color='#8B9099'>Procedimiento:</font> "
                               + "  ".join(f"<b>{i + 1}</b>. {x}" for i, x in enumerate(d["steps"])), S_SMALL)])
        rows.append([Paragraph(f"<font color='#8B9099'>Piezas:</font> {parts} · <font color='#8B9099'>Mano de obra:</font> "
                               f"{_n(d['labour_hours'])} h · <font color='#8B9099'>Dificultad:</font> {d['difficulty']}/5 · "
                               f"<font name='{F_MED}' color='#A88445'>Total {_n(d['cost_min_eur'], 0)}–"
                               f"{_n(d['cost_max_eur'], 0)} €</font>", S_SMALL)])
        tb = Table(rows, colWidths=[176 * mm])
        tb.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 2, sc if d["active"] else LINE),
                                ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("BACKGROUND", (0, 0), (-1, -1), PAPER2)]))
        el += [KeepTogether(tb), Spacer(1, 6)]

    # Centralitas
    el.append(_section("Unidades de control"))
    rows = [[Paragraph(_spaced(x), S_LABEL) for x in ("Dir.", "Unidad", "Software / calibración", "Horas", "Act.", "Hist.")]]
    for e in snapshot["ecus"]:
        sw = list(e.get("software") or []) + [f"{c['cal_id']} · CVN {c['cvn']}" for c in e.get("calibrations") or []]
        rows.append([Paragraph(e["address_hex"], S_SMALL), Paragraph(e["name"], S_SMALL),
                     Paragraph("<br/>".join(sw) or "—", S_SMALL), Paragraph(_n(e.get("engine_hours")), S_SMALL),
                     Paragraph(str(e["active_dtcs"]), S_SMALL), Paragraph(str(e["history_dtcs"]), S_SMALL)])
    et = Table(rows, colWidths=[20 * mm, 50 * mm, 62 * mm, 20 * mm, 12 * mm, 12 * mm], repeatRows=1)
    et.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    el.append(et)

    el += [Spacer(1, 12), Paragraph(
        f"Importes orientativos (recambio alternativo – original, más mano de obra). Verificar referencias por número de serie. "
        f"{m.get('brand_note') or ''}", S_SMALL),
        Paragraph(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}.", S_SMALL)]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
                            topMargin=38 * mm, bottomMargin=18 * mm, title="Informe Medikktion",
                            author="Medikktion")
    doc.build(el, onFirstPage=lambda c, d: _header(c, d, snapshot), onLaterPages=lambda c, d: _header(c, d, snapshot))
    return path
