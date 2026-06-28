import { useEffect, useState } from "react";
import { Wrench } from "lucide-react";
import { api } from "../lib/api";
import { fmtDate, fmtNum } from "../lib/ui";
import { useT } from "../lib/i18n.jsx";

const ACTIONS = {
  en: {
    "auth.login": "logged in",
    "auth.register": "registered",
    "movement.in": "received stock",
    "movement.out": "dispatched stock",
    "movement.adjust": "adjusted stock",
    "item.create": "created item",
    "item.match": "added to item",
    "item.update": "updated item",
    "item.delete": "deleted item",
    "upload.process": "imported a file",
    "upload.error": "failed an import",
    "schema.add_field": "added a field",
    "schema.create_table": "created a table",
    "record.create": "added a record",
    "agent.chat": "used the assistant",
    "org.create_region": "created a region",
    "org.create_center": "created a center",
    "org.create_user": "added a person",
    "org.set_active": "toggled a person",
    "org.reassign": "reassigned a person",
  },
  es: {
    "auth.login": "inició sesión",
    "auth.register": "se registró",
    "movement.in": "recibió stock",
    "movement.out": "despachó stock",
    "movement.adjust": "ajustó stock",
    "item.create": "creó un artículo",
    "item.match": "agregó a un artículo",
    "item.update": "actualizó un artículo",
    "item.delete": "eliminó un artículo",
    "upload.process": "importó un archivo",
    "upload.error": "falló una importación",
    "schema.add_field": "agregó un campo",
    "schema.create_table": "creó una tabla",
    "record.create": "agregó un registro",
    "agent.chat": "usó el asistente",
    "org.create_region": "creó una región",
    "org.create_center": "creó un centro",
    "org.create_user": "agregó una persona",
    "org.set_active": "activó/desactivó una persona",
    "org.reassign": "reasignó una persona",
  },
};

export default function Activity() {
  const { t, lang } = useT();
  const [tab, setTab] = useState("activity");
  const [logs, setLogs] = useState([]);
  const [corrections, setCorrections] = useState([]);
  const [loading, setLoading] = useState(true);
  const labels = ACTIONS[lang] || ACTIONS.en;

  useEffect(() => {
    setLoading(true);
    if (tab === "activity") {
      api.get("/api/audit?limit=200").then((d) => setLogs(d.logs)).finally(() => setLoading(false));
    } else {
      api.get("/api/corrections?limit=200").then((d) => setCorrections(d.corrections)).finally(() => setLoading(false));
    }
  }, [tab]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{t("act.title")}</h1>
        <p className="text-sm text-slate-500">{t("act.subtitle")}</p>
      </div>

      <div className="flex gap-1 rounded-xl bg-slate-100 p-1 sm:inline-flex">
        {["activity", "corrections"].map((tb) => (
          <button key={tb} onClick={() => setTab(tb)}
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium sm:flex-none ${
              tab === tb ? "bg-white text-brand-700 shadow-sm" : "text-slate-500"}`}>
            {t(`act.tab.${tb}`)}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <div className="p-8 text-center text-slate-400">{t("common.loading")}</div>
        ) : tab === "activity" ? (
          logs.length === 0 ? (
            <div className="p-8 text-center text-slate-400">{t("act.empty")}</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {logs.map((l) => (
                <li key={l.id} className="flex items-start gap-3 px-4 py-3 text-sm">
                  <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-400" />
                  <div className="min-w-0 flex-1">
                    <div className="text-slate-700">
                      <span className="font-semibold">{l.user_name || "—"}</span> {labels[l.action] || l.action}
                      {l.detail?.item_name && <span className="text-slate-500"> — {l.detail.item_name}</span>}
                      {l.detail?.quantity != null && <span className="text-slate-400"> ({l.detail.quantity})</span>}
                    </div>
                    <div className="text-xs text-slate-400">{fmtDate(l.created_at)}</div>
                  </div>
                </li>
              ))}
            </ul>
          )
        ) : corrections.length === 0 ? (
          <div className="p-8 text-center text-slate-400">{t("act.correctionsEmpty")}</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {corrections.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-amber-100 text-amber-600">
                    <Wrench size={15} />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-slate-700">{m.item_name}</div>
                    <div className="truncate text-xs text-slate-400">
                      {m.user_name || "—"} · {fmtDate(m.created_at)}{m.note ? ` · ${m.note}` : ""}
                    </div>
                  </div>
                </div>
                <div className={`shrink-0 font-semibold ${m.signed_quantity >= 0 ? "text-green-600" : "text-orange-600"}`}>
                  {m.signed_quantity >= 0 ? "+" : "−"}{fmtNum(m.quantity)} {m.unit}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
