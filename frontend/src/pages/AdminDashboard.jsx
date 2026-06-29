import { useEffect, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowDownLeft, ArrowUpRight, Boxes, CalendarClock, FileText, Globe2, PackageCheck, PackageX, TriangleAlert } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";
import { printReport } from "../lib/print";

export default function AdminDashboard() {
  const { t, lang } = useT();
  const [data, setData] = useState(null);

  useEffect(() => {
    const load = () => api.get("/api/admin/overview").then(setData).catch(() => {});
    load();
    window.addEventListener("acopio:data-changed", load);
    return () => window.removeEventListener("acopio:data-changed", load);
  }, []);

  if (!data) return <div className="text-slate-400">{t("common.loading")}</div>;
  const tot = data.summary.totals;

  const makeReport = async () => {
    const alerts = await api.get("/api/alerts?days=30").catch(() => ({ expiring: [], expired: [] }));
    printReport({ summary: data.summary, alerts, centerName: t("admin.title"), t, lang });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t("admin.title")}</h1>
          <p className="text-sm text-slate-500">{t("admin.subtitle")}</p>
        </div>
        <button onClick={makeReport}
          className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">
          <FileText size={16} /> {t("dash.report")}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4 xl:grid-cols-7">
        <Kpi icon={Globe2} color="#0d9488" label={t("admin.kpi.orgs")} value={fmtNum(data.tenant_count)} />
        <Kpi icon={Boxes} color="#0ea5e9" label={t("dash.kpi.items")} value={fmtNum(tot.items)} />
        <Kpi icon={PackageCheck} color="#6366f1" label={t("dash.kpi.stock")} value={fmtNum(tot.units)} />
        <Kpi icon={ArrowDownLeft} color="#22c55e" label={t("dash.kpi.received")} value={fmtNum(tot.units_in)} />
        <Kpi icon={ArrowUpRight} color="#f97316" label={t("dash.kpi.dispatched")} value={fmtNum(tot.units_out)} />
        <Kpi icon={CalendarClock} color="#d97706" label={t("dash.kpi.expiring")} value={fmtNum(tot.expiring_soon || 0)} />
        <Kpi icon={PackageX} color="#dc2626" label={t("dash.kpi.expired")} value={fmtNum(tot.expired_units || 0)} />
      </div>

      {data.summary.flow?.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">{t("dash.flow")}</h3>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={data.summary.flow} margin={{ left: -20, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="aIn" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} /><stop offset="95%" stopColor="#22c55e" stopOpacity={0} /></linearGradient>
                <linearGradient id="aOut" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#f97316" stopOpacity={0.4} /><stop offset="95%" stopColor="#f97316" stopOpacity={0} /></linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <Tooltip />
              <Area type="monotone" dataKey="in" name={t("dash.received")} stroke="#16a34a" fill="url(#aIn)" strokeWidth={2} />
              <Area type="monotone" dataKey="out" name={t("dash.dispatched")} stroke="#ea580c" fill="url(#aOut)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <h3 className="border-b border-slate-100 px-5 py-3 text-sm font-semibold text-slate-700">{t("admin.byOrg")}</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">{t("admin.col.org")}</th>
                <th className="px-4 py-3">{t("ten.country")}</th>
                <th className="px-4 py-3 text-right">{t("ten.centers")}</th>
                <th className="px-4 py-3 text-right">{t("ten.users")}</th>
                <th className="px-4 py-3 text-right">{t("dash.kpi.items")}</th>
                <th className="px-4 py-3 text-right">{t("dash.kpi.stock")}</th>
                <th className="px-4 py-3 text-right">{t("dash.kpi.expiring")}</th>
                <th className="px-4 py-3 text-right">{t("dash.kpi.expired")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.organizations.map((o) => (
                <tr key={o.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{o.name}</div>
                    <div className="text-xs text-slate-400">{(o.managers || []).join(", ")}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{o.country}</td>
                  <td className="px-4 py-3 text-right">{fmtNum(o.centers)}</td>
                  <td className="px-4 py-3 text-right">{fmtNum(o.users)}</td>
                  <td className="px-4 py-3 text-right">{fmtNum(o.totals.items)}</td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-800">{fmtNum(o.totals.units)}</td>
                  <td className="px-4 py-3 text-right text-amber-600">{fmtNum(o.totals.expiring_soon || 0)}</td>
                  <td className="px-4 py-3 text-right text-red-600">{fmtNum(o.totals.expired_units || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
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
