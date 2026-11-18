"""Importador del diccionario oficial SAE J1939 Digital Annex (J1939DA).

SAE lo vende como un Excel con todos los parámetros (SPN) y mensajes (PGN)
estándar: decenas de miles de SPN con nombre, descripción y unidades. No se
puede incluir en el programa (licencia de SAE), pero si lo compras:

    python -m medikktion importar-j1939da J1939DA_2025.xlsx

y desde ese momento cualquier avería estándar sale con su nombre oficial,
aunque no esté entre las que tienen procedimiento propio. El archivo generado
(kb/spn_da.json) se queda solo en tu portátil.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path(__file__).parent / "kb" / "spn_da.json"


def _norm(h) -> str:
    return re.sub(r"[^a-z]", "", str(h or "").lower())


def import_xlsx(path: str | Path, out: Path = OUT) -> int:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    table: dict[str, dict] = {}
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header_idx, cols = None, {}
        for i, row in enumerate(rows):
            names = [_norm(c) for c in row]
            if "spn" in names and any(n in ("spnname", "spnlabel", "name", "parametername") for n in names):
                cols = {n: j for j, n in enumerate(names)}
                header_idx = i
                break
            if i > 30:
                break
        if header_idx is None:
            continue
        c_spn = cols["spn"]
        c_name = next(cols[n] for n in ("spnname", "spnlabel", "parametername", "name") if n in cols)
        c_desc = next((cols[n] for n in ("spndescription", "description", "parameterdescription") if n in cols), None)
        c_unit = next((cols[n] for n in ("units", "unit", "spnunits") if n in cols), None)
        c_pgn = cols.get("pgn")
        for row in rows:
            try:
                spn = int(float(row[c_spn]))
            except (TypeError, ValueError, IndexError):
                continue
            name = str(row[c_name] or "").strip()
            if not name:
                continue
            e = {"n": name}
            if c_desc is not None and row[c_desc]:
                e["d"] = str(row[c_desc]).strip()[:400]
            if c_unit is not None and row[c_unit]:
                e["u"] = str(row[c_unit]).strip()
            if c_pgn is not None and row[c_pgn] not in (None, ""):
                try:
                    e["p"] = int(float(row[c_pgn]))
                except (TypeError, ValueError):
                    pass
            table.setdefault(str(spn), e)
    out.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    return len(table)
