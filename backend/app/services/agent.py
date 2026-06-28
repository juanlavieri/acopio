"""The Acopio AI assistant: a tool-calling agent over the inventory.

Capabilities exposed as tools (every mutation is attributed to the calling user
and written to the audit log):

* ``search_inventory``   — semantic + lexical search (librarian embeddings)
* ``run_query``          — safe, read-only SQL (the "code execution" for
                            analytical / semantic questions over the data)
* ``record_stock``       — take items in or out
* ``create_item``        — register a new supply line
* ``add_field``          — add a custom field/column to items (flexible schema)
* ``create_table``       — spin up a new lightweight table
* ``add_record``         — insert a row into a custom table
* ``get_stats``          — dashboard-style aggregates

Without an OpenAI key the agent falls back to a simple semantic search so the
chat box still returns useful results.
"""
from __future__ import annotations

import json
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import audit
from ..models import Category, CustomField, CustomRecord, CustomTable, Item, Movement, User
from ..scope import resolve_target_center, visible_center_ids
from .inventory import (
    KINDS,
    correct_stock,
    match_item,
    record_movement,
    resolve_or_create_item,
    void_movement,
)
from .llm import get_llm
from .semantic import get_index

MAX_STEPS = 6
QUERY_ROW_LIMIT = 200

# Tables the read-only query tool is allowed to touch (never users/sessions).
_ALLOWED_TABLES = {
    "items", "movements", "categories", "audit_logs", "uploads",
    "custom_fields", "custom_tables", "custom_records",
}
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace|"
    r"truncate|grant|vacuum)\b",
    re.IGNORECASE,
)


SCHEMA_DOC = """
Read-only tables you can query with run_query (SQLite/Postgres compatible SQL):
- items(id, canonical_name, description, category_id, unit, quantity, fingerprint, attributes(JSON), created_at)
- movements(id, item_id, type['in'|'out'|'adjust'], quantity, signed_quantity, balance_after, unit, party, location, note, source, user_id, created_at)
- categories(id, name, kind['food'|'water'|'medical'|'hygiene'|'shelter'|'clothing'|'tools'|'baby'|'other'], description)
- uploads(id, filename, rows_detected, items_created, created_at)
- audit_logs(id, user_id, action, entity_type, entity_id, created_at)
- batches(id, item_id, center_id, lot_code, expiry_date, qty_received, qty_remaining) — perishable stock by expiry (FEFO)
- needs(id, center_id, item_name, quantity, fulfilled_quantity, unit, priority, status, needed_by) — field requests
- custom_tables(id, name, label, schema) and custom_records(id, table_id, data(JSON))
'quantity' on items is the CURRENT stock. items.min_quantity is the reorder level.
For flow over time, aggregate movements. For expiry questions, use batches or call check_alerts.
""".strip()


