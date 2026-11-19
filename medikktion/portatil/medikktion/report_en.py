"""Traducciones al inglés del informe PDF (estructura, valoración, mantenimiento,
gravedades, tipos de fallo FMI y nombres de las averías más comunes).
Los textos largos de procedimiento siguen en español (se indica en el informe)."""
from __future__ import annotations

import re

FMI_EN = {
    0: "Data valid but above normal range (most severe)", 1: "Data valid but below normal range (most severe)",
    2: "Data erratic, intermittent or incorrect", 3: "Voltage above normal or shorted to high source",
    4: "Voltage below normal or shorted to low source", 5: "Current below normal or open circuit",
    6: "Current above normal or grounded circuit", 7: "Mechanical system not responding or out of adjustment",
    8: "Abnormal frequency, pulse width or period", 9: "Abnormal update rate (communication)",
    10: "Abnormal rate of change", 11: "Root cause not known", 12: "Bad intelligent device or component",
    13: "Out of calibration", 14: "Special instructions", 15: "Above normal (least severe)",
    16: "Above normal (moderately severe)", 17: "Below normal (least severe)",
    18: "Below normal (moderately severe)", 19: "Received network data in error",
    20: "Data drifted high", 21: "Data drifted low", 31: "Condition exists",
}

SPN_EN = {
    100: "Engine oil pressure", 98: "Engine oil level", 110: "Engine coolant temperature", 111: "Coolant level",
    94: "Fuel delivery pressure", 97: "Water in fuel", 157: "Rail pressure (common rail)", 102: "Boost pressure (turbo)",
    105: "Intake manifold temperature", 168: "Battery / ECU supply voltage", 158: "ECU key-switch voltage",
    190: "Engine speed / speed sensor", 723: "Camshaft sensor", 636: "Engine position sensor",
    **{650 + i: f"Injector cylinder {i}" for i in range(1, 13)}, 629: "Controller (ECU) internal fault",
    639: "J1939 CAN network #1", 175: "Engine oil temperature", 177: "Transmission oil temperature",
    1638: "Hydraulic oil temperature", 91: "Accelerator pedal position", 27: "EGR valve position", 641: "VGT turbo actuator",
    3251: "DPF differential pressure", 3719: "DPF soot load", 3216: "NOx sensor SCR inlet",
    3226: "NOx sensor SCR outlet", 4364: "SCR conversion efficiency", 3364: "DEF (AdBlue) quality", 1761: "DEF (AdBlue) level",
    5246: "SCR operator inducement (derate)", 1569: "Engine protection torque derate",
    171: "Ambient air temperature", 84: "Vehicle speed", 3361: "DEF dosing unit", 3509: "Sensor supply 5 V #1",
}

SEV_EN = {1: "Information", 2: "Minor", 3: "Moderate", 4: "Serious", 5: "Critical"}
KIND_EN = {"active": "ACTIVE", "emissions": "ACTIVE (EMISSIONS)", "pending": "PENDING", "permanent": "PERMANENT",
           "emissions_prev": "EMISSIONS PREVIOUS", "history": "HISTORY", "prueba": "PUMP TEST"}

MAINT_EN = {
    "aceite_motor": "Engine oil and filter", "filtros_combustible": "Fuel filters (pre and main)",
    "filtro_aire": "Air filter (primary and safety)", "filtros_hidraulicos": "Hydraulic filters (return and pilot)",
    "aceite_hidraulico": "Hydraulic oil change", "reductoras": "Final drive and swing drive oil",
    "transmision": "Transmission oil and filter", "refrigerante": "Engine coolant", "valvulas": "Valve lash adjustment",
    "correa": "Drive belt and tensioner", "filtro_adblue": "DEF pump filter", "dpf": "DPF ash cleaning",
}

