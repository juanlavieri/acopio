import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileSpreadsheet, Loader2, UploadCloud } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";
import { useScope } from "../lib/scope.jsx";

export default function Upload() {
  const { t } = useT();
  const scope = useScope();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [drag, setDrag] = useState(false);
  const [centerId, setCenterId] = useState(scope.actionCenter || "");
  const inputRef = useRef();

  const loadHistory = () => api.get("/api/uploads").then((d) => setHistory(d.uploads));
  useEffect(() => { loadHistory(); }, []);
  useEffect(() => { setCenterId(scope.actionCenter || ""); }, [scope.actionCenter]);

  const handleFile = async (file) => {
    if (!file) return;
    if (scope.needsCenterPicker && !centerId) {
      setError(t("inv.selectCenterFirst"));
      return;
    }
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (centerId) fd.append("center_id", centerId);
      const res = await api.upload("/api/uploads", fd);
      setResult(res);
      loadHistory();
      window.dispatchEvent(new CustomEvent("acopio:data-changed"));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t("up.title")}</h1>
        <p className="text-sm text-slate-500">{t("up.subtitle")}</p>
      </div>

      {scope.needsCenterPicker && (
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-slate-600">{t("up.intoCenter")}</span>
          <select value={centerId} onChange={(e) => setCenterId(e.target.value)}
            className="w-full max-w-sm rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500">
            <option value="">{t("scope.selectCenter")}</option>
            {scope.centers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
      )}

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files?.[0]); }}
        onClick={() => inputRef.current?.click()}
        className={`grid cursor-pointer place-items-center rounded-3xl border-2 border-dashed p-10 text-center transition sm:p-12 ${
          drag ? "border-brand-500 bg-brand-50" : "border-slate-300 bg-white hover:border-brand-400"
        }`}
      >
        <input ref={inputRef} type="file" hidden accept=".xlsx,.xlsm,.csv,.tsv,.txt,.json,.pdf,.docx"
          onChange={(e) => handleFile(e.target.files?.[0])} />
        {busy ? (
          <div className="flex flex-col items-center gap-3 text-brand-700">
            <Loader2 className="animate-spin" size={40} />
            <div className="font-medium">{t("up.normalizing")}</div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="grid h-16 w-16 place-items-center rounded-2xl bg-brand-100 text-brand-700">
              <UploadCloud size={30} />
            </div>
            <div className="font-semibold text-slate-700">{t("up.drop")}</div>
            <div className="text-xs text-slate-400">.xlsx · .csv · .tsv · .json · .pdf · .docx</div>
          </div>
        )}
      </div>

      {error && <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>}

      {result && (
        <div className="rounded-2xl border border-green-200 bg-green-50 p-5">
          <div className="flex items-center gap-2 font-semibold text-green-700">
            <CheckCircle2 size={20} /> {t("up.complete")}
          </div>
          <p className="mt-1 text-sm text-green-800">{result.result.summary}</p>
          <div className="mt-3 grid grid-cols-3 gap-3 text-center">
            <Stat label={t("up.rowsRead")} value={result.result.rows} />
            <Stat label={t("up.newItems")} value={result.result.created} />
            <Stat label={t("up.merged")} value={result.result.matched} />
          </div>
          {result.upload.mapping?.sheets?.[0]?.mapping && (
            <div className="mt-4">
              <div className="text-xs font-semibold uppercase text-green-700">{t("up.mapping")}</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {Object.entries(result.upload.mapping.sheets[0].mapping).filter(([, v]) => v).map(([field, col]) => (
                  <span key={field} className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-600">
                    <b className="text-brand-700">{field}</b> ← {col}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">{t("up.recent")}</h3>
        <div className="space-y-2">
          {history.length === 0 ? (
            <div className="text-sm text-slate-400">{t("up.noImports")}</div>
          ) : (
            history.map((u) => (
              <div key={u.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
                <div className="flex min-w-0 items-center gap-3">
                  <FileSpreadsheet size={18} className="shrink-0 text-brand-600" />
                  <div className="min-w-0">
                    <div className="truncate font-medium text-slate-700">{u.filename}</div>
                    <div className="text-xs text-slate-400">{u.user_name} · {fmtDate(u.created_at)}</div>
                  </div>
                </div>
                <div className="shrink-0 text-right text-xs text-slate-500">
                  <StatusPill status={u.status} />
                  <div className="mt-0.5">{u.rows_detected} · {u.items_created} new</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl bg-white py-2">
      <div className="text-xl font-bold text-slate-800">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    done: "bg-green-100 text-green-700",
    error: "bg-red-100 text-red-700",
    processing: "bg-amber-100 text-amber-700",
    pending: "bg-slate-100 text-slate-600",
  };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${map[status] || map.pending}`}>{status}</span>;
}
