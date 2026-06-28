import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { ArrowDownLeft, ArrowUpRight, Check, Loader2, X } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum, kindColor } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";
import { useScope } from "../lib/scope.jsx";

export default function Scanner({ onClose }) {
  const { t, kindName } = useT();
  const scope = useScope();
  const [phase, setPhase] = useState("scan"); // scan | loading | result | notfound
  const [item, setItem] = useState(null);
  const [code, setCode] = useState("");
  const [manual, setManual] = useState("");
  const [msg, setMsg] = useState("");
  const scannerRef = useRef(null);
  const runningRef = useRef(false);

  const stop = async () => {
    const s = scannerRef.current;
    if (s && runningRef.current) {
      try { await s.stop(); } catch { /* ignore */ }
      runningRef.current = false;
    }
  };

  const start = async () => {
    setPhase("scan"); setItem(null); setMsg("");
    await new Promise((r) => setTimeout(r, 80)); // let the target div mount
    try {
      const s = new Html5Qrcode("acopio-reader", { verbose: false });
      scannerRef.current = s;
      runningRef.current = true;
      await s.start({ facingMode: "environment" }, { fps: 10, qrbox: 240 },
        (decoded) => handleCode(decoded), () => {});
    } catch {
      runningRef.current = false;
      setMsg(t("scan.cameraError"));
    }
  };

  useEffect(() => {
    start();
    return () => { stop(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCode = async (text) => {
    await stop();
    setPhase("loading"); setCode(text); setMsg("");
    try {
      const { item } = await api.get(`/api/items/lookup?code=${encodeURIComponent(text)}`);
      setItem(item); setPhase("result");
    } catch {
      setPhase("notfound");
    }
  };

  const close = async () => { await stop(); onClose(); };
  const fireChanged = () => window.dispatchEvent(new CustomEvent("acopio:data-changed"));

  return (
    <div className="fixed inset-0 z-[60] grid place-items-end p-0 sm:place-items-center sm:p-4">
      <div className="absolute inset-0 bg-black/50" onClick={close} />
      <div className="relative w-full max-w-md overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <div className="font-semibold text-slate-800">{t("scan.title")}</div>
          <button onClick={close} className="rounded-lg p-1.5 hover:bg-slate-100"><X size={18} /></button>
        </div>

        <div className="p-4">
          {phase === "scan" && (
            <>
              <div id="acopio-reader" className="overflow-hidden rounded-xl bg-black" style={{ minHeight: 240 }} />
              <p className="mt-2 text-center text-xs text-slate-500">{t("scan.hint")}</p>
              {msg && <div className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">{msg}</div>}
              <div className="mt-3 flex gap-2">
                <input value={manual} onChange={(e) => setManual(e.target.value)} placeholder={t("scan.manual")}
                  className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
                <button onClick={() => manual.trim() && handleCode(manual.trim())}
                  className="rounded-xl bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800">{t("scan.find")}</button>
              </div>
            </>
          )}

          {phase === "loading" && (
            <div className="flex items-center justify-center gap-2 py-10 text-slate-400">
              <Loader2 className="animate-spin" size={20} /> {t("common.loading")}
            </div>
          )}

          {phase === "result" && item && (
            <ResultPanel item={item} t={t} kindName={kindName} onChanged={fireChanged}
              onAgain={start} setItem={setItem} />
          )}

          {phase === "notfound" && (
            <NotFound code={code} scope={scope} t={t} onCreated={(it) => { setItem(it); setPhase("result"); fireChanged(); }}
              onAgain={start} />
          )}
        </div>
      </div>
    </div>
  );
}

function ResultPanel({ item, t, kindName, onChanged, onAgain, setItem }) {
  const [count, setCount] = useState(String(item.quantity ?? 0));
  const [qty, setQty] = useState("");
  const [flash, setFlash] = useState("");
  const color = kindColor(item.category_kind);

  const refresh = async () => {
    const { item: it } = await api.get(`/api/items/${item.id}`);
    setItem(it); setCount(String(it.quantity ?? 0));
  };
  const saveCount = async () => {
    await api.post(`/api/items/${item.id}/correct`, { quantity: Number(count), note: "Count via scan" });
    await refresh(); onChanged(); flashMsg();
  };
  const move = async (type) => {
    if (!qty) return;
    await api.post("/api/movements", { item_id: item.id, type, quantity: Number(qty) });
    setQty(""); await refresh(); onChanged(); flashMsg();
  };
  const flashMsg = () => { setFlash(t("scan.saved")); setTimeout(() => setFlash(""), 1500); };

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-slate-200 p-4">
        <div className="text-lg font-bold text-slate-800">{item.canonical_name}</div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full px-2 py-0.5 font-medium" style={{ background: `${color}1a`, color }}>{kindName(item.category_kind)}</span>
          {item.center && <span className="text-slate-400">{item.center}</span>}
          {item.barcode && <span className="font-mono text-slate-400">{item.barcode}</span>}
        </div>
        <div className="mt-2 text-3xl font-bold text-brand-700">
          {fmtNum(item.quantity)} <span className="text-base font-medium text-slate-400">{item.unit}</span>
        </div>
      </div>

      <div className="rounded-xl bg-slate-50 p-3">
        <label className="mb-1 block text-sm font-medium text-slate-600">{t("scan.count")}</label>
        <div className="flex gap-2">
          <input type="number" value={count} onChange={(e) => setCount(e.target.value)}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <button onClick={saveCount} className="rounded-lg bg-amber-600 px-3 py-2 text-sm font-semibold text-white hover:bg-amber-700">{t("scan.saveCount")}</button>
        </div>
      </div>

      <div className="rounded-xl bg-slate-50 p-3">
        <label className="mb-1 block text-sm font-medium text-slate-600">{t("scan.qty")}</label>
        <div className="flex gap-2">
          <input type="number" value={qty} onChange={(e) => setQty(e.target.value)}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
          <button onClick={() => move("in")} className="flex items-center gap-1 rounded-lg bg-green-50 px-3 py-2 text-sm font-semibold text-green-700 hover:bg-green-100"><ArrowDownLeft size={15} />{t("scan.in")}</button>
          <button onClick={() => move("out")} className="flex items-center gap-1 rounded-lg bg-orange-50 px-3 py-2 text-sm font-semibold text-orange-700 hover:bg-orange-100"><ArrowUpRight size={15} />{t("scan.out")}</button>
        </div>
      </div>

      {flash && <div className="flex items-center justify-center gap-1 text-sm font-medium text-green-600"><Check size={16} /> {flash}</div>}
      <button onClick={onAgain} className="w-full rounded-xl border border-slate-200 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50">{t("scan.again")}</button>
    </div>
  );
}

function NotFound({ code, scope, t, onCreated, onAgain }) {
  const [name, setName] = useState("");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const create = async () => {
    if (!name.trim()) return;
    if (scope.needsCenterPicker && !scope.actionCenter) return setError(t("inv.selectCenterFirst"));
    setBusy(true);
    try {
      const { item } = await api.post("/api/items", {
        name, barcode: code, center_id: scope.actionCenter || null,
      });
      if (qty) await api.post("/api/movements", { item_id: item.id, type: "in", quantity: Number(qty) });
      const { item: fresh } = await api.get(`/api/items/${item.id}`);
      onCreated(fresh);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3">
      <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
        {t("scan.notFound")} <span className="font-mono">{code}</span>
      </div>
      <div className="text-sm font-medium text-slate-600">{t("scan.createWith")}</div>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("inv.name")}
        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
      <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} placeholder={t("scan.qty")}
        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
      {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
      <div className="flex gap-2">
        <button onClick={onAgain} className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">{t("scan.again")}</button>
        <button onClick={create} disabled={busy} className="flex-1 rounded-xl bg-brand-700 py-2.5 text-sm font-semibold text-white hover:bg-brand-800 disabled:opacity-60">{busy ? t("login.pleaseWait") : t("common.create")}</button>
      </div>
    </div>
  );
}
