"""Ingestion + normalization of arbitrary spreadsheets.

Built on librarian's intake substrate: ``parse_document`` turns any uploaded
file (xlsx/csv/tsv/json/…) into located blocks, ``profile_document`` infers the
column schema, and from there we map messy human columns onto our canonical
inventory model, classify each item, and dedup/group equivalent items.

Works with or without an LLM:
* with OpenAI → smart column mapping + classification;
* without    → header-keyword heuristics (ES/EN) + rule-based classification.
"""
from __future__ import annotations

import csv
import io
import os

from sqlalchemy.orm import Session

from .inventory import record_movement, resolve_or_create_item
from .llm import get_llm

# Canonical fields we try to recover from any spreadsheet.
CANONICAL_FIELDS = ["name", "quantity", "unit", "category", "party", "location", "date", "notes", "barcode"]

_HEADER_HINTS: dict[str, list[str]] = {
    "barcode": ["barcode", "codigo", "código", "code", "sku", "ref", "referencia", "id"],
    "name": ["item", "name", "descripcion", "description", "product", "producto", "articulo",
             "artículo", "insumo", "supply", "material", "donacion", "donación"],
    "quantity": ["qty", "quantity", "cantidad", "cant", "amount", "units", "unidades", "stock",
                 "existencia", "total"],
    "unit": ["unit", "unidad", "uom", "medida", "presentacion", "presentación", "empaque"],
    "category": ["category", "categoria", "categoría", "tipo", "type", "clase", "rubro"],
    "party": ["supplier", "proveedor", "donor", "donante", "from", "origen", "recipient",
              "destinatario", "to", "destino", "entidad"],
    "location": ["location", "ubicacion", "ubicación", "almacen", "almacén", "warehouse",
                 "bodega", "lugar", "deposito", "depósito"],
    "date": ["date", "fecha", "fecha de ingreso"],
    "notes": ["note", "nota", "observacion", "observación", "comment", "comentario", "detalle"],
}


# --- table extraction ----------------------------------------------------
def _grids_from_librarian(filename: str, data: bytes) -> list[list[list[str]]]:
    """Use librarian to parse the file, then recover row grids from its blocks."""
    from librarian.readers.registry import parse_document

    parsed = parse_document(
        doc_id="upload", title=filename, uri=filename, name=filename, data=data
    )
    grids: list[list[list[str]]] = []
    for block in parsed.blocks:
        if block.type in {"table", "sheet"}:
            grid = _pipe_grid(block.text)
            if grid:
                grids.append(grid)
    return grids


def _pipe_grid(text: str) -> list[list[str]] | None:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2 or " | " not in lines[0]:
        return None
    rows = [[c.strip() for c in ln.split(" | ")] for ln in lines]
    width = len(rows[0])
    rows = [r for r in rows if len(r) == width]
    return rows if len(rows) >= 2 else None


