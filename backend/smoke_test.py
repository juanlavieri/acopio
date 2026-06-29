"""End-to-end smoke test of the Acopio backend (no AI key required).

Covers the org hierarchy, scoping, normalization, dashboards and the agent.
Run from the repo root:  python backend/smoke_test.py
"""
import io
import os
import sys
import tempfile
from datetime import date, timedelta

_tmp = tempfile.mkdtemp(prefix="acopio_smoke_")
os.environ["DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = ""
os.environ.pop("OPENAI_API_KEY", None)
# Disable env-based bootstrap so the test controls the first account.
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = ""
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = ""
os.environ["BOOTSTRAP_SUPERADMIN_EMAIL"] = ""
os.environ["BOOTSTRAP_SUPERADMIN_PASSWORD"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
c = TestClient(app)


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    if not cond:
        raise SystemExit(f"Smoke test failed at: {label}")


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- bootstrap country manager ------------------------------------------
r = c.get("/healthz")
check("healthz", r.status_code == 200)

r = c.get("/api/auth/bootstrap")
check("needs bootstrap", r.json()["needs_bootstrap"] is True)

r = c.post("/api/auth/register", json={"email": "pais@acopio.org", "name": "País", "password": "supplies123"})
check("register country manager", r.status_code == 200 and r.json()["user"]["role"] == "country_manager")
country = r.json()["token"]

# self-registration now closed
r = c.post("/api/auth/register", json={"email": "x@y.org", "name": "X", "password": "supplies123"})
check("self-register closed", r.status_code == 403)

# --- org structure -------------------------------------------------------
r = c.get("/api/org/overview", headers=H(country))
ov = r.json()
check("overview default region", len(ov["regions"]) >= 1)
check("overview default center", len(ov["centers"]) >= 1)
region_id = ov["regions"][0]["id"]
center_a = ov["centers"][0]["id"]

# create a second center
r = c.post("/api/org/centers", headers=H(country), json={"name": "Centro Oriente", "region_id": region_id})
check("create center B", r.status_code == 200)
center_b = r.json()["center"]["id"]

# create a regional manager
r = c.post("/api/org/users", headers=H(country), json={
    "email": "region@acopio.org", "name": "Regional", "password": "supplies123",
    "role": "regional_manager", "region_id": region_id})
check("create regional manager", r.status_code == 200)

# create a center manager + volunteer for center A
r = c.post("/api/org/users", headers=H(country), json={
    "email": "cm@acopio.org", "name": "Centro Mgr", "password": "supplies123",
    "role": "center_manager", "center_id": center_a})
check("create center manager", r.status_code == 200)

r = c.post("/api/org/users", headers=H(country), json={
    "email": "vol@acopio.org", "name": "Voluntario A", "password": "supplies123",
    "role": "volunteer", "center_id": center_a})
check("create volunteer A", r.status_code == 200)

# volunteer cannot create users
r = c.post("/api/auth/login", json={"email": "vol@acopio.org", "password": "supplies123"})
vol = r.json()["token"]
check("volunteer login", r.status_code == 200 and r.json()["user"]["center_id"] == center_a)
r = c.post("/api/org/users", headers=H(vol), json={
    "email": "z@a.org", "name": "Z", "password": "supplies123", "role": "volunteer", "center_id": center_a})
check("volunteer cannot create users", r.status_code == 403)

# --- scoped inventory ----------------------------------------------------
# Country manager must specify a center; record into A and B.
r = c.post("/api/movements", headers=H(country), json={"item_name": "Arroz 1kg", "type": "in", "quantity": 100, "unit": "bolsas", "center_id": center_a})
check("country records into A", r.status_code == 200 and r.json()["item"]["center_id"] == center_a)
check("auto food", r.json()["item"]["category_kind"] == "food")

r = c.post("/api/movements", headers=H(country), json={"item_name": "Carpas grandes", "type": "in", "quantity": 20, "center_id": center_b})
check("country records into B", r.status_code == 200 and r.json()["item"]["center_id"] == center_b)

# Volunteer in A records without center_id (uses their own center).
r = c.post("/api/movements", headers=H(vol), json={"item_name": "Paracetamol 500mg", "type": "in", "quantity": 50})
check("volunteer records into own center", r.status_code == 200 and r.json()["item"]["center_id"] == center_a)

# Volunteer only sees center A items (not B's tents).
r = c.get("/api/items", headers=H(vol))
names = [i["canonical_name"] for i in r.json()["items"]]
check("volunteer sees A items", "Arroz 1kg" in names and "Paracetamol 500mg" in names)
check("volunteer cannot see B items", "Carpas grandes" not in names)

# Country manager sees both centers.
r = c.get("/api/items", headers=H(country))
names_all = [i["canonical_name"] for i in r.json()["items"]]
check("country sees all", "Arroz 1kg" in names_all and "Carpas grandes" in names_all)

# Filter by center.
r = c.get("/api/items", headers=H(country), params={"center_id": center_b})
check("country filter center B", all(i["center_id"] == center_b for i in r.json()["items"]))

# out movement with note
item_a = next(i for i in r.json()["items"] if False) if False else None
r = c.get("/api/items", headers=H(vol))
rice = next(i for i in r.json()["items"] if i["canonical_name"] == "Arroz 1kg")
r = c.post("/api/movements", headers=H(vol), json={"item_id": rice["id"], "type": "out", "quantity": 30, "party": "Refugio Centro", "note": "Entregado a familias"})
check("out with note", r.status_code == 200 and r.json()["item"]["quantity"] == 70)

# --- upload scoped to volunteer's center --------------------------------
csv_bytes = (
    "Producto,Cantidad,Unidad,Proveedor\n"
    "Agua embotellada,500,botellas,Cruz Roja\n"
    "Jabon de manos,200,unidades,Donante B\n"
)
files = {"file": ("inv.csv", io.BytesIO(csv_bytes.encode()), "text/csv")}
r = c.post("/api/uploads", headers=H(vol), files=files)
check("volunteer upload", r.status_code == 200 and r.json()["result"]["rows"] == 2)

# uploaded items landed in center A
r = c.get("/api/items", headers=H(vol), params={"q": "agua"})
check("uploaded item in A", any(i["center_id"] == center_a for i in r.json()["items"]))

# --- dashboard scoped ----------------------------------------------------
r = c.get("/api/dashboard/summary", headers=H(vol))
dv = r.json()
r = c.get("/api/dashboard/summary", headers=H(country))
dc = r.json()
check("country totals >= volunteer totals", dc["totals"]["items"] >= dv["totals"]["items"])
check("dashboard flow list", isinstance(dc["flow"], list))

# --- agent fallback scoped ----------------------------------------------
r = c.post("/api/agent/chat", headers=H(vol), json={"message": "rice", "history": []})
check("agent fallback", r.status_code == 200 and "reply" in r.json())

# --- audit ---------------------------------------------------------------
r = c.get("/api/audit", headers=H(country))
check("audit log", r.status_code == 200 and len(r.json()["logs"]) >= 3)

# --- expiry / batches / FEFO --------------------------------------------
soon = (date.today() + timedelta(days=20)).isoformat()
far = (date.today() + timedelta(days=300)).isoformat()

r = c.post("/api/movements", headers=H(vol), json={"item_name": "Leche en polvo", "type": "in", "quantity": 40, "unit": "latas", "expiry_date": soon, "reason": "donation"})
check("intake near-expiry batch", r.status_code == 200)
milk_id = r.json()["item"]["id"]
r = c.post("/api/movements", headers=H(vol), json={"item_id": milk_id, "type": "in", "quantity": 60, "expiry_date": far})
check("intake far-expiry batch", r.status_code == 200 and r.json()["item"]["quantity"] == 100)

r = c.get(f"/api/items/{milk_id}", headers=H(vol))
det = r.json()
check("two batches tracked", len(det["batches"]) == 2)
check("item expiry status critical", det["item"]["expiry_status"] == "critical")

# FEFO: dispatch 50 depletes the near-expiry batch (40) first, then 10 from far.
r = c.post("/api/movements", headers=H(vol), json={"item_id": milk_id, "type": "out", "quantity": 50, "reason": "distributed"})
check("dispatch records", r.status_code == 200 and r.json()["item"]["quantity"] == 50)
batches = c.get(f"/api/items/{milk_id}", headers=H(vol)).json()["batches"]
near = [b for b in batches if b["expiry_date"] == soon]
far_b = [b for b in batches if b["expiry_date"] == far]
check("FEFO depleted near batch first", not near)  # near batch (40) fully consumed
check("FEFO far batch has 50 left", far_b and far_b[0]["qty_remaining"] == 50)

# --- alerts --------------------------------------------------------------
r = c.post("/api/movements", headers=H(vol), json={"item_name": "Vitaminas C", "type": "in", "quantity": 10, "expiry_date": soon, "reason": "donation"})
al = c.get("/api/alerts?days=30", headers=H(vol)).json()
check("alerts expiring includes near batch", any(b["expiry_date"] == soon for b in al["expiring"]))

# low stock via per-item reorder threshold
r = c.patch(f"/api/items/{milk_id}", headers=H(vol), json={"min_quantity": 80})
check("set reorder threshold", r.status_code == 200)
al = c.get("/api/alerts", headers=H(vol)).json()
check("low-stock flagged by min_quantity", any(i["id"] == milk_id for i in al["low_stock"]))

# --- needs / requisitions ------------------------------------------------
r = c.post("/api/needs", headers=H(vol), json={"item_name": "Leche en polvo", "quantity": 20, "unit": "latas", "priority": "urgent"})
check("create need", r.status_code == 200)
need_id = r.json()["need"]["id"]
r = c.post(f"/api/needs/{need_id}/fulfill", headers=H(vol), json={})
check("fulfill need dispatches stock", r.status_code == 200 and r.json()["dispatched"] > 0)
nd = next(n for n in c.get("/api/needs", headers=H(vol)).json()["needs"] if n["id"] == need_id)
check("need marked fulfilled/partial", nd["status"] in ("fulfilled", "partial"))

# --- export --------------------------------------------------------------
r = c.get("/api/export/items.csv", headers=H(vol))
check("export items csv", r.status_code == 200 and r.text.startswith("item,category"))
r = c.get("/api/export/movements.csv", headers=H(vol))
check("export movements csv", r.status_code == 200 and "date,type,item" in r.text)

# --- re-upload dedup with reconciliation preview/commit -----------------
def _qty(name):
    items = c.get("/api/items", headers=H(vol), params={"q": name}).json()["items"]
    m = [i for i in items if i["canonical_name"].lower() == name.lower()]
    return m[0]["quantity"] if m else None


def sync_preview(bytes_, force=False):
    data = {"mode": "sync"}
    if force:
        data["force"] = "true"
    return c.post("/api/uploads", headers=H(vol), files={"file": ("stock.csv", io.BytesIO(bytes_), "text/csv")}, data=data)


def commit(upload_id, plan, overrides=None):
    items = []
    for e in plan:
        target = (overrides or {}).get(e["name"], e["target"])
        items.append({"item_id": e["item_id"], "name": e["name"], "barcode": e["barcode"],
                      "unit": e["unit"], "target": target, "expiry": e.get("expiry")})
    return c.post(f"/api/uploads/{upload_id}/commit", headers=H(vol), json={"items": items})


# v-A: preview shows a NEW item at target 100, then commit applies it.
r = sync_preview(b"Producto,Cantidad,Unidad\nAceite vegetal,100,litros\n")
check("sync v-a returns preview", r.json().get("preview") is True)
plan = r.json()["plan"]
check("preview marks new item", plan[0]["status"] == "new" and plan[0]["target"] == 100)
check("preview made no writes yet", _qty("Aceite vegetal") in (None, 0))
r = commit(r.json()["upload"]["id"], plan)
check("commit v-a sets qty 100", r.status_code == 200 and _qty("Aceite vegetal") == 100)

# v-B: preview shows current 100 → target 140 (increase); commit reconciles (no double count).
r = sync_preview(b"Producto,Cantidad,Unidad\nAceite vegetal,140,litros\n")
plan = r.json()["plan"]
check("preview shows current+delta", plan[0]["current"] == 100 and plan[0]["delta"] == 40 and plan[0]["status"] == "increase")
r = commit(r.json()["upload"]["id"], plan)
check("commit v-b reconciles to 140", _qty("Aceite vegetal") == 140)

# Editing the proposed target before approval is respected.
r = sync_preview(b"Producto,Cantidad,Unidad\nAceite vegetal,140,litros\n", force=True)
up_id = r.json()["upload"]["id"]
r = commit(up_id, r.json()["plan"], overrides={"Aceite vegetal": 175})
check("edited target applied (175)", _qty("Aceite vegetal") == 175)

# Identical committed file is later flagged duplicate.
r = sync_preview(b"Producto,Cantidad,Unidad\nAceite vegetal,140,litros\n")
check("identical re-upload flagged duplicate", r.json().get("duplicate") is True)

# Cancel discards a preview (no changes).
r = sync_preview(b"Producto,Cantidad,Unidad\nAceite vegetal,999,litros\n")
up_id = r.json()["upload"]["id"]
c.post(f"/api/uploads/{up_id}/cancel", headers=H(vol))
check("cancel leaves qty unchanged", _qty("Aceite vegetal") == 175)

# Barcode matching across uploads (different names, same code → same item).
r = sync_preview(b"Code,Item,Qty\nABC123,Guantes nitrilo,50\n")
commit(r.json()["upload"]["id"], r.json()["plan"])
r = sync_preview(b"Code,Item,Qty\nABC123,Guantes de nitrilo (caja),80\n")
plan = r.json()["plan"]
check("barcode preview matches existing item", plan[0]["item_id"] is not None and plan[0]["current"] == 50)

# --- corrections: set-to-value, void, edit ------------------------------
r = c.post("/api/movements", headers=H(vol), json={"item_name": "Linterna prueba", "type": "in", "quantity": 60, "unit": "u"})
lid = r.json()["item"]["id"]
r = c.post(f"/api/items/{lid}/correct", headers=H(vol), json={"quantity": 45, "note": "recount"})
check("correct sets qty to 45", r.status_code == 200 and r.json()["item"]["quantity"] == 45)

r = c.post("/api/movements", headers=H(vol), json={"item_id": lid, "type": "in", "quantity": 10})
mid = r.json()["movement"]["id"]
check("wrong entry pushes to 55", r.json()["item"]["quantity"] == 55)
r = c.post(f"/api/movements/{mid}/void", headers=H(vol))
check("void reverses back to 45", r.status_code == 200 and r.json()["item"]["quantity"] == 45)
check("re-void blocked", c.post(f"/api/movements/{mid}/void", headers=H(vol)).status_code == 409)
voided = [m for m in c.get(f"/api/items/{lid}", headers=H(vol)).json()["movements"] if m["id"] == mid][0]
check("original entry flagged voided", voided["voided"] is True)

r = c.patch(f"/api/items/{lid}", headers=H(vol), json={"canonical_name": "Linterna LED prueba", "unit": "unidad"})
check("edit item name/unit", r.status_code == 200 and r.json()["item"]["canonical_name"] == "Linterna LED prueba")

# --- precise undo restores exact expiry/lot -----------------------------
expA = (date.today() + timedelta(days=25)).isoformat()
r = c.post("/api/movements", headers=H(vol), json={"item_name": "Atun lata", "type": "in", "quantity": 30, "unit": "lata", "expiry_date": expA})
atun_id = r.json()["item"]["id"]
mid_in = r.json()["movement"]["id"]
batches = c.get(f"/api/items/{atun_id}", headers=H(vol)).json()["batches"]
check("intake created its batch", any(b["expiry_date"] == expA and b["qty_remaining"] == 30 for b in batches))
r = c.post(f"/api/movements/{mid_in}/void", headers=H(vol))
check("undo intake removes stock", r.json()["item"]["quantity"] == 0)
batches = c.get(f"/api/items/{atun_id}", headers=H(vol)).json()["batches"]
check("undo intake removed its batch", all(b["expiry_date"] != expA for b in batches))

expB = (date.today() + timedelta(days=40)).isoformat()
r = c.post("/api/movements", headers=H(vol), json={"item_name": "Sopa sobre", "type": "in", "quantity": 50, "unit": "sobre", "expiry_date": expB})
sopa_id = r.json()["item"]["id"]
r = c.post("/api/movements", headers=H(vol), json={"item_id": sopa_id, "type": "out", "quantity": 20})
mid_out = r.json()["movement"]["id"]
r = c.post(f"/api/movements/{mid_out}/void", headers=H(vol))
check("undo dispatch restores qty", r.json()["item"]["quantity"] == 50)
batches = c.get(f"/api/items/{sopa_id}", headers=H(vol)).json()["batches"]
restored = sum(b["qty_remaining"] for b in batches if b["expiry_date"] == expB)
check("undo dispatch restored exact expiry batch", restored == 50)

# --- corrections log -----------------------------------------------------
r = c.get("/api/corrections", headers=H(vol))
check("corrections log lists corrections", r.status_code == 200 and len(r.json()["corrections"]) >= 2)
check("corrections are reason=correction", all(m["reason"] == "correction" for m in r.json()["corrections"]))

# --- scan lookup (QR/barcode -> item) -----------------------------------
r = c.post("/api/items", headers=H(vol), json={"name": "Scan item", "barcode": "EAN999"})
scan_id = r.json()["item"]["id"]
r = c.get("/api/items/lookup", headers=H(vol), params={"code": "EAN999"})
check("lookup by barcode", r.status_code == 200 and r.json()["item"]["id"] == scan_id)
r = c.get("/api/items/lookup", headers=H(vol), params={"code": f"acopio:item:{scan_id}"})
check("lookup by QR payload", r.status_code == 200 and r.json()["item"]["id"] == scan_id)
r = c.get("/api/items/lookup", headers=H(vol), params={"code": "https://x/?item=" + scan_id})
check("lookup by URL payload", r.status_code == 200 and r.json()["item"]["id"] == scan_id)
check("lookup unknown 404", c.get("/api/items/lookup", headers=H(vol), params={"code": "NOPE000"}).status_code == 404)

# --- multi-tenancy: super admin + tenant isolation ----------------------
# (Emails built at runtime to avoid literal-email redaction in tooling.)
AT = chr(64)
SUPER_EMAIL = "rootadmin" + AT + "acopio.org"
CO_EMAIL = "colombia.mgr" + AT + "acopio.org"
NEG_EMAIL = "neg.test" + AT + "acopio.org"

# Create a super admin directly (no public endpoint creates one).
from app.auth import hash_password as _hp  # noqa: E402
from app.db import SessionLocal as _SL  # noqa: E402
from app.models import User as _User  # noqa: E402

with _SL() as _s:
    _s.add(_User(email=SUPER_EMAIL, name="Root", password_hash=_hp("rootpass123"), role="super_admin"))
    _s.commit()

r = c.post("/api/auth/login", json={"email": SUPER_EMAIL, "password": "rootpass123"})
check("super admin login", r.status_code == 200 and r.json()["user"]["role"] == "super_admin")
sa = r.json()["token"]

r = c.get("/api/org/tenants", headers=H(sa))
check("super admin lists tenants", r.status_code == 200 and len(r.json()["tenants"]) >= 1)

r = c.post("/api/org/tenants", headers=H(sa), json={
    "org_name": "Acopio Colombia", "country": "Colombia",
    "manager_name": "Gerente CO", "manager_email": CO_EMAIL, "manager_password": "supplies123"})
check("super admin creates tenant + country manager", r.status_code == 200)

r = c.post("/api/auth/login", json={"email": CO_EMAIL, "password": "supplies123"})
check("tenant B manager login", r.status_code == 200 and r.json()["user"]["role"] == "country_manager")
bteam = r.json()["token"]
b_tenant = r.json()["user"]["tenant_id"]
check("tenant B has its own tenant", b_tenant and b_tenant != r.json()["user"].get("center_id"))

# B sees only its own (empty) org — not tenant A's items.
names_b = [i["canonical_name"] for i in c.get("/api/items", headers=H(bteam)).json()["items"]]
check("tenant B cannot see tenant A items", "Arroz 1kg" not in names_b and "Carpas grandes" not in names_b)

# B records into its own seeded center.
ctr_b = c.get("/api/org/centers", headers=H(bteam)).json()["centers"][0]["id"]
r = c.post("/api/movements", headers=H(bteam), json={"item_name": "Cobijas Colombia", "type": "in", "quantity": 10, "center_id": ctr_b})
check("tenant B records into its center", r.status_code == 200)

# A cannot see B's item; super admin sees both.
names_a = [i["canonical_name"] for i in c.get("/api/items", headers=H(country)).json()["items"]]
check("tenant A cannot see tenant B items", "Cobijas Colombia" not in names_a)
names_all = [i["canonical_name"] for i in c.get("/api/items", headers=H(sa)).json()["items"]]
check("super admin sees all tenants' items", "Arroz 1kg" in names_all and "Cobijas Colombia" in names_all)

# Country manager B cannot use the tenant-creation endpoint.
check("country manager cannot create tenants", c.post("/api/org/tenants", headers=H(bteam), json={
    "org_name": "x", "country": "Peru", "manager_name": "y", "manager_email": NEG_EMAIL, "manager_password": "supplies123"}).status_code == 403)

# --- help guide + super admin overview ----------------------------------
r = c.get("/api/help?lang=es", headers=H(vol))
check("help guide (es)", r.status_code == 200 and len(r.json()["sections"]) >= 5)
r = c.get("/api/help?lang=en", headers=H(vol))
check("help guide (en)", r.status_code == 200 and len(r.json()["sections"]) >= 5)

r = c.get("/api/admin/overview", headers=H(sa))
check("admin overview (super admin)", r.status_code == 200 and r.json()["tenant_count"] >= 2)
ov = r.json()
check("admin overview has per-org totals", all("totals" in o for o in ov["organizations"]))
check("admin overview global summary", "summary" in ov and "totals" in ov["summary"])
check("admin overview blocked for country manager", c.get("/api/admin/overview", headers=H(country)).status_code == 403)

# --- per-tenant AI gating (bring-your-own-key) --------------------------
from app.config import settings as _settings  # noqa: E402

_settings.openai_api_key = "sk-dummy-platform"  # simulate a platform key

def ai_enabled(tok):
    return c.get("/api/agent/status", headers=H(tok)).json()["ai_enabled"]

check("super admin AI on", ai_enabled(sa) is True)
check("grandfathered tenant A AI on (platform key)", ai_enabled(country) is True)
check("new tenant B AI off by default", ai_enabled(bteam) is False)

r = c.post("/api/org/ai-key", headers=H(bteam), json={"api_key": "sk-bteam-own"})
check("tenant B sets own key -> AI on", r.status_code == 200 and r.json()["ai_enabled"] is True and r.json()["source"] == "own")
check("status reflects own key", ai_enabled(bteam) is True)

c.post("/api/org/ai-key", headers=H(bteam), json={"api_key": ""})
check("tenant B clears key -> AI off", ai_enabled(bteam) is False)

r = c.post(f"/api/org/tenants/{b_tenant}/platform-key", headers=H(sa), json={"enabled": True})
check("super admin grants platform key", r.status_code == 200 and r.json()["tenant"]["use_platform_key"] is True)
check("tenant B AI on via platform grant", ai_enabled(bteam) is True)

check("volunteer cannot set AI key", c.post("/api/org/ai-key", headers=H(vol), json={"api_key": "x"}).status_code == 403)
_settings.openai_api_key = None

# --- auth enforced -------------------------------------------------------
check("auth enforced", c.get("/api/items").status_code == 401)

print("\nALL SMOKE TESTS PASSED ✅")
