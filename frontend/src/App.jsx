import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Boxes,
  Upload as UploadIcon,
  History,
  Building2,
  Bell,
  ClipboardList,
  Sparkles,
  LogOut,
  KeyRound,
  Menu,
  X,
} from "lucide-react";
import { useAuth } from "./lib/auth.jsx";
import { useT } from "./lib/i18n.jsx";
import { useScope } from "./lib/scope.jsx";
import ChangePassword from "./components/ChangePassword.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Inventory from "./pages/Inventory.jsx";
import Upload from "./pages/Upload.jsx";
import Activity from "./pages/Activity.jsx";
import Organization from "./pages/Organization.jsx";
import Alerts from "./pages/Alerts.jsx";
import Needs from "./pages/Needs.jsx";
import Assistant from "./components/Assistant.jsx";

function NavItem({ to, icon: Icon, label, onClick }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
          isActive ? "bg-brand-700 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
        }`
      }
    >
      <Icon size={18} />
      {label}
    </NavLink>
  );
}

function LangToggle() {
  const { lang, setLang } = useT();
  return (
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
  );
}

function CenterSelector() {
  const { t } = useT();
  const { centers, needsCenterPicker, fixedCenter, activeCenter, setActiveCenter } = useScope();

  if (fixedCenter) {
    const c = centers.find((x) => x.id === fixedCenter);
    return (
      <span className="hidden items-center gap-1.5 rounded-lg bg-brand-50 px-2.5 py-1.5 text-xs font-semibold text-brand-700 sm:inline-flex">
        <Building2 size={14} /> {c?.name || t("scope.center")}
      </span>
    );
  }
  if (!needsCenterPicker) return null;
  return (
    <select
      value={activeCenter}
      onChange={(e) => setActiveCenter(e.target.value)}
      className="max-w-[10rem] rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-medium text-slate-600 outline-none focus:border-brand-500"
      title={t("scope.center")}
    >
      <option value="">{t("scope.allCenters")}</option>
      {centers.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );
}

export default function App() {
  const { user, loading, logout } = useAuth();
  const { t, roleName } = useT();
  const navigate = useNavigate();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [pwdOpen, setPwdOpen] = useState(false);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        <div className="animate-pulse text-lg">{t("common.loading")}</div>
      </div>
    );
  }

  if (!user) return <Login />;

  const canManageOrg = user.role !== "volunteer";

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-2 py-1">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-700 text-xl text-white">📦</div>
        <div>
          <div className="text-lg font-bold leading-tight text-slate-800">Acopio</div>
          <div className="text-[11px] text-slate-400">{t("app.tagline")}</div>
        </div>
      </div>

      <nav className="mt-6 flex flex-1 flex-col gap-1">
        <NavItem to="/" icon={LayoutDashboard} label={t("nav.dashboard")} onClick={() => setMobileNav(false)} />
        <NavItem to="/inventory" icon={Boxes} label={t("nav.inventory")} onClick={() => setMobileNav(false)} />
        <NavItem to="/alerts" icon={Bell} label={t("nav.alerts")} onClick={() => setMobileNav(false)} />
        <NavItem to="/needs" icon={ClipboardList} label={t("nav.needs")} onClick={() => setMobileNav(false)} />
        <NavItem to="/upload" icon={UploadIcon} label={t("nav.import")} onClick={() => setMobileNav(false)} />
        <NavItem to="/activity" icon={History} label={t("nav.activity")} onClick={() => setMobileNav(false)} />
        {canManageOrg && (
          <NavItem to="/organization" icon={Building2} label={t("nav.organization")} onClick={() => setMobileNav(false)} />
        )}
      </nav>

      <button
        onClick={() => {
          setAssistantOpen(true);
          setMobileNav(false);
        }}
        className="mb-3 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-teal-500 px-3 py-2.5 text-sm font-semibold text-white shadow hover:opacity-95"
      >
        <Sparkles size={18} /> {t("nav.assistant")}
      </button>

      <div className="border-t border-slate-200 pt-3">
        <div className="flex items-center justify-between gap-2 px-1">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-700">{user.name}</div>
            <div className="truncate text-xs text-slate-400">{roleName(user.role)}</div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                setPwdOpen(true);
                setMobileNav(false);
              }}
              title={t("pwd.change")}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              <KeyRound size={18} />
            </button>
            <button
              onClick={async () => {
                await logout();
                navigate("/");
              }}
              title={t("nav.logout")}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white p-4 md:block">{sidebar}</aside>

      {mobileNav && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileNav(false)} />
          <aside className="absolute left-0 top-0 h-full w-72 bg-white p-4 shadow-xl">{sidebar}</aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2.5 md:px-6">
          <button onClick={() => setMobileNav(true)} className="rounded-lg p-2 hover:bg-slate-100 md:hidden">
            <Menu size={20} />
          </button>
          <div className="font-bold md:hidden">📦 Acopio</div>
          <div className="ml-auto flex items-center gap-2">
            <CenterSelector />
            <LangToggle />
            <button
              onClick={() => setAssistantOpen(true)}
              className="grid h-9 w-9 place-items-center rounded-lg bg-brand-50 text-brand-700 hover:bg-brand-100 md:hidden"
            >
              <Sparkles size={18} />
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 md:p-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/needs" element={<Needs />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/activity" element={<Activity />} />
            <Route path="/organization" element={canManageOrg ? <Organization /> : <Navigate to="/" />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>

      {assistantOpen && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/30" onClick={() => setAssistantOpen(false)} />
          <div className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div className="flex items-center gap-2 font-semibold text-slate-800">
                <Sparkles size={18} className="text-brand-600" /> {t("ai.title")}
              </div>
              <button onClick={() => setAssistantOpen(false)} className="rounded-lg p-2 hover:bg-slate-100">
                <X size={18} />
              </button>
            </div>
            <Assistant />
          </div>
        </div>
      )}

      {pwdOpen && <ChangePassword onClose={() => setPwdOpen(false)} />}
    </div>
  );
}