def _grids_direct(filename: str, data: bytes) -> list[list[list[str]]]:
    """Full-fidelity fallback for CSV/XLSX (no row cap)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in {".csv", ".tsv", ".txt"}:
        text = data.decode("utf-8", errors="replace")
        delim = "\t" if ext == ".tsv" or "\t" in text.splitlines()[0:1] else ","
        rows = [[(c or "").strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
        rows = [r for r in rows if any(c for c in r)]
        return [rows] if len(rows) >= 2 else []
    if ext in {".xlsx", ".xlsm"}:
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception:
            return []
        grids = []
        for sheet in wb.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if c is None else str(c).strip() for c in row]
                if any(cells):
                    rows.append(cells)
            if len(rows) >= 2:
                grids.append(rows)
        return grids
    return []


def extract_tables(filename: str, data: bytes) -> list[list[list[str]]]:
    """Return list of grids (each grid = list of rows, row[0] = header)."""
    direct = _grids_direct(filename, data)
    lib = _grids_from_librarian(filename, data)
    # Prefer whichever recovered more total rows (direct avoids the 1000-row cap).
    direct_rows = sum(len(g) for g in direct)
    lib_rows = sum(len(g) for g in lib)
    return direct if direct_rows >= lib_rows else lib


# --- column mapping ------------------------------------------------------
def _heuristic_mapping(header: list[str]) -> dict[str, int | None]:
    norm = [h.lower().strip() for h in header]
    mapping: dict[str, int | None] = {f: None for f in CANONICAL_FIELDS}
    for field, hints in _HEADER_HINTS.items():
        for ci, h in enumerate(norm):
            if any(hint in h for hint in hints):
                mapping[field] = ci
                break
    if mapping["name"] is None:
        # Fall back to the first non-numeric-looking column.
        mapping["name"] = 0
    return mapping


def _llm_mapping(llm, header: list[str], sample: list[list[str]]) -> dict[str, int | None] | None:
    sample_txt = "\n".join(" | ".join(r) for r in sample[:4])
    result = llm.json(
        system=(
            "You map spreadsheet columns of a humanitarian relief inventory onto a "
            "canonical schema. Given the header and sample rows, return JSON: "
            '{"name": <col index or null>, "quantity": <idx|null>, "unit": <idx|null>, '
            '"category": <idx|null>, "party": <idx|null>, "location": <idx|null>, '
            '"date": <idx|null>, "notes": <idx|null>, "barcode": <idx|null>, '
            '"movement_type": "in"|"out"}. '
            "Column indices are 0-based. 'name' is the item description (required). "
            "'barcode' is any stable code/SKU/reference id for the item. "
            "'party' is supplier/donor (for intake) or recipient (for dispatch)."
        ),
        user=f"Header (0-based): {list(enumerate(header))}\nSample rows:\n{sample_txt}",
    )
    if not result:
        return None
    mapping: dict[str, int | None] = {}
    for f in CANONICAL_FIELDS:
        v = result.get(f)
        mapping[f] = v if isinstance(v, int) and 0 <= v < len(header) else None
    if mapping.get("name") is None:
        mapping["name"] = 0
    mapping["_movement_type"] = result.get("movement_type", "in")  # type: ignore
    return mapping


def _parse_qty(value: str) -> float:
    if not value:
        return 1.0
    cleaned = "".join(ch for ch in str(value) if ch.isdigit() or ch in ".,-")
    cleaned = cleaned.replace(",", "")
    try:
        return abs(float(cleaned)) if cleaned not in {"", ".", "-"} else 1.0
    except Exception:
        return 1.0


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _parse_date(val: str):
    if not val:
        return None
    from datetime import date

    s = str(val).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            from datetime import datetime as _dt

            return _dt.strptime(s, fmt).date()
        except Exception:
            continue
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _parse_grids(db, *, llm, grids, filename):
    """Turn raw grids into normalized row dicts + the mapping used per sheet."""
    rows_out: list[dict] = []
    mappings_used: list[dict] = []
    movement_type = "in"
    for grid in grids:
        header, rows = grid[0], grid[1:]
        mapping = (_llm_mapping(llm, header, rows[:4]) if llm.enabled else None) or _heuristic_mapping(header)
        mt = mapping.pop("_movement_type", "in") if isinstance(mapping, dict) else "in"
        if mt in {"in", "out"}:
            movement_type = mt
        mappings_used.append(
            {"header": header, "mapping": {k: (header[v] if isinstance(v, int) else None) for k, v in mapping.items()}}
        )
        for row in rows:
            name = _cell(row, mapping.get("name"))
            barcode = _cell(row, mapping.get("barcode"))
            if not name and not barcode:
                continue
            rows_out.append({
                "name": name or barcode,
                "barcode": barcode,
                "qty": _parse_qty(_cell(row, mapping.get("quantity"))),
                "unit": _cell(row, mapping.get("unit")) or "unit",
                "party": _cell(row, mapping.get("party")),
                "location": _cell(row, mapping.get("location")),
                "notes": _cell(row, mapping.get("notes")),
                "cat_hint": _cell(row, mapping.get("category")),
                "expiry": _parse_date(_cell(row, mapping.get("date"))),
            })
    return rows_out, mappings_used, movement_type


# --- orchestration -------------------------------------------------------
def normalize_upload(
    db: Session, *, upload, filename: str, data: bytes, user, center_id: str | None, mode: str = "add"
) -> dict:
    """Parse, normalize, dedup and ingest a spreadsheet.

    mode="add"  → every row is a NEW arrival (additive intake movements).
    mode="sync" → the sheet is the CURRENT full stock; the system matches each
                  item and records only the DIFFERENCE (an adjustment), so
                  re-uploading an updated version never double-counts.
    """
    llm = get_llm()
    grids = extract_tables(filename, data)
    if not grids:
        raise ValueError("Could not find any tabular data in this file.")

    parsed_rows, mappings_used, movement_type = _parse_grids(db, llm=llm, grids=grids, filename=filename)
    created = 0
    matched = 0

    if mode == "sync":
        # Aggregate target quantity per resolved item, then reconcile by delta.
        targets: dict[str, dict] = {}
        for r in parsed_rows:
            item, was_created = resolve_or_create_item(
                db, name=r["name"], user=user, center_id=center_id, unit=r["unit"],
                description=r["cat_hint"], barcode=r["barcode"],
            )
            if was_created:
                created += 1
            else:
                matched += 1
            agg = targets.setdefault(item.id, {"item": item, "target": 0.0, "unit": r["unit"],
                                               "party": r["party"], "expiry": r["expiry"]})
            agg["target"] += r["qty"]
            if r["expiry"] and not agg["expiry"]:
                agg["expiry"] = r["expiry"]

        increased = decreased = unchanged = 0
        for agg in targets.values():
            item = agg["item"]
            delta = round(agg["target"] - (item.quantity or 0.0), 4)
            if abs(delta) < 1e-9:
                unchanged += 1
                continue
            record_movement(
                db, item=item, type="adjust", quantity=delta, user=user, unit=agg["unit"],
                party=agg["party"], reason="reconciliation",
                expiry_date=agg["expiry"] if delta > 0 else None,
                note=f"Sync import: {filename} (set to {agg['target']:g})", source="upload",
            )
            if delta > 0:
                increased += 1
            else:
                decreased += 1

        total_items = len(targets)
        summary = (
            f"Synced {total_items} items from {len(parsed_rows)} rows: "
            f"{created} new, {increased} increased, {decreased} reduced, {unchanged} unchanged."
        )
        result = {"rows": len(parsed_rows), "created": created, "matched": matched,
                  "increased": increased, "decreased": decreased, "unchanged": unchanged,
                  "mode": "sync", "summary": summary}
    else:
        for r in parsed_rows:
            attributes = {}
            if r["cat_hint"]:
                attributes["source_category"] = r["cat_hint"]
            item, was_created = resolve_or_create_item(
                db, name=r["name"], user=user, center_id=center_id, unit=r["unit"],
                description=r["cat_hint"], attributes=attributes, barcode=r["barcode"],
            )
            created += 1 if was_created else 0
            matched += 0 if was_created else 1
            record_movement(
                db, item=item, type=movement_type, quantity=r["qty"], user=user, unit=r["unit"],
                party=r["party"], location=r["location"], expiry_date=r["expiry"], reason="donation",
                note=(r["notes"] or f"Imported from {filename}"), source="upload",
            )
        summary = f"Imported {len(parsed_rows)} rows: {created} new items, {matched} merged into existing items."
        result = {"rows": len(parsed_rows), "created": created, "matched": matched, "mode": "add", "summary": summary}

    upload.rows_detected = result["rows"]
    upload.items_created = created
    upload.items_matched = matched
    upload.mapping = {"sheets": mappings_used}
    upload.summary = summary
    upload.status = "done"
    db.commit()
    return result
