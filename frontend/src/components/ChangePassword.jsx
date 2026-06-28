import { useState } from "react";
import { CheckCircle2, X } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../lib/i18n.jsx";

export default function ChangePassword({ onClose }) {
  const { t } = useT();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const save = async () => {
    setError("");
    if (next.length < 8) return setError(t("pwd.tooShort"));
    if (next !== confirm) return setError(t("pwd.mismatch"));
    setBusy(true);
    try {
      await api.post("/api/auth/change-password", { current_password: current, new_password: next });
      setDone(true);
      setTimeout(onClose, 1200);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] grid place-items-end p-0 sm:place-items-center sm:p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-t-2xl bg-white p-6 shadow-2xl sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-800">{t("pwd.change")}</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-slate-100"><X size={18} /></button>
        </div>

        {done ? (
          <div className="flex flex-col items-center gap-2 py-6 text-green-600">
            <CheckCircle2 size={36} />
            <div className="font-medium">{t("pwd.success")}</div>
          </div>
        ) : (
          <div className="space-y-3">
            <Field label={t("pwd.current")} value={current} onChange={setCurrent} />
            <Field label={t("pwd.new")} value={next} onChange={setNext} />
            <Field label={t("pwd.confirm")} value={confirm} onChange={setConfirm} />
            {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
            <button onClick={save} disabled={busy}
              className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
              {busy ? t("login.pleaseWait") : t("pwd.save")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, onChange }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-600">{label}</span>
      <input type="password" value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500" />
    </label>
  );
}
