import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Download, Pencil, Plus, Search, Sparkles, Trash2, Undo2, Wrench, X } from "lucide-react";
import { api } from "../lib/api";
import { REASONS, expiryColor, fmtDate, fmtNum, kindColor } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";
import { useScope } from "../lib/scope.jsx";

export default function Inventory() {
  const { t, kindName } = useT();
  const scope = useScope();
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [q, setQ] = useState("");
  const [semantic, setSemantic] = useState(false);
  const [categoryId, setCategoryId] = useState("");
  const [alertFilter, setAlertFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (semantic) params.set("semantic", "true");
      if (categoryId) params.set("category_id", categoryId);
      if (scope.viewCenter) params.set("center_id", scope.viewCenter);
      const { items } = await api.get(`/api/items?${params.toString()}`);
      setItems(items);
    } finally {
      setLoading(false);
    }
  }, [q, semantic, categoryId, scope.viewCenter]);

  useEffect(() => {
    api.get("/api/categories").then((d) => setCategories(d.categories));
  }, []);
  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
  }, [load]);
  useEffect(() => {
    window.addEventListener("acopio:data-changed", load);
    return () => window.removeEventListener("acopio:data-changed", load);
  }, [load]);

  const filtered = useMemo(() => {
    if (alertFilter === "low") return items.filter((i) => i.low_stock);
    if (alertFilter === "expiring") return items.filter((i) => ["critical", "warning", "caution"].includes(i.expiry_status));
    if (alertFilter === "expired") return items.filter((i) => i.expiry_status === "expired");
    return items;
  }, [items, alertFilter]);

  const exportCsv = (kind) => {
    const qs = scope.viewCenter ? `?center_id=${scope.viewCenter}` : "";
    api.download(`/api/export/${kind}.csv${qs}`, `acopio_${kind}.csv`);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t("inv.title")}</h1>
          <p className="text-sm text-slate-500">{filtered.length} {t("inv.shown")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => exportCsv("items")}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50" title={t("inv.exportItems")}>
            <Download size={16} /> <span className="hidden sm:inline">{t("inv.export")}</span>
          </button>
          <button onClick={() => setModal({ type: "item" })}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            <Plus size={16} /> <span className="hidden sm:inline">{t("inv.newItem")}</span>
          </button>
          <button onClick={() => setModal({ type: "movement", movementType: "in" })}
            className="flex items-center gap-1.5 rounded-xl bg-brand-700 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-800">
            <ArrowDownLeft size={16} /> {t("inv.recordMovement")}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[180px] flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("inv.search")}
            className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-500" />
        </div>
        <button onClick={() => setSemantic((s) => !s)}
          className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium ${
            semantic ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 bg-white text-slate-600"}`}>
          <Sparkles size={15} /> {t("inv.smart")}
        </button>
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 outline-none focus:border-brand-500">
          <option value="">{t("inv.allCategories")}</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      <div className="flex flex-wrap gap-2">
        {["all", "low", "expiring", "expired"].map((f) => (
          <button key={f} onClick={() => setAlertFilter(f)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              alertFilter === f ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
            {t(`inv.filter.${f}`)}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">{t("inv.col.item")}</th>
              <th className="px-4 py-3">{t("inv.col.category")}</th>
              <th className="px-4 py-3">{t("inv.col.expiry")}</th>
              <th className="px-4 py-3 text-right">{t("inv.col.stock")}</th>
              <th className="px-4 py-3 text-right">{t("inv.col.actions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">{t("common.loading")}</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">{t("inv.empty")}</td></tr>
            ) : (
              filtered.map((it) => (
                <tr key={it.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <button onClick={() => setDetail(it.id)} className="text-left">
                      <div className="font-medium text-slate-800 hover:text-brand-700">{it.canonical_name}</div>
                      <div className="text-xs text-slate-400">{it.center || ""}</div>
                    </button>
                  </td>
                  <td className="px-4 py-3"><CatBadge kind={it.category_kind} name={kindName(it.category_kind)} /></td>
                  <td className="px-4 py-3"><ExpiryPill status={it.expiry_status} date={it.earliest_expiry} t={t} /></td>
                  <td className="px-4 py-3 text-right">
                    <span className={`font-semibold ${it.low_stock ? "text-red-600" : "text-slate-800"}`}>{fmtNum(it.quantity)}</span>
                    <span className="ml-1 text-xs text-slate-400">{it.unit}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => setModal({ type: "movement", item: it, movementType: "in" })}
                        className="rounded-lg bg-green-50 p-1.5 text-green-600 hover:bg-green-100" title={t("inv.stockIn")}><ArrowDownLeft size={16} /></button>
                      <button onClick={() => setModal({ type: "movement", item: it, movementType: "out" })}
                        className="rounded-lg bg-orange-50 p-1.5 text-orange-600 hover:bg-orange-100" title={t("inv.stockOut")}><ArrowUpRight size={16} /></button>
                      <button onClick={async () => { if (confirm(t("inv.deleteConfirm", { name: it.canonical_name }))) { await api.del(`/api/items/${it.id}`); load(); } }}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600" title={t("common.delete")}><Trash2 size={16} /></button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {modal?.type === "movement" && (
        <MovementModal presetItem={modal.item} presetType={modal.movementType} scope={scope}
          onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} />
      )}
      {modal?.type === "item" && (
        <ItemModal categories={categories} scope={scope}
          onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} />
      )}
      {detail && <ItemDrawer itemId={detail} categories={categories} onClose={() => setDetail(null)} onChanged={load} />}
    </div>
  );
}

function ExpiryPill({ status, date, t }) {
  if (!status || status === "none") return <span className="text-xs text-slate-300">—</span>;
  const color = expiryColor(status);
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: `${color}1a`, color }}>
      {t(`expiry.${status}`)}{date ? ` · ${date}` : ""}
    </span>
  );
}

