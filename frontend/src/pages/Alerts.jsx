import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CalendarClock, PackageX, Trash2, TriangleAlert } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";
import { useScope } from "../lib/scope.jsx";

export default function Alerts() {
  const { t } = useT();
  const { viewCenter } = useScope();
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    const qs = viewCenter ? `&center_id=${viewCenter}` : "";
    api.get(`/api/alerts?days=30${qs}`).then(setData);
  }, [viewCenter]);

  useEffect(() => {
    load();
    window.addEventListener("acopio:data-changed", load);
    return () => window.removeEventListener("acopio:data-changed", load);
  }, [load]);

  const dispose = async (b) => {
    if (!confirm(t("alerts.disposeConfirm", { qty: `${fmtNum(b.qty_remaining)} ${b.unit}`, name: b.item_name }))) return;
    await api.post("/api/movements", {
      item_id: b.item_id, type: "out", quantity: b.qty_remaining, reason: "expired",
      note: `Expired lot ${b.lot_code || ""}`.trim(),
    });
    load();
    window.dispatchEvent(new CustomEvent("acopio:data-changed"));
  };

  if (!data) return <div className="text-slate-400">{t("common.loading")}</div>;

  const empty = !data.expired.length && !data.expiring.length && !data.low_stock.length;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t("alerts.title")}</h1>
        <p className="text-sm text-slate-500">{t("alerts.subtitle")}</p>
      </div>

      {empty && (
        <div className="grid h-40 place-items-center rounded-2xl border border-dashed border-slate-300 text-sm text-slate-400">
          ✅ {t("alerts.none")}
        </div>
      )}

      {data.expired.length > 0 && (
        <Section icon={PackageX} color="#dc2626" title={t("alerts.expired")} count={data.expired.length}>
          {data.expired.map((b) => (
            <Row key={b.id}>
              <div>
                <div className="font-medium text-slate-800">{b.item_name}</div>
                <div className="text-xs text-red-600">
                  {b.expiry_date} · {Math.abs(b.days)} {t("alerts.daysAgo")}{b.lot_code ? ` · ${b.lot_code}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-semibold text-slate-700">{fmtNum(b.qty_remaining)} {b.unit}</span>
                <button onClick={() => dispose(b)}
                  className="flex items-center gap-1 rounded-lg bg-red-50 px-2.5 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-100">
                  <Trash2 size={14} /> {t("alerts.dispose")}
                </button>
              </div>
            </Row>
          ))}
        </Section>
      )}

      {data.expiring.length > 0 && (
        <Section icon={CalendarClock} color="#d97706" title={t("alerts.expiring")} count={data.expiring.length}>
          {data.expiring.map((b) => (
            <Row key={b.id}>
              <div>
                <div className="font-medium text-slate-800">{b.item_name}</div>
                <div className="text-xs text-amber-600">{b.expiry_date} · {b.days} {t("alerts.daysLeft")}{b.lot_code ? ` · ${b.lot_code}` : ""}</div>
              </div>
              <span className="font-semibold text-slate-700">{fmtNum(b.qty_remaining)} {b.unit}</span>
            </Row>
          ))}
        </Section>
      )}

      {data.low_stock.length > 0 && (
        <Section icon={TriangleAlert} color="#0ea5e9" title={t("alerts.lowStock")} count={data.low_stock.length}>
          {data.low_stock.map((it) => (
            <Row key={it.id}>
              <div>
                <div className="font-medium text-slate-800">{it.canonical_name}</div>
                <div className="text-xs text-slate-400">{it.center || ""}</div>
              </div>
              <span className={`font-semibold ${it.quantity <= 0 ? "text-red-600" : "text-slate-700"}`}>
                {fmtNum(it.quantity)} {it.unit}
              </span>
            </Row>
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ icon: Icon, color, title, count, children }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-lg" style={{ background: `${color}1a`, color }}>
          <Icon size={16} />
        </span>
        <h3 className="font-semibold text-slate-800">{title}</h3>
        <span className="ml-auto rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{count}</span>
      </div>
      <div className="divide-y divide-slate-100">{children}</div>
    </div>
  );
}

function Row({ children }) {
  return <div className="flex items-center justify-between px-4 py-2.5 text-sm">{children}</div>;
}