# Frases fijas del informe (de más larga a más corta para que no se pisen)
PHRASES = {
    "Informe técnico": "Technical report",
    "Medikktion · diagnóstico de maquinaria pesada · documento de uso interno":
        "Medikktion · heavy machinery diagnostics · internal document",
    "Índice de estado": "Condition index", "Averías activas": "Active faults", "Históricas": "History",
    "Centralitas": "Control units", "Coste estimado": "Estimated cost",
    "Valoración de compra": "Purchase assessment", "Coste para dejarla a punto": "Cost to make it ready",
    "Averías activas y permanentes": "Active and permanent faults", "Averías pendientes (riesgo)": "Pending faults (risk)",
    "Servicio de entrada (mantenimiento)": "Entry service (maintenance)", "Desplazamiento y diagnóstico": "Travel and diagnosis",
    "Horas ocultas": "Hidden hours", "Rebaja recomendada": "Recommended discount",
    "Precio que piden": "Asking price", "Oferta máxima recomendada": "Recommended maximum offer", "hasta": "up to",
    "No comprar sin una inspección a fondo en taller": "Do not buy without a full workshop inspection",
    "No compensa: reparaciones y horas ocultas superan el precio que piden":
        "Not worth it: repairs and hidden hours exceed the asking price",
    "Negociar el precio con este informe": "Negotiate the price with this report", "Compra razonable": "Reasonable purchase",
    "Integridad del horómetro": "Hour meter integrity",
    "Manipulación MUY PROBABLE": "Tampering VERY LIKELY", "Sospechoso: revisar": "Suspicious: check",
    "Sin indicios de manipulación": "No signs of tampering", "Datos insuficientes": "Insufficient data",
    "comprobaciones cruzadas": "cross-checks", "índice de sospecha": "suspicion index",
    "horas registradas": "recorded hours", "horas reales estimadas": "estimated real hours",
    "Uso y procedencia": "Usage and provenance", "Al ralentí": "At idle", "de su vida": "of its life",
    "Consumo medio de vida": "Lifetime average fuel use", "Régimen medio de vida": "Lifetime average engine speed",
    "Uso anual": "Annual usage", "Último borrado de averías": "Last fault clear", "de motor": "engine time",
    "Con testigo de avería encendido": "With warning lamp on", "Placa · nº de serie": "Plate · serial no.",
    "Placa · año": "Plate · year", "Cuadro · horas": "Dash · hours", "Cuadro · km": "Dash · km",
    "Modificaciones detectadas": "Detected modifications", "Mediciones registradas": "Recorded measurements",
    "Aceite hidráulico": "Hydraulic oil", "Refrigerante": "Coolant", "Presión de aceite": "Oil pressure",
    "Régimen motor": "Engine speed", "Últimos valores": "Latest values", "Mantenimiento según horas": "Maintenance by hours",
    "Operación": "Task", "Cada": "Every", "Próximo a": "Next at", "Faltan": "Remaining", "Coste": "Cost",
    "Averías": "Faults", "Causas probables:": "Probable causes:", "Procedimiento:": "Procedure:",
    "Piezas:": "Parts:", "Mano de obra:": "Labour:", "Dificultad:": "Difficulty:",
    "Recambio alternativo": "Aftermarket part", "original": "OEM", "Cuando saltó:": "When it occurred:",
    "No requiere piezas": "No parts required", "Unidades de control": "Control units",
    "Unidad": "Unit", "Software / calibración": "Software / calibration", "Horas": "Hours", "Dir.": "Addr.",
    "Act.": "Act.", "Hist.": "Hist.", "Tarifas aplicadas": "Rates applied", "de mano de obra": "labour",
    "margen": "margin", "en piezas y": "on parts and", "en horas. Siempre redondeado al alza.":
        "on hours. Always rounded up.", "Generado el": "Generated on", "nº de serie": "serial no.",
    "Fotos y notas del taller": "Workshop photos and notes", "refrigerante": "coolant", "carga": "load",
    "sobrealim.": "boost", "ACTIVA": "ACTIVE", "HISTÓRICA": "HISTORY", "hace": "ago", "Página": "Page",
    "Importes orientativos (recambio alternativo – original, más mano de obra). Verificar referencias por número de serie.":
        "Indicative amounts (aftermarket – OEM part, plus labour). Verify part numbers by serial number. "
        "Detailed causes and procedures are in Spanish.",
    "España": "Spain", "Alemania": "Germany",
}
_ORDERED = sorted(PHRASES.items(), key=lambda kv: -len(kv[0]))
# Frases de los detalles (comprobaciones del horómetro, modificaciones, centralitas y medidas)
PHRASES.update({
    "Las centralitas cuentan las horas a la vez; una diferencia grande indica que una se ha rebajado o se ha cambiado una centralita.":
        "Control units count hours simultaneously; a large difference means one was wound back or a unit was replaced.",
    "Diferencia de": "Difference of", "centralitas coinciden": "control units match", "diferencia": "difference",
    "Revoluciones totales": "Total revolutions", "rpm de media durante toda su vida": "rpm average over its whole life",
    "Con un régimen medio típico de 1.400 rpm corresponderían unas": "At a typical 1,400 rpm average it would have about",
    "el contador de revoluciones pudo reiniciarse": "the revolution counter may have been reset",
    "rpm de media de vida": "rpm lifetime average", "Régimen medio de": "Average engine speed of",
    "lo normal es": "normal is", "Para ": "For ",
    "Indica que la máquina tiene más horas de las que marca": "The machine has more hours than it shows",
    "según el gasoil consumido": "based on fuel burned", "El contador de combustible pudo reiniciarse.": "The fuel counter may have been reset.",
    "Prueba directa de manipulación o cambio de centralita.": "Direct proof of tampering or a replaced control unit.",
    "marcaba": "showed", "y ahora": "and now", "El ": "On ",
    "La centralita registra": "The control unit records", "h al ralentí pero solo": "h at idle but only",
    "h en total. Es imposible: el horómetro total se ha rebajado y el contador de ralentí no.":
        "h in total. Impossible: the total hour meter was wound back but the idle counter was not.",
    "h al ralentí": "h at idle", "de su vida": "of its life",
    "El último borrado de códigos fue hace": "Fault codes were last cleared", "h de motor": "engine hours ago",
    "Antes de una compra es una señal de alerta: trabaje la máquina un rato y vuelva a leer.":
        "Before a purchase this is a red flag: work the machine for a while and read it again.",
    "Último borrado hace": "Last clear", "Ha trabajado": "It has run", "con el testigo de avería encendido": "with the warning lamp on",
    "centralita de motor": "engine control unit", "centralita": "control unit", "Cuadro": "Dash", "h/año desde": "h/year since", "h/año": "h/year",
    "Lo habitual en obra es": "Typical on site is", "Puede haber estado parada… o tener el horómetro rebajado.":
        "It may have been parked… or the hour meter wound back.", "en unos": "in about", "años": "years",
    "La centralita guarda": "The control unit stores", "avería(s) permanente(s) que ya no aparecen como activas":
        "permanent fault(s) no longer shown as active",
    "Se borraron sin reparar; volverán a salir al trabajar.": "They were cleared without repair; they will return once the machine works.",
    "Se borraron sin reparar": "They were cleared without repair",
    "Placa": "Plate", "La centralita puede proceder de otra máquina.": "The control unit may come from another machine.",
    "Una centralita procede de otra máquina (sustitución o 'trasplante', método habitual para reiniciar horas).":
        "A control unit comes from another machine (replacement or 'transplant', a common way to reset hours).",
    "Motor #1 (ECM)": "Engine #1 (ECM)", "Cuadro de instrumentos": "Instrument cluster",
    "Postratamiento escape #1 (DPF/SCR)": "Aftertreatment #1 (DPF/SCR)", "Controlador del fabricante": "Manufacturer controller",
    "hidráulico/implementos": "hydraulics/implements", "Gestión · Control maquina": "Machine management",
    "Temperatura aceite hidráulico": "Hydraulic oil temperature", "Consumo instantáneo": "Fuel rate",
    "Temperatura aceite transmisión": "Transmission oil temperature", "Tensión batería": "Battery voltage",
    "Nivel AdBlue (DEF)": "DEF (AdBlue) level", "Presión de sobrealimentación": "Boost pressure",
    "Temperatura colector admisión": "Intake manifold temperature", "Temperatura ambiente": "Ambient temperature",
    "Nivel combustible": "Fuel level", "Temperatura aceite motor": "Engine oil temperature",
    "Temperatura refrigerante": "Coolant temperature", "Presión aceite motor": "Engine oil pressure", "Par motor real": "Actual engine torque",
    "Excavadora 14-25 t": "Excavator 14-25 t", "Manipuladora de material": "Material handler",
    "Trituradora / biotrituradora": "Shredder", "Rodillo compactador": "Compaction roller", "Demostración": "Demo",
    # Prueba de bombas
    "Prueba de bombas hidráulicas": "Hydraulic pump test", "Bombas: hay que actuar": "Pumps: action needed",
    "Bombas: justas, vigilar": "Pumps: borderline, monitor", "Bombas en buen estado (presión)": "Pumps in good condition (pressure)",
    "Prueba sin lecturas": "Test without readings", "Paso": "Step", "Canal": "Channel", "Lectura": "Reading",
    "Referencia": "Reference", "Estado": "Status", "Fuente": "Source", "Bien": "Good", "Justa": "Borderline",
    "Baja": "Low", "Alta": "High", "manómetro": "gauge", "Bomba 1": "Pump 1", "Bomba 2": "Pump 2", "Pilotaje": "Pilot",
    "Presión de reposo": "Standby pressure", "Alivio principal · bomba 1": "Main relief · pump 1",
    "Alivio principal · bomba 2": "Main relief · pump 2", "Presión de pilotaje": "Pilot pressure",
    "Diferencia entre bombas al alivio": "Difference between pumps at relief",
    "(más de un 5 %: la más baja rinde menos)": "(over 5 %: the lower one is weaker)", "(iguales)": "(equal)",
    "La presión indica si bombas y válvulas aguantan; el caudal (rapidez) se comprueba con tiempos de ciclo o caudalímetro.":
        "Pressure shows whether pumps and valves hold; flow (speed) is checked with cycle times or a flow meter.",
    "Lecturas de la centralita.": "Readings from the control unit.", "Lecturas de manómetro de taller.": "Workshop gauge readings.",
    "Lecturas de centralita y de manómetro.": "Control unit and gauge readings.",
    "Referencias del manual de la máquina.": "References from the machine manual.",
    "Referencias orientativas": "Indicative references", "confirmar con el manual de la máquina.": "confirm with the machine manual.",
    "Lo que sale de la prueba aparece en Averías con su procedimiento y coste.":
        "Findings from the test appear under Faults with procedure and cost.",
    "no llega a la presión de alivio": "does not reach relief pressure", "Prueba de presión:": "Pressure test:",
    "Las dos bombas se quedan bajas por igual": "Both pumps equally low", "Presión de reposo alta": "High standby pressure",
    "Presión de pilotaje baja": "Low pilot pressure", "por encima de lo normal": "above normal", "bar de": "bar of",
    "Prueba de bombas": "Pump test", "PRUEBA DE BOMBAS": "PUMP TEST",
})
_ORDERED = sorted(PHRASES.items(), key=lambda kv: -len(kv[0]))
_EVIDENCE_EN = {
    "Horas distintas entre centralitas": "Hours differ between control units",
    "Horas coherentes entre centralitas": "Hours consistent between control units",
    "Régimen medio imposible": "Impossible average engine speed", "Régimen medio plausible": "Plausible average engine speed",
    "Consumo medio demasiado alto para las horas": "Average fuel use too high for the hours",
    "Consumo medio coherente": "Average fuel use consistent",
    "Horas al ralentí mayores que las horas totales": "Idle hours greater than total hours",
    "Horas al ralentí coherentes": "Idle hours consistent", "Averías borradas hace muy poco": "Faults cleared very recently",
    "Sin borrado reciente de averías": "No recent fault clear",
    "Testigo de avería encendido en su historial": "Warning lamp on in its history",
    "Las horas del cuadro no coinciden con la centralita": "Dash hours do not match the control unit",
    "Horas del cuadro coherentes con la centralita": "Dash hours match the control unit",
    "Muy pocas horas para su antigüedad": "Very few hours for its age", "Uso anual normal": "Normal annual usage",
    "Averías permanentes que alguien borró": "Permanent faults someone cleared",
    "Horas MENORES que en una revisión anterior": "FEWER hours than at a previous inspection",
    "El nº de serie de la placa no coincide con la centralita": "Plate serial number ≠ control unit",
    "Nº de serie distinto entre centralitas": "Different serial numbers between control units",
}


def tr(text: str) -> str:
    """Traduce las frases fijas conocidas (deja intacto el resto)."""
    if text in _EVIDENCE_EN:
        return _EVIDENCE_EN[text]
    for es, en in _ORDERED:
        if es in text:
            pat = ("(?<!\\w)" if es[0].isalnum() else "") + re.escape(es) + ("(?!\\w)" if es[-1].isalnum() else "")
            text = re.sub(pat, lambda _m, en=en: en, text)
    return text


def dtc_name(d: dict) -> str:
    if d.get("kind") == "prueba":
        return tr(d.get("name", ""))
    if d.get("name_language") == "en":
        return d.get("name", "")
    return SPN_EN.get(d.get("spn") or -1, d.get("name", ""))


def fmi_text(d: dict) -> str:
    if d.get("kind") == "prueba":
        return tr(d.get("fmi_text", ""))
    return FMI_EN.get(d["fmi"], d.get("fmi_text", "")) if d.get("fmi") is not None else d.get("fmi_text", "")
