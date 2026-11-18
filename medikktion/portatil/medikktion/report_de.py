"""Traducciones al alemán del informe PDF (estructura, valoración, mantenimiento,
gravedades, tipos de fallo FMI y nombres de las averías más comunes).
Los textos largos de procedimiento siguen en español (se indica en el informe)."""
from __future__ import annotations

import re

FMI_DE = {
    0: "Wert über dem Normalbereich (höchste Stufe)", 1: "Wert unter dem Normalbereich (höchste Stufe)",
    2: "Daten unregelmäßig, sporadisch oder falsch", 3: "Spannung zu hoch oder Kurzschluss nach Plus",
    4: "Spannung zu niedrig oder Kurzschluss nach Masse", 5: "Strom zu niedrig oder Leitungsunterbrechung",
    6: "Strom zu hoch oder Masseschluss", 7: "Mechanisches System reagiert nicht oder verstellt",
    8: "Frequenz, Pulsbreite oder Periode abnormal", 9: "Aktualisierungsrate abnormal (Kommunikation)",
    10: "Änderungsrate abnormal", 11: "Ursache unbekannt", 12: "Gerät oder Bauteil defekt",
    13: "Nicht kalibriert", 14: "Spezielle Herstelleranweisung", 15: "Wert über Normal (niedrige Stufe)",
    16: "Wert über Normal (mittlere Stufe)", 17: "Wert unter Normal (niedrige Stufe)",
    18: "Wert unter Normal (mittlere Stufe)", 19: "Netzwerkdaten fehlerhaft empfangen",
    20: "Daten nach oben abgedriftet", 21: "Daten nach unten abgedriftet", 31: "Zustand vorhanden",
}

SPN_DE = {
    100: "Motoröldruck", 98: "Motorölstand", 110: "Kühlmitteltemperatur", 111: "Kühlmittelstand",
    94: "Kraftstoffförderdruck", 97: "Wasser im Kraftstoff", 157: "Raildruck (Common Rail)", 102: "Ladedruck (Turbo)",
    105: "Ansauglufttemperatur", 168: "Batteriespannung / Steuergeräteversorgung", 158: "Zündungsspannung Steuergerät",
    190: "Motordrehzahl / Drehzahlsensor", 723: "Nockenwellensensor", 636: "Motorpositionssensor",
    **{650 + i: f"Injektor Zylinder {i}" for i in range(1, 13)}, 629: "Steuergerät (ECU) interner Fehler",
    639: "CAN-Netzwerk J1939 Nr. 1", 175: "Motoröltemperatur", 177: "Getriebeöltemperatur",
    1638: "Hydrauliköltemperatur", 91: "Gaspedalstellung", 27: "AGR-Ventilstellung", 641: "VTG-Turbo-Steller",
    3251: "Differenzdruck Partikelfilter (DPF)", 3719: "Rußbeladung DPF", 3216: "NOx-Sensor SCR-Eingang",
    3226: "NOx-Sensor SCR-Ausgang", 4364: "SCR-Wirkungsgrad", 3364: "AdBlue-Qualität", 1761: "AdBlue-Füllstand",
    5246: "SCR-Leistungsreduzierung (Inducement)", 1569: "Drehmomentreduzierung (Motorschutz)",
    171: "Umgebungstemperatur", 84: "Fahrgeschwindigkeit", 3361: "AdBlue-Dosiereinheit", 3509: "Sensorversorgung 5 V Nr. 1",
}

SEV_DE = {1: "Information", 2: "Gering", 3: "Mittel", 4: "Schwer", 5: "Kritisch"}
KIND_DE = {"active": "AKTIV", "emissions": "AKTIV (ABGAS)", "pending": "AUSSTEHEND", "permanent": "PERMANENT",
           "emissions_prev": "ABGAS FRÜHER", "history": "HISTORISCH"}

