import { useEffect, useState } from "react";
import { Building2, MapPin, Plus, ShieldCheck, User as UserIcon, Users, X } from "lucide-react";
import { api } from "../lib/api";
import { useT } from "../lib/i18n.jsx";
import { useAuth } from "../lib/auth.jsx";

export default function Organization() {
  const { t, roleName } = useT();
  const { user: me } = useAuth();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("people");
  const [modal, setModal] = useState(null);

  const load = () => api.get("/api/org/overview").then(setData);
  useEffect(() => { load(); }, []);

  const refresh = () => {
    setModal(null);
    load();
    window.dispatchEvent(new CustomEvent("acopio:org-changed"));
  };

  if (!data) return <div className="text-slate-400">{t("common.loading")}</div>;

  const tabs = [
    { id: "people", label: t("org.tab.people"), icon: Users },
    { id: "centers", label: t("org.tab.centers"), icon: Building2 },
  ];
  if (data.can_create_regions || data.regions.length > 0) {
    tabs.push({ id: "regions", label: t("org.tab.regions"), icon: MapPin });
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t("org.title")}</h1>
          <p className="text-sm text-slate-500">{t("org.subtitle")}</p>
        </div>
        <div className="flex gap-2">
          {tab === "people" && (
            <AddBtn onClick={() => setModal({ type: "user" })} label={t("org.newUser")} />
          )}
          {tab === "centers" && data.can_create_centers && (
            <AddBtn onClick={() => setModal({ type: "center" })} label={t("org.newCenter")} />
          )}
          {tab === "regions" && data.can_create_regions && (
            <AddBtn onClick={() => setModal({ type: "region" })} label={t("org.newRegion")} />
          )}
        </div>
      </div>

      <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
        {tabs.map((tb) => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium ${
              tab === tb.id ? "bg-white text-brand-700 shadow-sm" : "text-slate-500"}`}>
            <tb.icon size={16} /> {tb.label}
          </button>
        ))}
      </div>

      {tab === "people" && (
        <PeopleTable data={data} me={me} roleName={roleName} t={t} onChanged={load} />
      )}
      {tab === "centers" && <CentersList data={data} t={t} />}
      {tab === "regions" && <RegionsList data={data} t={t} />}

      {modal?.type === "user" && <UserModal data={data} t={t} roleName={roleName} onClose={() => setModal(null)} onSaved={refresh} />}
      {modal?.type === "center" && <CenterModal data={data} t={t} onClose={() => setModal(null)} onSaved={refresh} />}
      {modal?.type === "region" && <RegionModal t={t} onClose={() => setModal(null)} onSaved={refresh} />}
    </div>
  );
}

function AddBtn({ onClick, label }) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-1.5 rounded-xl bg-brand-700 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-800">
      <Plus size={16} /> {label}
    </button>
  );
}

function PeopleTable({ data, me, roleName, t, onChanged }) {
  const setActive = async (id, active) => {
    await api.post(`/api/org/users/${id}/active`, { active });
    onChanged();
  };
  const people = data.users;
  if (people.length === 0) return <Empty>{t("org.noPeople")}</Empty>;
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">{t("org.col.name")}</th>
            <th className="px-4 py-3">{t("org.col.role")}</th>
            <th className="px-4 py-3">{t("org.col.scope")}</th>
            <th className="px-4 py-3 text-right">{t("org.col.actions")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {people.map((u) => (
            <tr key={u.id} className={u.active ? "" : "opacity-50"}>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-500">
                    {u.role.includes("manager") ? <ShieldCheck size={16} /> : <UserIcon size={16} />}
                  </span>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-slate-700">{u.name}</div>
                    <div className="truncate text-xs text-slate-400">{u.email}</div>
                  </div>
                </div>
              </td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-800">{roleName(u.role)}</span>
              </td>
              <td className="px-4 py-3 text-slate-500">{u.center || u.region || "—"}</td>
              <td className="px-4 py-3">
                <div className="flex items-center justify-end gap-2">
                  {u.id !== me.id ? (
                    <button onClick={() => setActive(u.id, !u.active)}
                      className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                        u.active ? "text-red-600 hover:bg-red-50" : "text-green-600 hover:bg-green-50"}`}>
                      {u.active ? t("org.disable") : t("org.enable")}
                    </button>
                  ) : (
                    <span className="text-xs text-slate-400">{t("common.you")}</span>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CentersList({ data, t }) {
  if (data.centers.length === 0) return <Empty>{t("org.noCenters")}</Empty>;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {data.centers.map((c) => (
        <div key={c.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-50 text-brand-700"><Building2 size={18} /></span>
            <div className="font-semibold text-slate-800">{c.name}</div>
          </div>
          <div className="mt-2 text-xs text-slate-500">{c.region || "—"}{c.location ? ` · ${c.location}` : ""}</div>
        </div>
      ))}
    </div>
  );
}

function RegionsList({ data, t }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {data.regions.map((r) => (
        <div key={r.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-teal-50 text-teal-700"><MapPin size={18} /></span>
            <div className="font-semibold text-slate-800">{r.name}</div>
          </div>
          <div className="mt-2 text-xs text-slate-500">{r.country} · {r.centers ?? 0} {t("org.centersCount")}</div>
        </div>
      ))}
    </div>
  );
}

function ModalShell({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-end p-0 sm:place-items-center sm:p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-t-2xl bg-white p-6 shadow-2xl sm:rounded-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-800">{title}</h3>
          <button onClick={onClose} className="rounded-lg p-1.5 hover:bg-slate-100"><X size={18} /></button>
        </div>
        {children}
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

const inputCls = "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-brand-500";

function UserModal({ data, t, roleName, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(data.assignable_roles[data.assignable_roles.length - 1] || "volunteer");
  const [regionId, setRegionId] = useState(data.regions[0]?.id || "");
  const [centerId, setCenterId] = useState(data.centers[0]?.id || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const needsRegion = role === "regional_manager";
  const needsCenter = role === "center_manager" || role === "volunteer";

  const save = async () => {
    setError("");
    setBusy(true);
    try {
      await api.post("/api/org/users", {
        name, email, password, role,
        region_id: needsRegion ? regionId : null,
        center_id: needsCenter ? centerId : null,
      });
      onSaved();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell title={t("org.newUser")} onClose={onClose}>
      <div className="space-y-3">
        <Field label={t("login.fullName")}><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label={t("login.email")}><input type="email" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label={t("login.password")}><input type="password" className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("login.passwordHint")} /></Field>
        <Field label={t("org.role")}>
          <select className={inputCls} value={role} onChange={(e) => setRole(e.target.value)}>
            {data.assignable_roles.map((r) => <option key={r} value={r}>{roleName(r)}</option>)}
          </select>
        </Field>
        {needsRegion && (
          <Field label={t("org.region")}>
            <select className={inputCls} value={regionId} onChange={(e) => setRegionId(e.target.value)}>
              {data.regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </Field>
        )}
        {needsCenter && (
          <Field label={t("scope.center")}>
            <select className={inputCls} value={centerId} onChange={(e) => setCenterId(e.target.value)}>
              {data.centers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        )}
        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
        <button onClick={save} disabled={busy} className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
          {busy ? t("login.pleaseWait") : t("org.newUser")}
        </button>
      </div>
    </ModalShell>
  );
}

function CenterModal({ data, t, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [regionId, setRegionId] = useState(data.regions[0]?.id || "");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async () => {
    setError("");
    setBusy(true);
    try {
      await api.post("/api/org/centers", { name, region_id: regionId, location });
      onSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <ModalShell title={t("org.newCenter")} onClose={onClose}>
      <div className="space-y-3">
        <Field label={t("org.centerName")}><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label={t("org.region")}>
          <select className={inputCls} value={regionId} onChange={(e) => setRegionId(e.target.value)}>
            {data.regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </Field>
        <Field label={t("org.location")}><input className={inputCls} value={location} onChange={(e) => setLocation(e.target.value)} /></Field>
        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
        <button onClick={save} disabled={busy} className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
          {busy ? t("login.pleaseWait") : t("common.create")}
        </button>
      </div>
    </ModalShell>
  );
}

function RegionModal({ t, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [country, setCountry] = useState("Venezuela");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async () => {
    setError("");
    setBusy(true);
    try {
      await api.post("/api/org/regions", { name, country });
      onSaved();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  return (
    <ModalShell title={t("org.newRegion")} onClose={onClose}>
      <div className="space-y-3">
        <Field label={t("org.regionName")}><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label={t("org.country")}><input className={inputCls} value={country} onChange={(e) => setCountry(e.target.value)} /></Field>
        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
        <button onClick={save} disabled={busy} className="w-full rounded-xl bg-brand-700 py-2.5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60">
          {busy ? t("login.pleaseWait") : t("common.create")}
        </button>
      </div>
    </ModalShell>
  );
}

function Empty({ children }) {
  return <div className="grid h-40 place-items-center rounded-2xl border border-dashed border-slate-300 text-center text-sm text-slate-400">{children}</div>;
}
