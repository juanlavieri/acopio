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
CANONICAL_FIELDS = ["name", "quantity", "unit", "category", "party", "location", "date", "notes"]

_HEADER_HINTS: dict[str, list[str]] = {
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
            '"date": <idx|null>, "notes": <idx|null>, "movement_type": "in"|"out"}. '
            "Column indices are 0-based. 'name' is the item description (required). "
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


# --- orchestration -------------------------------------------------------
def normalize_upload(db: Session, *, upload, filename: str, data: bytes, user, center_id: str | None) -> dict:
    """Parse, normalize, dedup and ingest a spreadsheet as intake movements."""
    llm = get_llm()
    grids = extract_tables(filename, data)
    if not grids:
        raise ValueError("Could not find any tabular data in this file.")

    total_rows = 0
    created = 0
    matched = 0
    mappings_used: list[dict] = []
    default_type = "in"

    for grid in grids:
        header, rows = grid[0], grid[1:]
        mapping = None
        if llm.enabled:
            mapping = _llm_mapping(llm, header, rows[:4])
        if not mapping:
            mapping = _heuristic_mapping(header)
        movement_type = mapping.pop("_movement_type", default_type) if isinstance(mapping, dict) else default_type
        if movement_type not in {"in", "out"}:
            movement_type = "in"

        mappings_used.append(
            {"header": header, "mapping": {k: (header[v] if isinstance(v, int) else None)
                                            for k, v in mapping.items()}}
        )

        for row in rows:
            name = _cell(row, mapping.get("name"))
            if not name:
                continue
            total_rows += 1
            qty = _parse_qty(_cell(row, mapping.get("quantity")))
            unit = _cell(row, mapping.get("unit")) or "unit"
            party = _cell(row, mapping.get("party"))
            location = _cell(row, mapping.get("location"))
            notes = _cell(row, mapping.get("notes"))
            cat_hint = _cell(row, mapping.get("category"))

            attributes = {}
            if cat_hint:
                attributes["source_category"] = cat_hint
            if _cell(row, mapping.get("date")):
                attributes["source_date"] = _cell(row, mapping.get("date"))

            item, was_created = resolve_or_create_item(
                db,
                name=name,
                user=user,
                center_id=center_id,
                unit=unit,
                description=cat_hint,
                attributes=attributes,
            )
            if was_created:
                created += 1
            else:
                matched += 1

            record_movement(
                db,
                item=item,
                type=movement_type,
                quantity=qty,
                user=user,
                unit=unit,
                party=party,
                location=location,
                note=(notes + (f" (import: {filename})" if not notes else "")) or f"Imported from {filename}",
                source="upload",
            )

    # Optional LLM summary of what landed.
    summary = f"Imported {total_rows} rows: {created} new items, {matched} merged into existing items."
    upload.rows_detected = total_rows
    upload.items_created = created
    upload.items_matched = matched
    upload.mapping = {"sheets": mappings_used}
    upload.summary = summary
    upload.status = "done"
    db.commit()
    return {"rows": total_rows, "created": created, "matched": matched, "summary": summary}