function CatBadge({ kind, name }) {
  const color = kindColor(kind);
  return <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: `${color}1a`, color }}>{name}</span>;
}

function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-end p-0 sm:place-items-center sm:p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative max-h-[92vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-6 shadow-2xl sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-slate-100"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function CenterPicker({ scope, value, onChange, t }) {
  if (!scope.needsCenterPicker) return null;
  return (
    <Field label={t("scope.center")}>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="ac-sel">
        <option value="">{t("scope.selectCenter")}</option>
        {scope.centers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
    </Field>
  );
}

function MovementModal({ presetItem, presetType, scope, onClose, onSaved }) {
  const { t } = useT();
  const [type, setType] = useState(presetType || "in");
  const [itemName, setItemName] = useState(presetItem?.canonical_name || "");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState(presetItem?.unit || "unit");
  const [party, setParty] = useState("");
  const [location, setLocation] = useState("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [expiry, setExpiry] = useState("");
  const [lot, setLot] = useState("");
  const [centerId, setCenterId] = useState(scope.actionCenter || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setError("");
    if (!itemName.trim() || !quantity) return setError(t("inv.required"));
    if (!presetItem && scope.needsCenterPicker && !centerId) return setError(t("inv.selectCenterFirst"));
    setBusy(true);
    try {
      await api.post("/api/movements", {
        item_id: presetItem?.id || null,
        item_name: presetItem ? null : itemName,
        type, quantity: Number(quantity), unit, party, location, note,
        reason: reason || null,
        expiry_date: type === "in" && expiry ? expiry : null,
        lot_code: type === "in" ? lot : "",
        center_id: presetItem ? null : centerId || null,
      });
      onSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <Modal title={t("inv.recordMovement")} onClose={onClose}>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          {["in", "out"].map((tp) => (
            <button key={tp} onClick={() => setType(tp)}
              className={`rounded-xl border py-2 text-sm font-semibold ${
                type === tp ? (tp === "in" ? "border-green-500 bg-green-50 text-green-700" : "border-orange-500 bg-orange-50 text-orange-700") : "border-slate-200 text-slate-500"}`}>
              {tp === "in" ? t("inv.receiving") : t("inv.dispatching")}
            </button>
          ))}
        </div>
        {!presetItem && <CenterPicker scope={scope} value={centerId} onChange={setCenterId} t={t} />}
        <Input label={t("inv.item")} value={itemName} onChange={setItemName} disabled={!!presetItem} />
        <div className="grid grid-cols-2 gap-2">
          <Input label={t("inv.quantity")} value={quantity} onChange={setQuantity} type="number" placeholder="100" />
          <Input label={t("inv.unit")} value={unit} onChange={setUnit} />
        </div>
        <Input label={type === "in" ? t("inv.supplier") : t("inv.recipient")} value={party} onChange={setParty} />
        <Field label={t("inv.reason")}>
          <select value={reason} onChange={(e) => setReason(e.target.value)} className="ac-sel">
            <option value="">{t("reason.select")}</option>
            {REASONS[type].map((r) => <option key={r} value={r}>{t(`reason.${r}`)}</option>)}
          </select>
        </Field>
        {type === "in" && (
          <div className="grid grid-cols-2 gap-2">
            <Input label={t("inv.expiryDate")} value={expiry} onChange={setExpiry} type="date" />
            <Input label={t("inv.lot")} value={lot} onChange={setLot} />
          </div>
        )}
        <Input label={t("inv.note")} value={note} onChange={setNote} />
        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
        <button onClick={save} disabled={busy} className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
          {busy ? t("login.pleaseWait") : t("inv.saveMovement")}
        </button>
      </div>
    </Modal>
  );
}

function ItemModal({ categories, scope, onClose, onSaved }) {
  const { t } = useT();
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("unit");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [minQty, setMinQty] = useState("");
  const [barcode, setBarcode] = useState("");
  const [centerId, setCenterId] = useState(scope.actionCenter || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    if (!name.trim()) return setError(t("inv.nameRequired"));
    if (scope.needsCenterPicker && !centerId) return setError(t("inv.selectCenterFirst"));
    setBusy(true);
    try {
      await api.post("/api/items", {
        name, unit, description, category_id: categoryId || null, center_id: centerId || null,
        min_quantity: minQty ? Number(minQty) : 0, barcode,
      });
      onSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <Modal title={t("inv.newItem")} onClose={onClose}>
      <div className="space-y-3">
        <CenterPicker scope={scope} value={centerId} onChange={setCenterId} t={t} />
        <Input label={t("inv.name")} value={name} onChange={setName} />
        <div className="grid grid-cols-2 gap-2">
          <Input label={t("inv.unit")} value={unit} onChange={setUnit} />
          <Input label={t("inv.minStock")} value={minQty} onChange={setMinQty} type="number" placeholder="0" />
        </div>
        <Input label={t("inv.barcode")} value={barcode} onChange={setBarcode} />
        <Input label={t("inv.description")} value={description} onChange={setDescription} />
        <Field label={t("inv.categoryAuto")}>
          <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="ac-sel">
            <option value="">{t("inv.autoDetect")}</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
        <button onClick={save} disabled={busy} className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
          {busy ? t("login.pleaseWait") : t("inv.createItem")}
        </button>
      </div>
    </Modal>
  );
}

function ItemDrawer({ itemId, categories, onClose, onChanged }) {
  const { t, kindName } = useT();
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(false);
  const [correcting, setCorrecting] = useState(false);

  const reload = () => api.get(`/api/items/${itemId}`).then((d) => { setData(d); onChanged?.(); });
  useEffect(() => { api.get(`/api/items/${itemId}`).then(setData); }, [itemId]);

  const voidMovement = async (m) => {
    if (!confirm(t("inv.undoConfirm"))) return;
    await api.post(`/api/movements/${m.id}/void`);
    reload();
    window.dispatchEvent(new CustomEvent("acopio:data-changed"));
  };

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-800">{t("inv.itemDetail")}</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-slate-100"><X size={18} /></button>
        </div>
        {!data ? (
          <div className="text-slate-400">{t("common.loading")}</div>
        ) : editing ? (
          <EditItemForm item={data.item} categories={categories} onCancel={() => setEditing(false)}
            onSaved={() => { setEditing(false); reload(); window.dispatchEvent(new CustomEvent("acopio:data-changed")); }} />
        ) : (
          <>
            <div className="rounded-2xl border border-slate-200 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="text-xl font-bold text-slate-800">{data.item.canonical_name}</div>
                <button onClick={() => setEditing(true)}
                  className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50">
                  <Pencil size={13} /> {t("inv.edit")}
                </button>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <CatBadge kind={data.item.category_kind} name={kindName(data.item.category_kind)} />
                <ExpiryPill status={data.item.expiry_status} date={data.item.earliest_expiry} t={t} />
                {data.item.center && <span className="text-xs text-slate-400">· {data.item.center}</span>}
              </div>
              <div className="mt-3 flex items-end justify-between">
                <div className="text-3xl font-bold text-brand-700">
                  {fmtNum(data.item.quantity)} <span className="text-base font-medium text-slate-400">{data.item.unit}</span>
                </div>
                <button onClick={() => setCorrecting((v) => !v)}
                  className="flex items-center gap-1 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-100">
                  <Wrench size={14} /> {t("inv.correctStock")}
                </button>
              </div>
              <div className="mt-1 text-xs text-slate-400">
                {data.item.barcode ? `${t("inv.barcode")}: ${data.item.barcode} · ` : ""}
                {t("inv.minStock")}: {fmtNum(data.item.min_quantity)}
              </div>
              {correcting && (
                <CorrectStockForm item={data.item} t={t}
                  onDone={() => { setCorrecting(false); reload(); window.dispatchEvent(new CustomEvent("acopio:data-changed")); }} />
              )}
            </div>

            {data.batches?.length > 0 && (
              <>
                <h4 className="mb-2 mt-5 text-sm font-semibold text-slate-700">{t("inv.batches")}</h4>
                <div className="space-y-1.5">
                  {data.batches.map((b) => (
                    <div key={b.id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                      <div>
                        <span className="font-medium text-slate-700">{fmtNum(b.qty_remaining)} {b.unit}</span>
                        {b.lot_code && <span className="ml-1 text-xs text-slate-400">· {b.lot_code}</span>}
                      </div>
                      <ExpiryPill status={b.expiry_status} date={b.expiry_date} t={t} />
                    </div>
                  ))}
                </div>
              </>
            )}

            <h4 className="mb-2 mt-5 text-sm font-semibold text-slate-700">{t("inv.history")}</h4>
            <div className="space-y-2">
              {data.movements.length === 0 ? (
                <div className="text-sm text-slate-400">{t("inv.noMovements")}</div>
              ) : (
                data.movements.map((m) => (
                  <div key={m.id} className={`flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm ${m.voided ? "opacity-50" : ""}`}>
                    <div className="min-w-0">
                      <div className={`font-semibold ${m.voided ? "text-slate-400 line-through" : m.type === "in" ? "text-green-600" : m.type === "out" ? "text-orange-600" : "text-slate-600"}`}>
                        {m.signed_quantity > 0 ? "+" : "−"}{fmtNum(m.quantity)} {m.unit}
                        {m.reason && <span className="ml-1 text-xs font-normal text-slate-400">· {t(`reason.${m.reason}`)}</span>}
                        {m.voided && <span className="ml-1 rounded bg-slate-200 px-1 text-[10px] not-italic text-slate-500 no-underline">{t("inv.voided")}</span>}
                      </div>
                      <div className="text-xs text-slate-400">{m.user_name || "—"} · {m.party || "—"} · {fmtDate(m.created_at)}</div>
                      {m.note && <div className="truncate text-xs italic text-slate-500">"{m.note}"</div>}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-slate-400">{t("inv.balance")} {fmtNum(m.balance_after)}</span>
                      {!m.voided && m.reason !== "correction" && (
                        <button onClick={() => voidMovement(m)} title={t("inv.undo")}
                          className="rounded-lg p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"><Undo2 size={15} /></button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function CorrectStockForm({ item, t, onDone }) {
  const [qty, setQty] = useState(String(item.quantity ?? 0));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.post(`/api/items/${item.id}/correct`, { quantity: Number(qty), note });
      onDone();
    } finally { setBusy(false); }
  };
  return (
    <div className="mt-3 space-y-2 rounded-xl bg-amber-50 p-3">
      <Input label={t("inv.correctTo")} value={qty} onChange={setQty} type="number" />
      <Input label={t("inv.correctNote")} value={note} onChange={setNote} />
      <button onClick={save} disabled={busy}
        className="w-full rounded-lg bg-amber-600 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-60">
        {busy ? t("login.pleaseWait") : t("inv.apply")}
      </button>
    </div>
  );
}

function EditItemForm({ item, categories, onCancel, onSaved }) {
  const { t } = useT();
  const [name, setName] = useState(item.canonical_name);
  const [unit, setUnit] = useState(item.unit);
  const [categoryId, setCategoryId] = useState(item.category_id || "");
  const [minQty, setMinQty] = useState(String(item.min_quantity ?? 0));
  const [barcode, setBarcode] = useState(item.barcode || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async () => {
    if (!name.trim()) return setError(t("inv.nameRequired"));
    setBusy(true);
    try {
      await api.patch(`/api/items/${item.id}`, {
        canonical_name: name, unit, category_id: categoryId || null,
        min_quantity: Number(minQty) || 0, barcode,
      });
      onSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3">
      <Input label={t("inv.name")} value={name} onChange={setName} />
      <div className="grid grid-cols-2 gap-2">
        <Input label={t("inv.unit")} value={unit} onChange={setUnit} />
        <Input label={t("inv.minStock")} value={minQty} onChange={setMinQty} type="number" />
      </div>
      <Input label={t("inv.barcode")} value={barcode} onChange={setBarcode} />
      <label className="block">
        <span className="mb-1 block text-sm font-medium text-slate-600">{t("inv.col.category")}</span>
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="ac-sel">
          <option value="">{t("inv.autoDetect")}</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
      <div className="flex gap-2">
        <button onClick={onCancel} className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
          {t("common.cancel")}
        </button>
        <button onClick={save} disabled={busy} className="flex-1 rounded-xl bg-brand-700 py-2.5 text-sm font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
          {busy ? t("login.pleaseWait") : t("inv.saveChanges")}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-600">{label}</span>
      {children}
      <style>{`.ac-sel{width:100%;border:1px solid #e2e8f0;border-radius:0.75rem;padding:0.5rem 0.75rem;font-size:0.875rem;outline:none}.ac-sel:focus{border-color:#0d9488}`}</style>
    </label>
  );
}

function Input({ label, value, onChange, type = "text", placeholder = "", disabled = false }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-600">{label}</span>
      <input type={type} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500 disabled:bg-slate-50 disabled:text-slate-500" />
    </label>
  );
}
