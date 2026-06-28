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

# --- auth enforced -------------------------------------------------------
check("auth enforced", c.get("/api/items").status_code == 401)

print("\nALL SMOKE TESTS PASSED ✅")