def _tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "search_inventory",
                "description": "Semantic + keyword search over inventory items. Use to find items by meaning before acting.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer", "default": 8},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_query",
                "description": "Execute a READ-ONLY SQL SELECT over the inventory database for analytics. Only SELECT is allowed.",
                "parameters": {
                    "type": "object",
                    "properties": {"sql": {"type": "string", "description": "A single SELECT statement."}},
                    "required": ["sql"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "record_stock",
                "description": "Record an intake (in) or dispatch (out) of an item. Creates the item if it does not exist yet. Include expiry_date for perishable donations (food/medicine).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string"},
                        "type": {"type": "string", "enum": ["in", "out"]},
                        "quantity": {"type": "number"},
                        "unit": {"type": "string"},
                        "party": {"type": "string", "description": "Supplier/donor (in) or recipient (out)."},
                        "location": {"type": "string"},
                        "note": {"type": "string"},
                        "reason": {"type": "string", "description": "in: donation/purchase/transfer_in/return; out: distributed/transferred/damaged/expired/lost."},
                        "expiry_date": {"type": "string", "description": "Expiry date YYYY-MM-DD (intake of perishables)."},
                        "lot_code": {"type": "string"},
                    },
                    "required": ["item_name", "type", "quantity"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_alerts",
                "description": "List items expiring soon, expired stock, and items below their reorder level.",
                "parameters": {
                    "type": "object",
                    "properties": {"days": {"type": "integer", "default": 30}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_need",
                "description": "Log a field request/requisition for supplies that are needed (demand).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                        "note": {"type": "string"},
                    },
                    "required": ["item_name", "quantity"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "correct_stock",
                "description": "Fix/correct an item's CURRENT stock to the right absolute number (use when a previous entry was wrong). Logs a correction.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string"},
                        "quantity": {"type": "number", "description": "The correct current quantity on hand."},
                        "note": {"type": "string"},
                    },
                    "required": ["item_name", "quantity"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_item",
                "description": "Correct an item's details: rename, change unit, category, reorder level or barcode.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_name": {"type": "string", "description": "Current name (or barcode) to find the item."},
                        "new_name": {"type": "string"},
                        "unit": {"type": "string"},
                        "category_kind": {"type": "string", "enum": KINDS},
                        "min_quantity": {"type": "number"},
                        "barcode": {"type": "string"},
                    },
                    "required": ["item_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "undo_last_movement",
                "description": "Undo/reverse the most recent stock movement for an item (when it was entered by mistake).",
                "parameters": {
                    "type": "object",
                    "properties": {"item_name": {"type": "string"}},
                    "required": ["item_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_item",
                "description": "Register a new supply line without recording stock movement.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "unit": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_field",
                "description": "Add a new custom field/column to inventory items (flexible schema).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "type": {"type": "string", "enum": ["text", "number", "date", "boolean"]},
                    },
                    "required": ["label"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_table",
                "description": "Create a new lightweight custom table to track something new.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "columns": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "type": {"type": "string", "enum": ["text", "number", "date", "boolean"]},
                                },
                                "required": ["label"],
                            },
                        },
                    },
                    "required": ["name", "columns"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_record",
                "description": "Add a row to a custom table created with create_table.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table_name": {"type": "string"},
                        "data": {"type": "object"},
                    },
                    "required": ["table_name", "data"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_stats",
                "description": "Get summary aggregates (totals, by category, recent flow).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


# --- tool implementations ------------------------------------------------
def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "field"


def _parse_date(val):
    if not val:
        return None
    from datetime import date

    try:
        return date.fromisoformat(str(val)[:10])
    except Exception:
        return None


def _exec_tool(db: Session, user: User, name: str, args: dict, center_id: str | None) -> dict:
    try:
        if name == "search_inventory":
            vis = visible_center_ids(db, user)
            hits = get_index().search(args.get("query", ""), int(args.get("k", 8)) * 3)
            out = []
            for iid, score in hits:
                it = db.get(Item, iid)
                if not it:
                    continue
                if vis is not None and it.center_id not in vis:
                    continue
                out.append({**it.public(), "score": round(score, 3)})
                if len(out) >= int(args.get("k", 8)):
                    break
            return {"results": out}

        if name == "run_query":
            return _run_query(db, args.get("sql", ""))

        if name == "record_stock":
            try:
                target = resolve_target_center(db, user, center_id)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            item, _created = resolve_or_create_item(
                db, name=args["item_name"], user=user, center_id=target, unit=args.get("unit", "unit")
            )
            mv = record_movement(
                db,
                item=item,
                type=args.get("type", "in"),
                quantity=float(args.get("quantity", 0)),
                user=user,
                unit=args.get("unit"),
                party=args.get("party", ""),
                location=args.get("location", ""),
                note=args.get("note", ""),
                reason=args.get("reason", ""),
                expiry_date=_parse_date(args.get("expiry_date")),
                lot_code=args.get("lot_code", ""),
                source="agent",
            )
            return {"ok": True, "item": item.canonical_name, "new_balance": mv.balance_after,
                    "movement_id": mv.id}

        if name == "check_alerts":
            from ..models import Batch
            from .expiry import expiry_status, today

            vis = visible_center_ids(db, user)
            ref = today()
            bq = db.query(Batch).filter(Batch.qty_remaining > 0, Batch.expiry_date.isnot(None))
            if vis is not None:
                bq = bq.filter(Batch.center_id.in_(vis or {"__none__"}))
            expired, expiring = [], []
            for b in bq.all():
                delta = (b.expiry_date - ref).days
                rec = {"item": b.item.canonical_name if b.item else "", "qty": b.qty_remaining,
                       "expiry": b.expiry_date.isoformat(), "days": delta}
                if delta < 0:
                    expired.append(rec)
                elif delta <= int(args.get("days", 30)):
                    expiring.append(rec)
            iq = db.query(Item)
            if vis is not None:
                iq = iq.filter(Item.center_id.in_(vis or {"__none__"}))
            low = [
                {"item": it.canonical_name, "qty": it.quantity, "min": it.min_quantity or 5}
                for it in iq.all() if (it.quantity or 0.0) <= (it.min_quantity if it.min_quantity else 5)
            ]
            return {"expired": expired, "expiring": expiring, "low_stock": low}

        if name == "create_need":
            from ..models import Need

            try:
                target = resolve_target_center(db, user, center_id)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            need = Need(
                center_id=target, item_name=args["item_name"], quantity=abs(float(args.get("quantity", 0))),
                unit=args.get("unit", "unit"), priority=args.get("priority", "normal"),
                note=args.get("note", ""), requested_by=user.id,
            )
            db.add(need)
            db.commit()
            audit(db, user, "need.create", "need", need.id, {"item": need.item_name})
            return {"ok": True, "need_id": need.id, "item": need.item_name}

        if name in {"correct_stock", "update_item", "undo_last_movement"}:
            try:
                target_center = resolve_target_center(db, user, center_id)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            item = match_item(db, name=args["item_name"], center_id=target_center, barcode=args.get("item_name", ""))
            if not item:
                return {"ok": False, "error": f"No item matching '{args['item_name']}' was found."}

            if name == "correct_stock":
                mv = correct_stock(db, item=item, target=float(args.get("quantity", 0)), user=user,
                                   note=args.get("note", ""), source="agent")
                return {"ok": True, "item": item.canonical_name, "new_balance": item.quantity,
                        "changed": mv is not None}

            if name == "update_item":
                if args.get("new_name"):
                    item.canonical_name = args["new_name"]
                    from .inventory import fingerprint
                    item.fingerprint = fingerprint(args["new_name"])
                if args.get("unit"):
                    item.unit = args["unit"]
                if args.get("barcode"):
                    item.barcode = args["barcode"]
                if args.get("min_quantity") is not None:
                    item.min_quantity = float(args["min_quantity"])
                if args.get("category_kind"):
                    cat = db.query(Category).filter(Category.kind == args["category_kind"]).first()
                    if cat:
                        item.category_id = cat.id
                db.commit()
                get_index().upsert(item.id, f"{item.canonical_name}. {item.description}")
                audit(db, user, "item.update", "item", item.id, {"via": "agent"})
                return {"ok": True, "item": item.canonical_name}

            # undo_last_movement
            last = (
                db.query(Movement)
                .filter(Movement.item_id == item.id, Movement.voided == False, Movement.reason != "correction")  # noqa: E712
                .order_by(Movement.created_at.desc())
                .first()
            )
            if not last:
                return {"ok": False, "error": "No movement to undo for this item."}
            void_movement(db, movement=last, user=user, source="agent")
            return {"ok": True, "item": item.canonical_name, "undone": last.public(), "new_balance": item.quantity}

        if name == "create_item":
            try:
                target = resolve_target_center(db, user, center_id)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            item, created = resolve_or_create_item(
                db, name=args["name"], user=user, center_id=target, unit=args.get("unit", "unit"),
                description=args.get("description", ""),
            )
            return {"ok": True, "created": created, "item_id": item.id, "name": item.canonical_name}

        if name == "add_field":
            key = _slug(args["label"])
            existing = db.query(CustomField).filter_by(entity="item", key=key).first()
            if existing:
                return {"ok": True, "already_exists": True, "key": key}
            fld = CustomField(entity="item", key=key, label=args["label"],
                              type=args.get("type", "text"), created_by=user.id)
            db.add(fld)
            db.commit()
            audit(db, user, "schema.add_field", "custom_field", fld.id, {"label": args["label"]})
            return {"ok": True, "key": key, "label": args["label"]}

        if name == "create_table":
            tname = _slug(args["name"])
            if db.query(CustomTable).filter_by(name=tname).first():
                return {"ok": False, "error": "A table with that name already exists."}
            schema = [{"key": _slug(c["label"]), "label": c["label"], "type": c.get("type", "text")}
                      for c in args.get("columns", [])]
            tbl = CustomTable(name=tname, label=args["name"], schema=schema, created_by=user.id)
            db.add(tbl)
            db.commit()
            audit(db, user, "schema.create_table", "custom_table", tbl.id, {"name": tname})
            return {"ok": True, "table": tname, "columns": [c["key"] for c in schema]}

        if name == "add_record":
            tname = _slug(args["table_name"])
            tbl = db.query(CustomTable).filter_by(name=tname).first()
            if not tbl:
                return {"ok": False, "error": "Table not found. Create it first with create_table."}
            rec = CustomRecord(table_id=tbl.id, data=args.get("data", {}), created_by=user.id)
            db.add(rec)
            db.commit()
            audit(db, user, "record.create", "custom_record", rec.id, {"table": tname})
            return {"ok": True, "record_id": rec.id}

        if name == "get_stats":
            from .dashboard import build_summary

            return build_summary(db, center_ids=visible_center_ids(db, user), center_filter=center_id)

        return {"error": f"Unknown tool {name}"}
    except Exception as e:  # never let a tool crash the chat
        return {"error": str(e)}


def _run_query(db: Session, sql: str) -> dict:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return {"error": "Empty query."}
    low = sql.lower()
    if not low.startswith("select") and not low.startswith("with"):
        return {"error": "Only SELECT statements are allowed."}
    if ";" in sql:
        return {"error": "Multiple statements are not allowed."}
    if _FORBIDDEN_SQL.search(sql):
        return {"error": "Only read-only queries are allowed."}
    if re.search(r"\busers\b|\bsessions\b", low):
        return {"error": "Access to user/session tables is not allowed."}
    # Enforce a row cap.
    if not re.search(r"\blimit\b", low):
        sql = f"{sql} LIMIT {QUERY_ROW_LIMIT}"
    try:
        result = db.execute(text(sql))
        cols = list(result.keys())
        rows = [dict(zip(cols, r)) for r in result.fetchmany(QUERY_ROW_LIMIT)]
        # JSON-safe coercion
        for row in rows:
            for k, v in list(row.items()):
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
        return {"columns": cols, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": f"Query failed: {e}"}


# --- main loop -----------------------------------------------------------
def _system_prompt(user: User, db: Session, center_id: str | None) -> str:
    from ..models import Center

    tables = db.query(CustomTable).all()
    fields = db.query(CustomField).filter_by(entity="item").all()
    extra = ""
    if fields:
        extra += "\nCustom item fields: " + ", ".join(f"{f.key} ({f.label})" for f in fields)
    if tables:
        extra += "\nCustom tables: " + ", ".join(t.name for t in tables)

    vis = visible_center_ids(db, user)
    if vis is None:
        scope_line = "You oversee ALL collection centers (country manager)."
    else:
        names = [c.name for c in db.query(Center).filter(Center.id.in_(vis or {"__none__"})).all()]
        scope_line = f"You can see these centers: {', '.join(names) or 'none yet'}."
    active = db.get(Center, center_id) if center_id else (db.get(Center, user.center_id) if user.center_id else None)
    active_line = (
        f"The ACTIVE center for new stock actions is '{active.name}'."
        if active
        else "No active center is selected; ask the user which center before recording stock if you are a manager."
    )

    return f"""You are the assistant for **Acopio**, an inventory system for a humanitarian relief
operation routing supplies through Curaçao to Venezuela after recent earthquakes.

The current user is {user.name} (role: {user.role}). {scope_line} {active_line}

Every stock action you take is recorded under their name. Be careful, accurate and concise.
Confirm quantities and units. Reply in the same language the user writes in (Spanish or English).

You CAN take real actions, not just read: record stock IN (donations arriving) and OUT (supplies
dispatched) with notes and the supplier/recipient, create new items, evolve the schema (add fields
or tables), and run read-only SQL for analytics. Prefer run_query for "how much / how many / which"
questions. When a user dictates an intake or dispatch, call record_stock (type 'in' or 'out',
include the note and party). Only the centers above are yours; do not report on others.

{SCHEMA_DOC}{extra}

When you take an action, briefly state what you did and the resulting stock level."""


def run_agent(
    db: Session, user: User, message: str, history: list[dict] | None = None, center_id: str | None = None
) -> dict:
    llm = get_llm()
    actions: list[dict] = []

    if not llm.enabled:
        # Graceful fallback: semantic search only (scoped).
        vis = visible_center_ids(db, user)
        hits = get_index().search(message, 24)
        items = []
        for iid, _ in hits:
            it = db.get(Item, iid)
            if it and (vis is None or it.center_id in vis):
                items.append(it.public())
            if len(items) >= 8:
                break
        reply = (
            "The AI assistant needs an OpenAI API key to take actions and converse. "
            "Here are inventory items related to your message:\n"
            + ("\n".join(f"• {i['canonical_name']} — {i['quantity']} {i['unit']}" for i in items)
               if items else "No matching items found.")
        )
        return {"reply": reply, "actions": actions, "items": items}

    messages: list[dict] = [{"role": "system", "content": _system_prompt(user, db, center_id)}]
    for turn in (history or [])[-10:]:
        if turn.get("role") in {"user", "assistant"} and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    tools = _tool_schemas()
    final_text = ""

    for _ in range(MAX_STEPS):
        msg = llm.chat(messages, tools=tools, tool_choice="auto", temperature=0.2)
        if msg is None:
            final_text = "The assistant is temporarily unavailable."
            break

        tool_calls = getattr(msg, "tool_calls", None)
        # Record the assistant message (with tool calls) into the running transcript.
        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant_entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ]
        messages.append(assistant_entry)

        if not tool_calls:
            final_text = msg.content or ""
            break

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            result = _exec_tool(db, user, tc.function.name, args, center_id)
            actions.append({"tool": tc.function.name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str)[:6000],
            })

    audit(db, user, "agent.chat", "chat", "", {"message": message[:500], "tools": [a["tool"] for a in actions]})
    return {"reply": final_text or "Done.", "actions": actions}
