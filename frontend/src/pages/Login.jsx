import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth.jsx";
import { useT } from "../lib/i18n.jsx";
import { api } from "../lib/api";

export default function Login() {
  const { login, register } = useAuth();
  const { t, lang, setLang } = useT();
  const [needsBootstrap, setNeedsBootstrap] = useState(false);
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get("/api/auth/bootstrap")
      .then((d) => {
        setNeedsBootstrap(d.needs_bootstrap);
        if (d.needs_bootstrap) setMode("register");
      })
      .catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, name, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative flex min-h-full items-center justify-center bg-gradient-to-br from-brand-50 via-slate-50 to-teal-50 p-4 sm:p-6">
      <div className="absolute right-4 top-4">
        <div className="flex overflow-hidden rounded-lg border border-slate-200 text-xs font-semibold">
          {["es", "en"].map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`px-2.5 py-1.5 uppercase ${lang === l ? "bg-brand-700 text-white" : "bg-white text-slate-500"}`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <div className="grid w-full max-w-4xl overflow-hidden rounded-3xl bg-white shadow-xl md:grid-cols-2">
        <div className="hidden flex-col justify-between bg-gradient-to-br from-brand-700 to-teal-600 p-10 text-white md:flex">
          <div>
            <div className="text-3xl">📦</div>
            <h1 className="mt-4 text-3xl font-bold">Acopio</h1>
            <p className="mt-2 text-brand-100">{t("app.tagline")}</p>
          </div>
          <ul className="space-y-3 text-sm text-brand-50">
            <li>{t("login.b1")}</li>
            <li>{t("login.b2")}</li>
            <li>{t("login.b3")}</li>
            <li>{t("login.b4")}</li>
            <li>{t("login.b5")}</li>
          </ul>
          <p className="text-xs text-brand-200">{t("login.footer")}</p>
        </div>

        <div className="p-8 md:p-10">
          <h2 className="text-2xl font-bold text-slate-800">
            {mode === "login" ? t("login.welcome") : t("login.createFirst")}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {mode === "login" ? t("login.subtitleLogin") : t("login.subtitleFirst")}
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            {mode === "register" && (
              <Field label={t("login.fullName")}>
                <input className="ac-input" value={name} onChange={(e) => setName(e.target.value)} required />
              </Field>
            )}
            <Field label={t("login.email")}>
              <input type="email" className="ac-input" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field label={t("login.password")}>
              <input
                type="password"
                className="ac-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t("login.passwordHint")}
                required
              />
            </Field>

            {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}

            <button
              disabled={busy}
              className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white shadow hover:bg-brand-800 disabled:opacity-60"
            >
              {busy ? t("login.pleaseWait") : mode === "login" ? t("login.logIn") : t("login.createAccount")}
            </button>
          </form>

          {!needsBootstrap && (
            <p className="mt-6 text-center text-xs text-slate-400">{t("login.closed")}</p>
          )}
        </div>
      </div>

      <style>{`
        .ac-input { width:100%; border:1px solid #e2e8f0; border-radius:0.75rem; padding:0.6rem 0.8rem; font-size:0.9rem; outline:none; }
        .ac-input:focus { border-color:#0d9488; box-shadow:0 0 0 3px rgba(13,148,136,0.15); }
      `}</style>
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
