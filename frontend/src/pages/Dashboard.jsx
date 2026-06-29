import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowDownLeft, ArrowUpRight, Boxes, CalendarClock, FileText, PackageCheck, PackageX, TriangleAlert } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum, fmtDate, kindColor } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";
import { useScope } from "../lib/scope.jsx";
import { useAuth } from "../lib/auth.jsx";
import { printReport } from "../lib/print";
import AdminDashboard from "./AdminDashboard.jsx";

export default function Dashboard() {
  const { user } = useAuth();
  if (user?.role === "super_admin") return <AdminDashboard />;
  return <TenantDashboard />;
}

function TenantDashboard() {
  const { t, kindName, lang } = useT();
  const { viewCenter, centers } = useScope();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const makeReport = async () => {
    const qs = viewCenter ? `?center_id=${viewCenter}` : "";
    const [summary, alerts] = await Promise.all([
      api.get(`/api/dashboard/summary${qs}`),
      api.get(`/api/alerts?days=30${viewCenter ? `&center_id=${viewCenter}` : ""}`).catch(() => ({ expiring: [], expired: [] })),
    ]);
    const centerName = viewCenter ? centers.find((c) => c.id === viewCenter)?.name : null;
    printReport({ summary, alerts, centerName, t, lang });
  };

  useEffect(() => {
    const load = () => {
      const qs = viewCenter ? `?center_id=${viewCenter}` : "";
      api.get(`/api/dashboard/summary${qs}`).then(setData).catch((e) => setError(e.message));
    };
    load();
    window.addEventListener("acopio:data-changed", load);
    return () => window.removeEventListener("acopio:data-changed", load);
  }, [viewCenter]);

  if (error) return <div className="text-red-600">{error}</div>;
  if (!data) return <div className="text-slate-400">{t("common.loading")}</div>;

  const tot = data.totals;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t("dash.title")}</h1>
          <p className="text-sm text-slate-500">{t("dash.subtitle")}</p>
        </div>
        <button onClick={makeReport}
          className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
          <FileText size={16} /> {t("dash.report")}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4 xl:grid-cols-7">
        <Kpi icon={Boxes} color="#0d9488" label={t("dash.kpi.items")} value={fmtNum(tot.items)} />
        <Kpi icon={PackageCheck} color="#0ea5e9" label={t("dash.kpi.stock")} value={fmtNum(tot.units)} />
        <Kpi icon={ArrowDownLeft} color="#22c55e" label={t("dash.kpi.received")} value={fmtNum(tot.units_in)} />
        <Kpi icon={ArrowUpRight} color="#f97316" label={t("dash.kpi.dispatched")} value={fmtNum(tot.units_out)} />
        <Kpi icon={TriangleAlert} color="#ef4444" label={t("dash.kpi.low")} value={fmtNum(tot.low_stock)} />
        <Kpi icon={CalendarClock} color="#d97706" label={t("dash.kpi.expiring")} value={fmtNum(tot.expiring_soon || 0)} />
        <Kpi icon={PackageX} color="#dc2626" label={t("dash.kpi.expired")} value={fmtNum(tot.expired_units || 0)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={t("dash.flow")} className="lg:col-span-2">
          {data.flow.length === 0 ? (
            <Empty>{t("dash.flow.empty")}</Empty>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={data.flow} margin={{ left: -20, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="gIn" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gOut" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f97316" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <Tooltip />
                <Area type="monotone" dataKey="in" name={t("dash.received")} stroke="#16a34a" fill="url(#gIn)" strokeWidth={2} />
                <Area type="monotone" dataKey="out" name={t("dash.dispatched")} stroke="#ea580c" fill="url(#gOut)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title={t("dash.byCategory")}>
          {data.by_category.filter((c) => c.units > 0).length === 0 ? (
            <Empty>{t("dash.noStock")}</Empty>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={data.by_category.filter((c) => c.units > 0)}
                    dataKey="units"
                    nameKey="name"
                    innerRadius={50}
                    outerRadius={85}
                    paddingAngle={2}
                  >
                    {data.by_category.filter((c) => c.units > 0).map((c, i) => (
                      <Cell key={i} fill={kindColor(c.kind)} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-2 flex flex-wrap gap-2">
                {data.by_category.filter((c) => c.units > 0).map((c) => (
                  <span key={c.name} className="flex items-center gap-1.5 text-xs text-slate-600">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: kindColor(c.kind) }} />
                    {kindName(c.kind)}
                  </span>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={t("dash.topItems")} className="lg:col-span-2">
          {data.top_items.length === 0 ? (
            <Empty>{t("dash.noItems")}</Empty>
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(180, data.top_items.length * 34)}>
              <BarChart data={data.top_items} layout="vertical" margin={{ left: 20, right: 16 }}>
                <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11 }} stroke="#64748b" />
                <Tooltip />
                <Bar dataKey="quantity" name={t("dash.inStock")} fill="#0d9488" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title={t("dash.volActivity")}>
          {data.by_volunteer.length === 0 ? (
            <Empty>{t("dash.noActivity")}</Empty>
          ) : (
            <ul className="space-y-2">
              {data.by_volunteer.map((v) => (
                <li key={v.name} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                  <span className="font-medium text-slate-700">{v.name}</span>
                  <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">
                    {v.movements} {t("dash.moves")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title={t("dash.recent")}>
        {data.recent_movements.length === 0 ? (
          <Empty>{t("dash.noMovements")}</Empty>
        ) : (
          <div className="divide-y divide-slate-100">
            {data.recent_movements.map((m) => (
              <div key={m.id} className="flex items-center justify-between py-2.5 text-sm">
                <div className="flex items-center gap-3">
                  <span
                    className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${
                      m.type === "in" ? "bg-green-100 text-green-600" : "bg-orange-100 text-orange-600"
                    }`}
                  >
                    {m.type === "in" ? <ArrowDownLeft size={16} /> : <ArrowUpRight size={16} />}
                  </span>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-slate-700">{m.item_name}</div>
                    <div className="truncate text-xs text-slate-400">
                      {m.user_name || "—"} · {m.party || t("dash.noParty")} · {fmtDate(m.created_at)}
                    </div>
                  </div>
                </div>
                <div className={`shrink-0 font-semibold ${m.type === "in" ? "text-green-600" : "text-orange-600"}`}>
                  {m.type === "in" ? "+" : "−"}
                  {fmtNum(m.quantity)} {m.unit}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function Kpi({ icon: Icon, color, label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg" style={{ background: `${color}1a`, color }}>
          <Icon size={16} />
        </span>
        <span className="text-xs font-medium text-slate-500">{label}</span>
      </div>
      <div className="mt-2 text-2xl font-bold text-slate-800">{value}</div>
    </div>
  );
}

function Card({ title, children, className = "" }) {
  return (
    <div className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      <h3 className="mb-3 text-sm font-semibold text-slate-700">{title}</h3>
      {children}
    </div>
  );
}

function Empty({ children }) {
  return <div className="grid h-40 place-items-center text-center text-sm text-slate-400">{children}</div>;
}