MAINT_DE = {
    "aceite_motor": "Motoröl und -filter", "filtros_combustible": "Kraftstofffilter (Vor- und Hauptfilter)",
    "filtro_aire": "Luftfilter (Haupt- und Sicherheitselement)", "filtros_hidraulicos": "Hydraulikfilter (Rücklauf und Vorsteuer)",
    "aceite_hidraulico": "Hydrauliköl komplett", "reductoras": "Öl Fahr- und Schwenkgetriebe",
    "transmision": "Getriebeöl und -filter", "refrigerante": "Motorkühlmittel", "valvulas": "Ventilspiel einstellen",
    "correa": "Keilriemen und Spanner", "filtro_adblue": "Filter AdBlue-Pumpe", "dpf": "Aschereinigung Partikelfilter",
}

# Frases fijas del informe (de más larga a más corta para que no se pisen)
PHRASES = {
    "Informe técnico": "Technischer Bericht",
    "Medikktion · diagnóstico de maquinaria pesada · documento de uso interno":
        "Medikktion · Diagnose für Baumaschinen · internes Dokument",
    "Índice de estado": "Zustandsindex", "Averías activas": "Aktive Fehler", "Históricas": "Historisch",
    "Centralitas": "Steuergeräte", "Coste estimado": "Geschätzte Kosten",
    "Valoración de compra": "Kaufbewertung", "Coste para dejarla a punto": "Kosten zur Instandsetzung",
    "Averías activas y permanentes": "Aktive und permanente Fehler", "Averías pendientes (riesgo)": "Ausstehende Fehler (Risiko)",
    "Servicio de entrada (mantenimiento)": "Eingangswartung", "Desplazamiento y diagnóstico": "Anfahrt und Diagnose",
    "Horas ocultas": "Verdeckte Stunden", "Rebaja recomendada": "Empfohlener Preisnachlass",
    "Precio que piden": "Angebotspreis", "Oferta máxima recomendada": "Empfohlenes Höchstgebot", "hasta": "bis",
    "No comprar sin una inspección a fondo en taller": "Nicht ohne gründliche Werkstattprüfung kaufen",
    "No compensa: reparaciones y horas ocultas superan el precio que piden":
        "Lohnt sich nicht: Reparaturen und verdeckte Stunden übersteigen den Angebotspreis",
    "Negociar el precio con este informe": "Preis mit diesem Bericht verhandeln", "Compra razonable": "Vertretbarer Kauf",
    "Integridad del horómetro": "Plausibilität des Betriebsstundenzählers",
    "Manipulación MUY PROBABLE": "Manipulation SEHR WAHRSCHEINLICH", "Sospechoso: revisar": "Verdächtig: prüfen",
    "Sin indicios de manipulación": "Keine Anzeichen von Manipulation", "Datos insuficientes": "Unzureichende Daten",
    "comprobaciones cruzadas": "Kreuzprüfungen", "índice de sospecha": "Verdachtsindex",
    "horas registradas": "erfasste Stunden", "horas reales estimadas": "geschätzte tatsächliche Stunden",
    "Uso y procedencia": "Nutzung und Herkunft", "Al ralentí": "Im Leerlauf", "de su vida": "der Lebensdauer",
    "Consumo medio de vida": "Durchschnittsverbrauch (Lebensdauer)", "Régimen medio de vida": "Mittlere Drehzahl (Lebensdauer)",
    "Uso anual": "Jährliche Nutzung", "Último borrado de averías": "Letzte Fehlerlöschung", "de motor": "Motorlaufzeit",
    "Con testigo de avería encendido": "Mit Fehlerleuchte an", "Placa · nº de serie": "Typenschild · Seriennummer",
    "Placa · año": "Typenschild · Baujahr", "Cuadro · horas": "Anzeige · Stunden", "Cuadro · km": "Anzeige · km",
    "Modificaciones detectadas": "Erkannte Veränderungen", "Mediciones registradas": "Aufgezeichnete Messwerte",
    "Aceite hidráulico": "Hydrauliköl", "Refrigerante": "Kühlmittel", "Presión de aceite": "Öldruck",
    "Régimen motor": "Motordrehzahl", "Últimos valores": "Letzte Werte", "Mantenimiento según horas": "Wartung nach Stunden",
    "Operación": "Arbeit", "Cada": "Alle", "Próximo a": "Fällig bei", "Faltan": "Noch", "Coste": "Kosten",
    "Averías": "Fehler", "Causas probables:": "Wahrscheinliche Ursachen:", "Procedimiento:": "Vorgehen:",
    "Piezas:": "Teile:", "Mano de obra:": "Arbeitszeit:", "Dificultad:": "Schwierigkeit:",
    "Recambio alternativo": "Nachbauteil", "original": "Originalteil", "Cuando saltó:": "Beim Auftreten:",
    "No requiere piezas": "Keine Teile erforderlich", "Unidades de control": "Steuergeräte",
    "Unidad": "Einheit", "Software / calibración": "Software / Kalibrierung", "Horas": "Stunden", "Dir.": "Adr.",
    "Act.": "Akt.", "Hist.": "Hist.", "Tarifas aplicadas": "Angewendete Sätze", "de mano de obra": "Arbeitslohn",
    "margen": "Aufschlag", "en piezas y": "auf Teile und", "en horas. Siempre redondeado al alza.":
        "auf Stunden. Immer aufgerundet.", "Generado el": "Erstellt am", "nº de serie": "Seriennummer",
    "Fotos y notas del taller": "Fotos und Werkstattnotizen", "refrigerante": "Kühlmittel", "carga": "Last",
    "sobrealim.": "Ladedruck", "ACTIVA": "AKTIV", "HISTÓRICA": "HISTORISCH", "hace": "vor", "Página": "Seite",
    "Importes orientativos (recambio alternativo – original, más mano de obra). Verificar referencias por número de serie.":
        "Richtwerte (Nachbau- bis Originalteil, zzgl. Arbeitslohn). Teilenummern anhand der Seriennummer prüfen. "
        "Detaillierte Ursachen und Arbeitsschritte auf Spanisch.",
    "España": "Spanien", "Alemania": "Deutschland",
}
_ORDERED = sorted(PHRASES.items(), key=lambda kv: -len(kv[0]))
_EVIDENCE_DE = {
    "Horas distintas entre centralitas": "Unterschiedliche Stunden zwischen Steuergeräten",
    "Horas coherentes entre centralitas": "Stunden zwischen Steuergeräten stimmig",
    "Régimen medio imposible": "Unmögliche mittlere Drehzahl", "Régimen medio plausible": "Mittlere Drehzahl plausibel",
    "Consumo medio demasiado alto para las horas": "Durchschnittsverbrauch zu hoch für die Stunden",
    "Consumo medio coherente": "Durchschnittsverbrauch stimmig",
    "Horas al ralentí mayores que las horas totales": "Leerlaufstunden größer als Gesamtstunden",
    "Horas al ralentí coherentes": "Leerlaufstunden stimmig", "Averías borradas hace muy poco": "Fehler kürzlich gelöscht",
    "Sin borrado reciente de averías": "Keine kürzliche Fehlerlöschung",
    "Testigo de avería encendido en su historial": "Fehlerleuchte in der Vorgeschichte an",
    "Las horas del cuadro no coinciden con la centralita": "Angezeigte Stunden stimmen nicht mit dem Steuergerät überein",
    "Horas del cuadro coherentes con la centralita": "Angezeigte Stunden stimmen mit dem Steuergerät überein",
    "Muy pocas horas para su antigüedad": "Sehr wenige Stunden für das Alter", "Uso anual normal": "Normale Jahresnutzung",
    "Averías permanentes que alguien borró": "Gelöschte permanente Fehler",
    "Horas MENORES que en una revisión anterior": "WENIGER Stunden als bei einer früheren Prüfung",
    "El nº de serie de la placa no coincide con la centralita": "Seriennummer Typenschild ≠ Steuergerät",
    "Nº de serie distinto entre centralitas": "Unterschiedliche Seriennummern zwischen Steuergeräten",
}


def tr(text: str) -> str:
    """Traduce las frases fijas conocidas (deja intacto el resto)."""
    if text in _EVIDENCE_DE:
        return _EVIDENCE_DE[text]
    for es, de in _ORDERED:
        if es in text:
            text = re.sub(re.escape(es), de, text)
    return text


def dtc_name(d: dict) -> str:
    return SPN_DE.get(d.get("spn") or -1, d.get("name", ""))


def fmi_text(d: dict) -> str:
    return FMI_DE.get(d["fmi"], d.get("fmi_text", "")) if d.get("fmi") is not None else d.get("fmi_text", "")
