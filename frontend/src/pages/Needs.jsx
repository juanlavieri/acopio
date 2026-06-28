import { useCallback, useEffect, useState } from "react";
import { Check, Plus, X } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum, priorityColor } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";
import { useScope } from "../lib/scope.jsx";

const PRIORITIES = ["urgent", "high", "normal", "low"];

export default function Needs() {
  const { t } = useT();
  const scope = useScope();
  const [needs, setNeeds] = useState([]);
  const [modal, setModal] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    const qs = scope.viewCenter ? `?center_id=${scope.viewCenter}` : "";
    api.get(`/api/needs${qs}`).then((d) => setNeeds(d.needs));
  }, [scope.viewCenter]);

  useEffect(() => { load(); }, [load]);

  const fulfill = async (id) => {
    setError("");
    try {
      await api.post(`/api/needs/${id}/fulfill`, {});
      load();
      window.dispatchEvent(new CustomEvent("acopio:data-changed"));
    } catch (e) { setError(e.message); }
  };
  const cancel = async (id) => {
    await api.patch(`/api/needs/${id}`, { status: "cancelled" });
    load();
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t("needs.title")}</h1>
          <p className="text-sm text-slate-500">{t("needs.subtitle")}</p>
        </div>
        <button onClick={() => setModal(true)}
          className="flex items-center gap-1.5 rounded-xl bg-brand-700 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-800">
          <Plus size={16} /> {t("needs.new")}
        </button>
      </div>

      {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}

      {needs.length === 0 ? (
        <div className="grid h-40 place-items-center rounded-2xl border border-dashed border-slate-300 text-sm text-slate-400">
          {t("needs.empty")}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {needs.map((n) => {
            const pct = n.quantity > 0 ? Math.min(100, Math.round((n.fulfilled_quantity / n.quantity) * 100)) : 0;
            const done = n.status === "fulfilled" || n.status === "cancelled";
            return (
              <div key={n.id} className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm ${done ? "opacity-60" : ""}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate font-semibold text-slate-800">{n.item_name}</div>
                    <div className="text-xs text-slate-400">{n.center || ""} · {n.requester || ""}</div>
                  </div>
                  <span className="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold"
                    style={{ background: `${priorityColor(n.priority)}1a`, color: priorityColor(n.priority) }}>
                    {t(`prio.${n.priority}`)}
                  </span>
                </div>

                <div className="mt-3 text-sm text-slate-600">
                  {fmtNum(n.fulfilled_quantity)} {t("needs.of")} {fmtNum(n.quantity)} {n.unit} {t("needs.fulfilled_label")}
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-brand-600" style={{ width: `${pct}%` }} />
                </div>

                <div className="mt-3 flex items-center justify-between">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                    {t(`needs.status.${n.status}`)}
                  </span>
                  {!done && (
                    <div className="flex gap-2">
                      <button onClick={() => cancel(n.id)} className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-slate-100">
                        {t("common.cancel")}
                      </button>
                      <button onClick={() => fulfill(n.id)}
                        className="flex items-center gap-1 rounded-lg bg-brand-700 px-2.5 py-1 text-xs font-semibold text-white hover:bg-brand-800">
                        <Check size={14} /> {t("needs.fulfill")}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {modal && <NeedModal scope={scope} t={t} onClose={() => setModal(false)} onSaved={() => { setModal(false); load(); }} />}
    </div>
  );
}

function NeedModal({ scope, t, onClose, onSaved }) {
  const [itemName, setItemName] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState("unit");
  const [priority, setPriority] = useState("normal");
  const [neededBy, setNeededBy] = useState("");
  const [note, setNote] = useState("");
  const [centerId, setCenterId] = useState(scope.actionCenter || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setError("");
    if (!itemName.trim() || !quantity) return setError(t("inv.required"));
    if (scope.needsCenterPicker && !centerId) return setError(t("inv.selectCenterFirst"));
    setBusy(true);
    try {
      await api.post("/api/needs", {
        item_name: itemName, quantity: Number(quantity), unit, priority,
        needed_by: neededBy || null, note, center_id: centerId || null,
      });
      onSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-end p-0 sm:place-items-center sm:p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative max-h-[92vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-6 shadow-2xl sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-800">{t("needs.new")}</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-slate-100"><X size={18} /></button>
        </div>
        <div className="space-y-3">
          {scope.needsCenterPicker && (
            <Field label={t("scope.center")}>
              <select value={centerId} onChange={(e) => setCenterId(e.target.value)} className="ac-sel2">
                <option value="">{t("scope.selectCenter")}</option>
                {scope.centers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
          )}
          <Inp label={t("needs.item")} value={itemName} onChange={setItemName} />
          <div className="grid grid-cols-2 gap-2">
            <Inp label={t("needs.quantity")} value={quantity} onChange={setQuantity} type="number" />
            <Inp label={t("needs.unit")} value={unit} onChange={setUnit} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label={t("needs.priority")}>
              <select value={priority} onChange={(e) => setPriority(e.target.value)} className="ac-sel2">
                {PRIORITIES.map((p) => <option key={p} value={p}>{t(`prio.${p}`)}</option>)}
              </select>
            </Field>
            <Inp label={t("needs.neededBy")} value={neededBy} onChange={setNeededBy} type="date" />
          </div>
          <Inp label={t("needs.note")} value={note} onChange={setNote} />
          {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
          <button onClick={save} disabled={busy} className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
            {busy ? t("login.pleaseWait") : t("needs.create")}
          </button>
        </div>
        <style>{`.ac-sel2{width:100%;border:1px solid #e2e8f0;border-radius:0.75rem;padding:0.5rem 0.75rem;font-size:0.875rem;outline:none}.ac-sel2:focus{border-color:#0d9488}`}</style>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-600">{label}</span>
      {children}
    </label>
  );
}
function Inp({ label, value, onChange, type = "text" }) {
  return (
    <Field label={label}>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
    </Field>
  );
}
